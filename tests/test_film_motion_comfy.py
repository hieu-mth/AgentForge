"""Local motion adapter contracts: trusted JSON, owner approvals, no implicit retries."""
import copy
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Event
from unittest.mock import call, patch
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

        self.workflow.write_text(json.dumps(ltx.workflow(49)), encoding="utf-8")
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
            ltx.check_runtime.assert_called_with(motion.PORT, require_models=True, frames=49)
            self.assertEqual(motion.draft_resources.require_gpu.call_args_list[-2:],
                             [call("ltx", min_commit_mib=20480)] * 2)
        transport.assert_called_once()
        graph = transport.call_args.kwargs["body"]["prompt"]
        self.assertEqual(graph["10"]["inputs"]["noise_seed"], 7)
        self.assertEqual(graph["10"]["inputs"]["cfg"], 1)
        self.assertEqual(graph["6"]["inputs"]["length"], 49)
        self.assertEqual(graph["9"]["inputs"]["sigmas"], ltx.SIGMAS)
        self.assertEqual(graph["13"]["inputs"]["format.codec"], "h264")
        self.assertEqual(result["model_id"], ltx.MODEL_ID)
        with closing(motion._db(self.db)) as conn:
            row = conn.execute("SELECT model_id,image_sha,frames FROM motion_sources WHERE job_id=?",
                               (result["job_id"],)).fetchone()
        self.assertEqual(tuple(row), (ltx.MODEL_ID, "b" * 64, 49))

    def test_ltx_continuation_binds_extracted_png_and_ledger(self):
        import hashlib
        from contextlib import ExitStack, closing
        from agentforge.features.film_studio import motion_verify

        ltx = motion.motion_ltx
        self.workflow.write_text(json.dumps(ltx.workflow(49)), encoding="utf-8")
        source = {"motion_job": "a"*32, "motion_sha": "b"*64, "frames": 24}
        marker = motion_verify.continuation_marker(source)
        png = b"fixture continuation PNG"
        with ExitStack() as mocks:
            for target, name, value in (
                (motion.comfy_service, "_settings", {"port": motion.PORT, "install_root": self.root}),
                (motion.comfy_service, "ensure_running", True),
                (ltx, "verify_weights", None),
                (ltx, "check_runtime", []),
            ):
                mocks.enter_context(patch.object(target, name, return_value=value))
            mocks.enter_context(patch.object(ltx, "read_source", side_effect=AssertionError("FLUX source used")))
            extract = mocks.enter_context(patch.object(motion_verify, "read_continuation_frame",
                                                       return_value=(marker, png)))
            upload = mocks.enter_context(patch.object(ltx, "upload_source", return_value="frame.png"))
            result, transport = self.submit(confirm_ltx_gate_b=True, image_job="c"*32,
                                            image_sha="d"*64, ltx_encoder=self.root / ltx.ENCODER,
                                            previous_motion=source)
            extract.assert_called_once()
            self.assertEqual(upload.call_args.args[2], png)
            self.assertEqual(transport.call_args.kwargs["body"]["prompt"]["5"]["inputs"]["image"], "frame.png")
        with closing(motion._db(self.db)) as conn:
            row = conn.execute("SELECT image_job,image_sha FROM motion_sources WHERE job_id=?",
                               (result["job_id"],)).fetchone()
        self.assertEqual(tuple(row), (marker, hashlib.sha256(png).hexdigest()))

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

    def test_old_ledger_refuses_reads_and_writes_without_migration(self):
        self.db.parent.mkdir()
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("CREATE TABLE motion_jobs(job_id TEXT PRIMARY KEY, state TEXT)")
            conn.execute("INSERT INTO motion_jobs VALUES (?,?)", ("c"*32, "SUBMITTED"))
        before = self.db.read_bytes()
        for write in (False, True):
            with self.assertRaisesRegex(motion.MotionError, "Unsupported motion ledger schema"):
                motion._db(self.db, write=write)
        self.assertEqual(self.db.read_bytes(), before)

    def test_current_ledger_retains_failed_attempt_and_requires_confirmation(self):
        old_id = "c"*32
        plan_sha = self.plan["plan_sha256"]
        with closing(motion._db(self.db, write=True)) as conn, conn:
            conn.execute("INSERT INTO motion_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (old_id, "pilot", "sh-00001", plan_sha, "b"*64, "a"*64,
                          7, None, "FAILED", "old-created", "old-updated"))
            conn.execute("INSERT INTO motion_sources VALUES (?,?,?,?,?)",
                         (old_id, motion.motion_ltx.MODEL_ID, "d"*32, "e"*64, 33))
        with self.assertRaisesRegex(PermissionError, "explicitly confirm"):
            self.submit()
        newer, request = self.submit(confirm_new_attempt=True)
        request.assert_called_once()
        self.assertNotEqual(newer["job_id"], old_id)
        with closing(motion._db(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM motion_jobs").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT state FROM motion_jobs WHERE job_id=?", (old_id,)).fetchone()[0], "FAILED")
        with self.assertRaisesRegex(PermissionError, "reconcile"):
            self.submit(confirm_new_attempt=True)

    def test_attempt_admission_fails_closed_and_preserves_completed_shots(self):
        first, _ = self.submit()
        for state, provider_id, allowed in (
            ("SUBMITTING", None, False),
            ("SUBMITTED", str(uuid4()), False),
            ("UNKNOWN", None, False),
            ("FAILED", None, False),
            ("FAILED_RESOURCE", None, False),
            ("FAILED", "invalid-id", False),
            ("COMPLETE_UNVERIFIED", str(uuid4()), False),
            ("FAILED", str(uuid4()), True),
            ("FAILED_RESOURCE", str(uuid4()), True),
        ):
            with self.subTest(state=state, provider_id=provider_id), closing(motion._db(self.db)) as conn, conn:
                conn.execute("UPDATE motion_jobs SET state=?, provider_id=? WHERE job_id=?",
                             (state, provider_id, first["job_id"]))
                args = ("pilot", "sh-00001", self.plan["plan_sha256"], True)
                if allowed:
                    motion._check_attempt(conn, *args)
                else:
                    with self.assertRaises(PermissionError):
                        motion._check_attempt(conn, *args)

    def test_concurrent_attempt_cannot_dispatch_while_first_is_in_flight(self):
        first, _ = self.submit()
        with closing(motion._db(self.db)) as conn, conn:
            conn.execute("UPDATE motion_jobs SET state='FAILED' WHERE job_id=?",
                         (first["job_id"],))
        entered, release = Event(), Event()

        def dispatch(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("Test did not release the provider")
            return {"prompt_id": str(uuid4())}

        with (patch.object(motion.ops_control, "require_active"),
              patch.object(motion, "health", return_value={"status": "GPU_DETECTED_UNBENCHMARKED"}),
              patch.object(motion, "_json_request", side_effect=dispatch) as request,
              ThreadPoolExecutor(max_workers=1) as pool):
            args = dict(film_slug="pilot", shot_id="sh-00001",
                        plan_sha=self.plan["plan_sha256"], prompt=self.prompt,
                        workflow_path=self.workflow, workflow_sha=motion.inspect_workflow(self.workflow)["sha256"],
                        seed=7, confirmed=True, confirm_new_attempt=True,
                        film_root=self.films, db_path=self.db)
            running = pool.submit(motion.submit_shot, **args)
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaisesRegex(PermissionError, "LOCAL_INFERENCE_BUSY"):
                    motion.submit_shot(**args)
            finally:
                release.set()
            self.assertEqual(running.result()["status"], "SUBMITTED")
            request.assert_called_once()

    def test_ltx_rejects_path_injection_and_sampling_mutation(self):
        ltx = motion.motion_ltx
        for frames in ltx.FRAME_PRESETS:
            self.workflow.write_text(json.dumps(ltx.workflow(frames)), encoding="utf-8")
            self.assertEqual(motion.inspect_workflow(self.workflow)["profile"], ltx.profile(frames))
        for node, field, value in (("5", "image", "../outside.png"),
                                   ("6", "length", 73), ("6", "length", 49.0),
                                   ("6", "width", 640), ("10", "cfg", 2),
                                   ("9", "sigmas", "1.0, 0.0"),
                                   ("13", "filename_prefix", "another/output")):
            with self.subTest(field=field):
                record = ltx.workflow(49)
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
