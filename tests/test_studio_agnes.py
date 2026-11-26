import os
import io
import base64
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_motion_cloud, studio_agnes, studio_runtime
from agentforge.features.media import studio_agnes_image, visual_jobs
from agentforge.features.film_studio import media_probe


class AgnesContractTests(unittest.TestCase):
    def profile(self, model):
        return {"id": "agnes_test", "provider": "agnes", "model": model, "enabled": True,
                "base_url_env": "AGNES_BASE_URL", "api_key_env": "AGNES_API_KEY"}

    def test_capabilities_and_routes(self):
        image = self.profile(studio_agnes.IMAGE_MODEL)
        video = self.profile("agnes-video-2.5-flash")
        self.assertIs(studio_runtime.image_adapter(image), studio_agnes_image)
        self.assertIs(studio_runtime.motion_adapter(video), draft_motion_cloud)
        self.assertTrue(model_hub.capability_contract("image.generate", image)["runtime_compatible"])
        self.assertFalse(model_hub.capability_contract("film.motion", image)["runtime_compatible"])
        self.assertTrue(model_hub.capability_contract("film.motion", video)["runtime_compatible"])
        self.assertEqual(draft_motion_cloud.billable_durations(video), tuple(range(4, 11)))

    def test_payload_and_poll(self):
        body = studio_agnes.payload("agnes-video-2.5-flash", "Cat walks", 4)
        self.assertEqual(body["seconds"], "4")
        self.assertEqual(body["mode"], "text")
        self.assertEqual(studio_agnes.image_payload("Cat", "16:9")["extra_body"]["response_format"], "b64_json")
        with patch.object(studio_agnes, "_request", return_value={"video_id": "job_123"}) as request:
            self.assertEqual(studio_agnes.submit(body, "fixture"), "job_123")
            request.assert_called_once_with("POST", "/v1/videos", "fixture", body)
        row = {"provider_id": "job_123", "model": body["model"]}
        with patch.object(studio_agnes, "_request", return_value={"status": "completed", "url": "https://example.com/result.mp4"}) as request:
            self.assertEqual(studio_agnes.poll(row, "fixture")["status"], "completed")
            self.assertIn("video_id=job_123", request.call_args.args[1])

    def test_endpoint_and_private_download_rejected(self):
        profile = self.profile(studio_agnes.IMAGE_MODEL)
        with patch.dict(os.environ, {"AGNES_BASE_URL": "https://example.com/v1", "AGNES_API_KEY": "fixture"}):
            with self.assertRaises(ValueError):
                studio_agnes.key(profile)
        with patch.object(studio_agnes.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ValueError):
                studio_agnes._public_addresses("example.com")

    def test_explicit_image_probe_persists_verified_asset_and_never_resubmits(self):
        from PIL import Image
        profile = self.profile(studio_agnes.IMAGE_MODEL)
        buffer = io.BytesIO()
        Image.new("RGB", (32, 18), "orange").save(buffer, format="PNG")
        payload = {"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}]}
        request = {"ack": "RUN_MEDIA_MODEL_PROBE", "profile_id": profile["id"],
                   "expected_revision": 1, "probe_id": "a"*32, "prompt": "Cat"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with (patch.object(model_hub, "DB_PATH", root/"hub.db"),
                  patch.object(visual_jobs, "DB", root/"visuals.db"),
                  patch.object(visual_jobs, "OUTPUTS", root/"images"),
                  patch.object(media_probe.ops_control, "require_active"),
                  patch.dict(os.environ, {"AGNES_BASE_URL": studio_agnes.BASE, "AGNES_API_KEY": "fixture"}),
                  patch.object(studio_agnes, "_request", return_value=payload) as transport):
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, profile=profile)
                first = media_probe.handle(request)
                self.assertEqual(first["status"], "ASSET_READY")
                self.assertEqual(media_probe.handle(request), first)
                self.assertEqual(media_probe.handle({key: value if key != "ack" else "POLL_MEDIA_MODEL_PROBE"
                                                     for key, value in request.items() if key != "prompt"}), first)
                transport.assert_called_once()
                data, mime = visual_jobs.image_for_job(request["probe_id"])
                self.assertEqual(mime, "image/png")
                self.assertTrue(data.startswith(b"\x89PNG"))
                self.assertTrue(visual_jobs.report()["jobs"][0]["probe"])

    def test_video_probe_persists_id_and_reuses_submission(self):
        profile = self.profile("agnes-video-2.5-flash")
        request = {"ack": "RUN_MEDIA_MODEL_PROBE", "profile_id": profile["id"],
                   "expected_revision": 1, "probe_id": "b"*32, "prompt": "Cat"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with (patch.object(model_hub, "DB_PATH", root/"hub.db"),
                  patch.object(draft_motion_cloud, "DB", root/"motion.db"),
                  patch.object(draft_motion_cloud, "bind", return_value=profile),
                  patch.object(media_probe.ops_control, "require_active"),
                  patch.dict(os.environ, {"AGNES_BASE_URL": studio_agnes.BASE, "AGNES_API_KEY": "fixture"}),
                  patch.object(studio_agnes, "_request", side_effect=[
                      {"video_id": "remote-1"}, {"status": "processing"}]) as transport):
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, profile=profile)
                first = media_probe.handle(request)
                self.assertEqual(first["status"], "SUBMITTED")
                self.assertEqual(media_probe.handle(request), first)
                poll = {key: value if key != "ack" else "POLL_MEDIA_MODEL_PROBE"
                        for key, value in request.items() if key != "prompt"}
                self.assertEqual(media_probe.handle(poll)["status"], "SUBMITTED")
                self.assertEqual([call.args[0] for call in transport.call_args_list], ["POST", "GET"])
                self.assertEqual(media_probe.video_record(request["probe_id"])["provider_id"], "remote-1")

    def test_production_cloud_durations_are_provider_specific(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)/"hub.db"
            profile = self.profile("agnes-video-2.5-flash")
            model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, db_path=db, profile=profile)
            options = model_hub.catalog(db_path=db)["production_options"]
            self.assertEqual(options["min_cloud_seconds"], 8)
            _, candidates = model_hub.production_candidates("cloud", db_path=db)
            self.assertEqual(candidates[0]["billable_durations_seconds"], list(range(4, 11)))
            self.assertFalse(candidates[0]["native_audio"])
