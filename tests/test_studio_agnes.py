import os
import io
import base64
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch, Mock

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


    def test_http_classification_never_echoes_provider_message(self):
        import json
        for status, code, rejected, retryable in (
            (503, "video_queue_full", True, True),
            (503, "other", False, False),
            (500, "video_queue_full", False, False),
            (429, "rate_limit_exceeded", True, True),
            (401, "", True, False),
            (402, "", True, False),
            (400, "", True, False),
        ):
            with self.subTest(status=status, code=code):
                response = Mock(status=status)
                response.read.return_value = json.dumps({
                    "code": code, "message": "secret fixture token", "data": None}).encode()
                response.getheader.return_value = "180"
                error = studio_agnes._http_error(response)
                self.assertEqual(error.rejected, rejected)
                self.assertEqual(error.retryable, retryable)
                self.assertEqual(error.retry_after, 180)
                self.assertNotIn("secret", str(error))
                self.assertIn(str(status), str(error))
        response = Mock(status=503)
        response.read.return_value = b'{"code":"video_queue_full","video_id":"already-accepted"}'
        self.assertNotIsInstance(studio_agnes._http_error(response), studio_agnes.AgnesHTTPError)

    def test_queue_retries_preserve_ledger_and_budget(self):
        motion = draft_motion_cloud
        profile = self.profile("agnes-video-2.5-flash")
        scene = {"frames": 96, "image_prompt": "Cat", "description": "Cat walks", "audio": "Quiet"}
        job = {"id": "a"*32, "status": "RUNNING",
               "production_plan": {"method": "cloud", "motion_ref": profile["id"], "max_cloud_seconds": 4},
               "board": {"scenes": [scene]}}
        errors = [studio_agnes.AgnesHTTPError(503, "video_queue_full") for _ in range(3)]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared = (job["id"], job, root, motion.workflow_sha(profile))
            states = []
            def save():
                states.append(job["status"])
            with (patch.object(motion, "DB", root/"ledger.db"),
                  patch.object(motion, "RETRY_DELAYS", (0, 0, 0)),
                  patch.object(motion, "_key", return_value="fixture"),
                  patch.object(motion.ops_control, "require_active"),
                  patch.object(model_hub, "cloud_call_limit", return_value=8),
                  patch.object(studio_agnes, "submit_video", side_effect=[*errors, "remote-1"]) as submit,
                  patch.object(motion, "_poll", return_value={"status": "completed", "url": "fixture"}),
                  patch.object(motion, "_path", return_value=root/"clip.mp4"),
                  patch.object(studio_agnes, "download_video", side_effect=lambda _, target, seconds: target.write_bytes(b"fixture")),
                  patch.object(motion.mp4, "verify_video", return_value="f"*64)):
                motion.run_shot(scene, 0, prepared, profile, save, lambda: False)
                self.assertEqual(submit.call_count, 4)
                self.assertEqual(job["cloud_calls"], 4)
                self.assertEqual(job["cloud_motion_seconds"], 4)
                self.assertEqual(states.count("WAITING_CLOUD_RESOURCES"), 3)
                self.assertEqual(motion._row(scene["motion_job"])["state"], "VERIFIED")
                self.assertEqual(scene["motion_sha"], "f"*64)
                self.assertEqual(motion.submission_error(scene["motion_job"])["attempts"], 3)
                self.assertTrue(all(call.args[0] == submit.call_args_list[0].args[0] for call in submit.call_args_list))

    def test_queue_exhaustion_and_owner_retry_reuse_reservation(self):
        motion = draft_motion_cloud
        profile = self.profile("agnes-video-2.5-flash")
        scene = {"frames": 96, "image_prompt": "Cat", "description": "Cat walks"}
        job = {"id": "b"*32, "status": "RUNNING",
               "production_plan": {"method": "cloud", "motion_ref": profile["id"], "max_cloud_seconds": 4},
               "board": {"scenes": [scene]}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared = (job["id"], job, root, motion.workflow_sha(profile))
            with (patch.object(motion, "DB", root/"ledger.db"),
                  patch.object(motion, "RETRY_DELAYS", (0, 0, 0)),
                  patch.object(motion, "_key", return_value="fixture"),
                  patch.object(motion.ops_control, "require_active"),
                  patch.object(model_hub, "cloud_call_limit", return_value=8),
                  patch.object(studio_agnes, "submit_video", side_effect=studio_agnes.AgnesHTTPError(503, "video_queue_full")) as submit):
                with self.assertRaisesRegex(ValueError, "video_queue_full"):
                    motion.run_shot(scene, 0, prepared, profile, lambda: None, lambda: False)
                ident = scene["motion_job"]
                self.assertEqual(submit.call_count, 4)
                self.assertEqual(motion._row(ident)["state"], "REJECTED")
                self.assertIsNone(motion.submission_error(ident)["retry_at"])
                self.assertEqual(motion.reconciliation_jobs(job), [])
                with self.assertRaisesRegex(ValueError, "video_queue_full"):
                    motion.run_shot(scene, 0, prepared, profile, lambda: None, lambda: False)
                self.assertEqual(submit.call_count, 4)
                with self.assertRaisesRegex(ValueError, "video_queue_full"):
                    motion.run_shot(scene, 0, prepared, profile, lambda: None, lambda: False, retry_motion_job=ident)
                self.assertEqual(submit.call_count, 5)
                self.assertEqual(scene["motion_job"], ident)
                self.assertEqual(job["cloud_motion_seconds"], 4)
                self.assertEqual(job["cloud_calls"], 5)

    def test_retry_timeout_remains_uncertain(self):
        from agentforge.features.film_studio.draft_resources import NeedsReconciliation
        motion = draft_motion_cloud
        profile = self.profile("agnes-video-2.5-flash")
        scene = {"frames": 96, "image_prompt": "Cat", "description": "Cat walks"}
        job = {"id": "c"*32, "status": "RUNNING", "production_plan": {
            "method": "cloud", "motion_ref": profile["id"], "max_cloud_seconds": 4}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared = (job["id"], job, root, motion.workflow_sha(profile))
            with (patch.object(motion, "DB", root/"ledger.db"),
                  patch.object(motion, "RETRY_DELAYS", (0, 0, 0)),
                  patch.object(motion, "_key", return_value="fixture"),
                  patch.object(motion.ops_control, "require_active"),
                  patch.object(model_hub, "cloud_call_limit", return_value=8),
                  patch.object(studio_agnes, "submit_video", side_effect=[
                      studio_agnes.AgnesHTTPError(503, "video_queue_full"),
                      ValueError("Agnes request timed out; outcome unknown.")]) as submit):
                with self.assertRaises(NeedsReconciliation):
                    motion.run_shot(scene, 0, prepared, profile, lambda: None, lambda: False)
                self.assertEqual(motion._row(scene["motion_job"])["state"], "SUBMITTING")
                with self.assertRaises(NeedsReconciliation):
                    motion.run_shot(scene, 0, prepared, profile, lambda: None, lambda: False)
                self.assertEqual(submit.call_count, 2)

    def test_permanent_rejection_is_not_retried(self):
        motion = draft_motion_cloud
        profile = self.profile("agnes-video-2.5-flash")
        scene = {"frames": 96, "image_prompt": "Cat", "description": "Cat walks"}
        job = {"id": "d"*32, "status": "RUNNING", "production_plan": {
            "method": "cloud", "motion_ref": profile["id"], "max_cloud_seconds": 4}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared = (job["id"], job, root, motion.workflow_sha(profile))
            with (patch.object(motion, "DB", root/"ledger.db"),
                  patch.object(motion, "_key", return_value="fixture"),
                  patch.object(motion.ops_control, "require_active"),
                  patch.object(model_hub, "cloud_call_limit", return_value=8),
                  patch.object(studio_agnes, "submit_video", side_effect=studio_agnes.AgnesHTTPError(401)) as submit):
                with self.assertRaisesRegex(ValueError, "401"):
                    motion.run_shot(scene, 0, prepared, profile, lambda: None, lambda: False)
                self.assertEqual(motion._row(scene["motion_job"])["state"], "REJECTED")
                self.assertIsNone(motion.submission_error(scene["motion_job"])["retry_at"])
                submit.assert_called_once()


    def test_old_uncertain_request_requires_owner_attestation_and_no_post(self):
        from contextlib import closing
        motion = draft_motion_cloud
        profile = self.profile("agnes-video-2.5-flash")
        ident = "e"*32
        job = {"id": "f"*32, "status": "NEEDS_RECONCILIATION",
               "board": {"scenes": [{"motion_job": ident}]}}
        payload = {"motion_job": ident, "request_sha": "d"*64,
                   "provider_request_id": "original-request-123", "owner_confirmed_rejected": True}
        with tempfile.TemporaryDirectory() as folder, patch.object(motion, "DB", Path(folder)/"ledger.db"):
            with closing(motion._db(True)) as conn, conn:
                conn.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                    (ident, job["id"], "text-to-video", profile["model"], 4, payload["request_sha"], "SUBMITTING", None, None))
            with patch.object(studio_agnes, "_request", side_effect=AssertionError("unexpected network")) as request:
                with self.assertRaises(PermissionError):
                    motion.confirm_rejected_submission(job, {**payload, "owner_confirmed_rejected": False}, profile)
                self.assertEqual(motion._row(ident)["state"], "SUBMITTING")
                result = motion.confirm_rejected_submission(job, payload, profile)
                self.assertFalse(result["provider_status_verified"])
                self.assertEqual(result["shot"], 1)
                self.assertEqual(motion._row(ident)["state"], "REJECTED")
                self.assertIsNone(motion.submission_error(ident)["retry_at"])
                request.assert_not_called()
