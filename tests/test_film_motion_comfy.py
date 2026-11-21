"""Local motion adapter contracts: trusted JSON, owner approvals, no implicit retries."""
import copy
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from agentforge.features.film_studio import long_form, motion_comfy as motion


def template():
    api = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "An original cinematic fantasy",
              "clip": ["2", 0]}},
        "4": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {
              "width": 640, "height": 352, "length": 49, "batch_size": 1}},
        "5": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "6": {"class_type": "KSampler", "inputs": {
              "seed": 101, "steps": 20, "cfg": 5, "sampler_name": "euler",
              "scheduler": "simple", "denoise": 1.0, "model": ["5", 0],
              "positive": ["3", 0], "negative": ["3", 0],
              "latent_image": ["4", 0]}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["7", 0]}},
        "9": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": 12}},
        "10": {"class_type": "SaveVideo", "inputs": {"video": ["9", 0],
               "filename_prefix": "af_test"}},
    }
    return {"format": "agentforge.film.comfy.t2v.v1", "positive_node": "3",
            "seed_node": "6", "size_node": "4", "fps_node": "9",
            "output_node": "10", "api": api}


def sample_plan(seconds=4):
    return long_form.build_plan(
        title="Original test", genre="fantasy", style="cinematic",
        chapters=[{"id": "a", "title": "One", "synopsis": "A hero travels",
                   "duration_seconds": seconds, "character_ids": []}],
        shot_seconds=4)


class MotionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(motion, "BLOCKED_MODELS", frozenset()))
        self.enterContext(patch.object(motion.draft_resources, "require_gpu"))
        self.enterContext(patch.object(motion.comfy_service, "require_idle_queue"))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.films = self.root / "films"
        self.db = self.root / "data" / "motion.db"
        self.workflow = self.root / "wan_api.json"
        self.workflow.write_text(json.dumps(template()), encoding="utf-8")
        self.plan = sample_plan()
        long_form.save_plan(self.films, "pilot", self.plan)
        self.prompt = "Original movie character walking slowly through a forest, low camera, breeze."

    def submit(self, **kw):
        args = dict(film_slug="pilot", shot_id="sh-00001",
                    plan_sha=self.plan["plan_sha256"], prompt=self.prompt,
                    workflow_path=self.workflow,
                    workflow_sha=motion.inspect_workflow(self.workflow)["sha256"],
                    seed=7, confirmed=True, film_root=self.films,
                    db_path=self.db)
        args.update(kw)
        with patch.object(motion.ops_control, "require_active"), \
             patch.object(motion, "health", return_value={"status": "GPU_DETECTED_UNBENCHMARKED"}), \
             patch.object(motion, "_json_request",
                          return_value={"prompt_id": str(uuid4())}) as called:
            result = motion.submit_shot(**args)
            return result, called

    def test_profile_is_conservative_and_cannot_be_raised_by_owner_workflow(self):
        self.assertEqual(motion.PROFILE["frames"], 49)
        self.assertEqual(motion.PROFILE["width"], 640)
        self.assertEqual(motion.PROFILE["batch_size"], 1)
        graph = template()
        graph["api"]["4"]["inputs"]["width"] = 1280
        self.workflow.write_text(json.dumps(graph))
        with self.assertRaises(motion.MotionError):
            motion.inspect_workflow(self.workflow)

    def test_unknown_nodes_and_url_paths_are_refused(self):
        graph = template()
        graph["api"]["1"]["class_type"] = "ExecutePythonScript"
        self.workflow.write_text(json.dumps(graph))
        with self.assertRaises(motion.MotionError):
            motion.inspect_workflow(self.workflow)
        graph = template()
        graph["api"]["1"]["inputs"]["unet_name"] = "https://malicious.test/model"
        self.workflow.write_text(json.dumps(graph))
        with self.assertRaises(motion.MotionError):
            motion.inspect_workflow(self.workflow)

    def test_submit_requires_confirmation_and_correct_source_sha(self):
        args = dict(film_slug="pilot", shot_id="sh-00001", plan_sha=self.plan["plan_sha256"],
                    prompt=self.prompt, workflow_path=self.workflow,
                    workflow_sha=motion.inspect_workflow(self.workflow)["sha256"],
                    seed=5, film_root=self.films, db_path=self.db)
        with self.assertRaises(PermissionError):
            motion.submit_shot(**args)
        args["plan_sha"] = "0" * 64
        with patch.object(motion.ops_control, "require_active"):
            with self.assertRaises(PermissionError):
                motion.submit_shot(**args, confirmed=True)

    def test_submit_dispatches_exactly_once_without_upload_or_verified_claim(self):
        result, mocked = self.submit()
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertFalse(result["video_verified"])
        self.assertFalse(result["youtube_uploaded"])
        self.assertEqual(mocked.call_count, 1)
        route = mocked.call_args.args[0]
        payload = mocked.call_args.kwargs["body"]
        self.assertEqual(route, "/prompt")
        graph = payload["prompt"]
        self.assertEqual(graph["3"]["inputs"]["text"], self.prompt)
        self.assertEqual(graph["6"]["inputs"]["seed"], 7)
        self.assertTrue(graph["10"]["inputs"]["filename_prefix"].startswith("af_motion_"))
        with self.assertRaises(PermissionError):
            self.submit()

    def test_fp16_is_blocked_before_provider_submission(self):
        with (patch.object(motion, "BLOCKED_MODELS", {motion.PILOT_MODEL_ID}),
              self.assertRaisesRegex(motion.MotionError, "WAN_FP16_BLOCKED")):
            self.submit()
        self.assertFalse(self.db.exists())

    def test_ltx_requires_gate_b_and_binds_only_reviewed_inputs(self):
        from contextlib import ExitStack, closing
        from agentforge.features.film_studio import motion_ltx as ltx

        self.workflow.write_text(json.dumps(ltx.workflow()), encoding="utf-8")
        digest = motion.inspect_workflow(self.workflow)["sha256"]
        with self.assertRaisesRegex(PermissionError, "Gate B"):
            self.submit()
        self.assertFalse(self.db.exists())
        with ExitStack() as mocks:
            for target, name, value in (
                (motion.comfy_service, "_settings", {"port": motion.PORT, "install_root": self.root}),
                (motion.comfy_service, "ensure_running", True),
                (ltx, "verify_weights", None),
                (ltx, "read_source", b"fixture image"),
                (ltx, "upload_source", "af_motion_source_" + "c" * 32 + ".png"),
                (ltx, "check_runtime", []),
            ):
                mocks.enter_context(patch.object(target, name, return_value=value))
            with (patch.object(ltx, "upload_source", side_effect=ValueError("Invalid ComfyUI upload response")) as upload,
                  patch.object(motion, "_json_request") as request,
                  patch.object(motion.ops_control, "require_active"),
                  patch.object(motion, "health", return_value={"status": "GPU_DETECTED_UNBENCHMARKED"}),
                  self.assertRaisesRegex(ValueError, "Invalid ComfyUI upload response")):
                motion.submit_shot(film_slug="pilot", shot_id="sh-00001",
                                   plan_sha=self.plan["plan_sha256"], prompt=self.prompt,
                                   workflow_path=self.workflow, workflow_sha=digest,
                                   seed=7, confirmed=True, confirm_ltx_gate_b=True,
                                   image_job="a" * 32, image_sha="b" * 64,
                                   ltx_encoder=self.root / ltx.ENCODER,
                                   film_root=self.films, db_path=self.db.with_name("failed.sqlite3"))
            upload.assert_called_once()
            request.assert_not_called()
            with closing(motion._db(self.db.with_name("failed.sqlite3"))) as conn:
                self.assertEqual(conn.execute("SELECT state, provider_id FROM motion_jobs").fetchone()[:],
                                 ("FAILED", None))
            result, transport = self.submit(workflow_sha=digest, confirm_ltx_gate_b=True,
                                            image_job="a" * 32, image_sha="b" * 64,
                                            ltx_encoder=self.root / ltx.ENCODER)
        transport.assert_called_once()
        graph = transport.call_args.kwargs["body"]["prompt"]
        self.assertEqual(graph["10"]["inputs"]["noise_seed"], 7)
        self.assertEqual(graph["10"]["inputs"]["cfg"], 1)
        self.assertEqual(graph["6"]["inputs"]["length"], 33)
        self.assertEqual(graph["9"]["inputs"]["sigmas"], ltx.SIGMAS)
        self.assertEqual(graph["13"]["inputs"]["format.codec"], "h264")
        self.assertEqual(result["model_id"], ltx.MODEL_ID)
        with closing(motion._db(self.db)) as conn:
            row = conn.execute("SELECT model_id,image_sha FROM motion_sources WHERE job_id=?",
                               (result["job_id"],)).fetchone()
        self.assertEqual(tuple(row), (ltx.MODEL_ID, "b" * 64))

    def test_ltx_upload_response_contract(self):
        ltx = motion.motion_ltx
        job_id = "c" * 32
        name = f"af_motion_source_{job_id}.png"
        core = {"name": name, "subfolder": "", "type": "input"}
        asset = {"id": "fixture", "name": name, "size": 20, "mime_type": "image/png",
                 "tags": ["input"], "preview_url": "/api/assets/fixture/preview"}
        valid = (core, {**core, "asset": asset}, {**core, "metadata": {"version": 1}})
        invalid = ({"name": "another.png"}, {"subfolder": "other"}, {"type": "output"},
                   {"name": [name]}, {"subfolder": None}, {"type": 1}, {"asset": []})
        cases = [(json.dumps(value).encode(), True) for value in valid]
        cases.extend((json.dumps({**core, **value}).encode(), False) for value in invalid)
        cases.extend((raw, False) for raw in (b"{", b"<html>", b"[]", b"null", b" " * 4097,
                                              b"\xff", b'{"name":"missing-fields.png"}'))
        for raw, accepted in cases:
            with self.subTest(raw=raw[:150], accepted=accepted), patch.object(ltx.http.client, "HTTPConnection") as client:
                connection = client.return_value
                response = connection.getresponse.return_value
                response.status = 200
                response.read.return_value = raw
                if accepted:
                    self.assertEqual(ltx.upload_source(8188, job_id, b"fixture"), name)
                else:
                    with self.assertRaisesRegex(ValueError, "ComfyUI .*upload response|unexpected input filename"):
                        ltx.upload_source(8188, job_id, b"fixture")
                connection.request.assert_called_once()
                self.assertEqual(connection.request.call_args.args, ("POST", "/upload/image"))
                response.read.assert_called_once_with(4097)
                connection.close.assert_called_once()

    def test_ltx_rejects_path_injection_and_sampling_mutation(self):
        ltx = motion.motion_ltx
        for node, field, value in (("5", "image", "../outside.png"),
                                   ("9", "sigmas", "1.0, 0.0"),
                                   ("13", "filename_prefix", "another/output")):
            with self.subTest(field=field):
                record = ltx.workflow()
                record["api"][node]["inputs"][field] = value
                self.workflow.write_text(json.dumps(record), encoding="utf-8")
                with self.assertRaisesRegex(motion.MotionError, "pinned pilot workflow"):
                    motion.inspect_workflow(self.workflow)

    def test_uncertain_http_failure_keeps_submitting_checkpoint_and_no_retry(self):
        with patch.object(motion.ops_control, "require_active"), \
             patch.object(motion, "health", return_value={"status": "GPU_DETECTED_UNBENCHMARKED"}), \
             patch.object(motion, "_json_request", side_effect=OSError("offline")) as called:
            with self.assertRaises(OSError):
                motion.submit_shot(
                    film_slug="pilot", shot_id="sh-00001",
                    plan_sha=self.plan["plan_sha256"], prompt=self.prompt,
                    workflow_path=self.workflow,
                    workflow_sha=motion.inspect_workflow(self.workflow)["sha256"],
                    seed=7, confirmed=True, film_root=self.films, db_path=self.db)
            self.assertEqual(called.call_count, 1)
        db = motion._db(self.db)
        with db:
            statuses = [x[0] for x in db.execute("SELECT state FROM motion_jobs")]
        db.close()
        self.assertEqual(statuses, ["SUBMITTING"])
        with self.assertRaises(PermissionError):
            self.submit()

    def test_rejects_eight_second_shot_for_four_second_pilot(self):
        plan = long_form.build_plan(
            title="Original test", genre="fantasy", style="cinematic",
            chapters=[{"id": "a", "title": "One", "synopsis": "A hero travels",
                       "duration_seconds": 8, "character_ids": []}],
            shot_seconds=8)
        long_form.save_plan(self.films, "eight", plan)
        with patch.object(motion.ops_control, "require_active"):
            with self.assertRaises(motion.MotionError):
                motion.submit_shot(
                    film_slug="eight", shot_id="sh-00001",
                    plan_sha=plan["plan_sha256"], prompt=self.prompt,
                    workflow_path=self.workflow,
                    workflow_sha=motion.inspect_workflow(self.workflow)["sha256"],
                    seed=7, confirmed=True, film_root=self.films, db_path=self.db)

    def test_history_success_is_not_runtime_video_validation(self):
        job, _ = self.submit()
        with patch.object(motion, "_json_request", return_value={
                "000": {}}):
            view = motion.job_status(job["job_id"], db_path=self.db)
        self.assertEqual(view["status"], "PROVIDER_QUEUED_OR_UNKNOWN")
        with closing(motion._db(self.db)) as db:
            provider_id = db.execute(
                "SELECT provider_id FROM motion_jobs WHERE job_id=?", (job["job_id"],)
            ).fetchone()[0]
        with patch.object(motion, "_json_request", return_value={
                provider_id: {"status": {"completed": True, "status_str": "success"}}}):
            view = motion.job_status(job["job_id"], db_path=self.db)
        self.assertEqual(view["status"], "COMFY_COMPLETE_NOT_IMPORTED_OR_VERIFIED")
        self.assertFalse(view["video_verified"])
        db = motion._db(self.db)
        try:
            saved_state = db.execute(
                "SELECT state FROM motion_jobs WHERE job_id=?", (job["job_id"],)
            ).fetchone()[0]
        finally:
            db.close()
        self.assertEqual(saved_state, "COMPLETE_UNVERIFIED")

    def test_health_unavailable_never_claims_gpu_ready(self):
        with patch.object(motion, "_json_request", side_effect=OSError("offline")):
            self.assertEqual(motion.health()["status"], "COMFYUI_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
