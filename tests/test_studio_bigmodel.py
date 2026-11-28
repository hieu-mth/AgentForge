"""BigModel transport and Model Hub probe contract (no live API or paid calls)."""
import base64
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_motion_cloud, media_probe, studio_bigmodel, studio_runtime
from agentforge.features.film_studio.studio_contracts import ProviderRequestError


class BigModelTests(unittest.TestCase):
    def profile(self):
        return {"id": "bigmodel_test", "provider": "bigmodel", "model": studio_bigmodel.MODEL,
                "enabled": True, "base_url_env": "BIGMODEL_BASE_URL", "api_key_env": "BIGMODEL_API_KEY"}

    def test_registry_routes_and_duration(self):
        profile = self.profile()
        self.assertIs(studio_runtime.motion_adapter(profile), draft_motion_cloud)
        self.assertEqual(draft_motion_cloud.billable_durations(profile), (5,))
        self.assertEqual(draft_motion_cloud.output_profile(profile).max_frames, 120)
        self.assertFalse(draft_motion_cloud.native_audio(profile))
        self.assertFalse(draft_motion_cloud.supports({**profile, "model": "cogvideox-3"}))
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "hub.db"
            model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, db_path=db, profile=profile)
            _, candidates = model_hub.production_candidates("auto", db_path=db)
            self.assertEqual({c["method"] for c in candidates}, {"cloud", "hybrid"})
            self.assertTrue(all(c["billable_durations_seconds"] == [5] for c in candidates))

    def test_credentials_and_payload(self):
        profile = self.profile()
        with patch.dict(os.environ, {"BIGMODEL_BASE_URL": studio_bigmodel.BASE, "BIGMODEL_API_KEY": "id.secret"}):
            self.assertEqual(studio_bigmodel.credential(profile), "id.secret")
        with patch.dict(os.environ, {"BIGMODEL_BASE_URL": studio_bigmodel.BASE, "BIGMODEL_API_KEY": "id-only"}):
            with self.assertRaises(ValueError):
                studio_bigmodel.credential(profile)
        with self.assertRaises(ValueError):
            studio_bigmodel.validate_endpoint("https://other.example")
        body = studio_bigmodel.payload(studio_bigmodel.MODEL, "Cat walks", 5)
        self.assertEqual(body, {"model": studio_bigmodel.MODEL, "prompt": "Cat walks"})
        image = io.BytesIO()
        Image.new("RGB", (32, 32)).save(image, format="PNG")
        body = studio_bigmodel.payload(studio_bigmodel.MODEL, "Cat blinks", 5, image=image.getvalue())
        self.assertEqual(base64.b64decode(body["image_url"]), image.getvalue())
        with self.assertRaises(ValueError):
            studio_bigmodel.payload(studio_bigmodel.MODEL, "Cat", 10)
        with self.assertRaises(ValueError):
            studio_bigmodel.payload(studio_bigmodel.MODEL, "x" * 513, 5)

    def test_status_and_identity(self):
        row = {"provider_id": "job-1", "model": studio_bigmodel.MODEL}
        with patch.object(studio_bigmodel, "_request", return_value={
                "id": "job-1", "model": studio_bigmodel.MODEL, "task_status": "SUCCESS",
                "video_result": [{"url": "https://example.com/result.mp4"}]}) as request:
            self.assertEqual(studio_bigmodel.poll_video(row, "fixture"),
                             {"status": "completed", "url": "https://example.com/result.mp4"})
            request.assert_called_once_with("GET", "/async-result/job-1", "fixture")
        with patch.object(studio_bigmodel, "_request", return_value={"id": "other", "task_status": "SUCCESS"}):
            with self.assertRaises(ValueError):
                studio_bigmodel.poll_video(row, "fixture")
        with patch.object(studio_bigmodel, "_request", return_value={"task_status": "PROCESSING"}):
            with self.assertRaises(ProviderRequestError):
                studio_bigmodel.submit_video({"model": studio_bigmodel.MODEL, "prompt": "Cat"}, "fixture", "text-to-video")

    def test_probe_reserves_once_and_polls_existing_id(self):
        profile = self.profile()
        request = {"ack": "RUN_MEDIA_MODEL_PROBE", "profile_id": profile["id"],
                   "expected_revision": 1, "probe_id": "b" * 32, "prompt": "Cat"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with (patch.object(model_hub, "DB_PATH", root / "hub.db"),
                  patch.object(draft_motion_cloud, "DB", root / "motion.db"),
                  patch.object(draft_motion_cloud, "bind", return_value=profile),
                  patch.object(media_probe.ops_control, "require_active"),
                  patch.dict(os.environ, {"BIGMODEL_BASE_URL": studio_bigmodel.BASE, "BIGMODEL_API_KEY": "id.secret"}),
                  patch.object(studio_bigmodel, "_request", side_effect=[
                      {"id": "remote-1", "model": studio_bigmodel.MODEL, "task_status": "PROCESSING"},
                      {"id": "remote-1", "model": studio_bigmodel.MODEL, "task_status": "PROCESSING"}]) as transport):
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, profile=profile)
                first = media_probe.handle(request)
                self.assertEqual(first["status"], "SUBMITTED")
                self.assertEqual(media_probe.handle(request), first)
                poll = {key: value if key != "ack" else "POLL_MEDIA_MODEL_PROBE"
                        for key, value in request.items() if key != "prompt"}
                self.assertEqual(media_probe.handle(poll)["status"], "SUBMITTED")
                self.assertEqual([call.args[0] for call in transport.call_args_list], ["POST", "GET"])
                self.assertEqual(media_probe.video_record(request["probe_id"])["seconds"], 5)
