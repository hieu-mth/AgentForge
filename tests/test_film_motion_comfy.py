"""Local motion adapter contracts: trusted JSON, owner approvals, no implicit retries."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from agentforge.domains.media import long_form, motion_comfy as motion


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
        with motion._db(self.db) as db:
            provider_id = db.execute(
                "SELECT provider_id FROM motion_jobs WHERE job_id=?", (job["job_id"],)
            ).fetchone()[0]
        with patch.object(motion, "_json_request", return_value={
                provider_id: {"status": {"completed": True, "status_str": "success"}}}):
            view = motion.job_status(job["job_id"], db_path=self.db)
        self.assertEqual(view["status"], "COMFY_COMPLETE_NOT_IMPORTED_OR_VERIFIED")
        self.assertFalse(view["video_verified"])

    def test_health_unavailable_never_claims_gpu_ready(self):
        with patch.object(motion, "_json_request", side_effect=OSError("offline")):
            self.assertEqual(motion.health()["status"], "COMFYUI_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
