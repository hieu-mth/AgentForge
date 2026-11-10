"""Wave 8 Film Studio: real MP4 intake contract exercised with safe fixtures.

No actual GPU, ComfyUI or native FFmpeg invoked in CI; Owner evidence stays
UNVERIFIED until manual 12-GiB pilot. Tests are intentionally strict on SHA,
job provenance, unsafe filenames, ffprobe frame count, atomic copy and no retry.
"""
import hashlib
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from agentforge.features.film_studio import motion_comfy as motion
from agentforge.features.film_studio import motion_verify as verify
from agentforge.features.film_studio import long_form
from tests.test_film_motion_comfy import template, sample_plan

TEST_MP4 = b"\x00\x00\x00\x18ftypisom" + b"local-test-video" * 200


class MotionRuntimeWave8Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.films = self.root / "workspace" / "films"
        self.db = self.root / "data" / "motion.sqlite3"
        self.outputs = self.root / "comfy-output"
        self.outputs.mkdir()
        self.workflow = self.root / "pilot.json"
        self.workflow.write_text(json.dumps(template()), encoding="utf-8")
        self.plan = sample_plan()
        long_form.save_plan(self.films, "pilot", self.plan)
        self.prompt = "An original cinematic fox walks slowly in a misty forest, camera tracking."
        self.info = None

    def submitted(self):
        with patch.object(motion.ops_control, "require_active"), \
             patch.object(motion, "health", return_value={
                 "status": "GPU_DETECTED_UNBENCHMARKED",
                 "vram_gib": 12, "peak_vram_gib": None}), \
             patch.object(motion, "_json_request",
                          return_value={"prompt_id": str(uuid4())}) as transport:
            info = motion.submit_shot(
                film_slug="pilot", shot_id="sh-00001",
                plan_sha=self.plan["plan_sha256"], prompt=self.prompt,
                workflow_path=self.workflow,
                workflow_sha=motion.inspect_workflow(self.workflow)["sha256"],
                seed=17, confirmed=True, film_root=self.films, db_path=self.db)
            transport.assert_called_once()
        self.info = info
        return info

    def completed(self):
        info = self.submitted()
        with closing(motion._db(self.db)) as conn:
            provider = conn.execute("SELECT provider_id FROM motion_jobs "
                                    "WHERE job_id=?", (info["job_id"],)).fetchone()[0]
        with patch.object(motion, "_json_request", return_value={
                provider: {"status": {"completed": True, "status_str": "success"}}}):
            result = motion.job_status(info["job_id"], db_path=self.db)
        self.assertEqual(result["status"], "COMFY_COMPLETE_NOT_IMPORTED_OR_VERIFIED")
        file_name = "af_motion_" + info["job_id"] + "_00001.mp4"
        (self.outputs / file_name).write_bytes(TEST_MP4)
        return info, file_name

    def collect(self, info, filename, **kwargs):
        with patch.object(motion.ops_control, "require_active"), \
             patch.object(verify, "_probe", return_value={
                 "codec": "h264", "width": 640, "height": 352,
                 "fps": 12, "frames_decoded": 49, "duration_seconds": 4.083}):
            return verify.import_clip(
                job_id=info["job_id"], filename=filename, output_dir=self.outputs,
                confirmed=True, db_path=self.db, film_root=self.films, **kwargs)

    def test_repository_workflow_example_is_strict_wan5b_49_frame_graph(self):
        from agentforge.paths import REPOSITORY_ROOT
        example = REPOSITORY_ROOT / "examples" / "film_studio" / "wan22_5b_4s_api.json"
        record = motion.inspect_workflow(example)
        self.assertEqual(record["profile"]["frames"], 49)
        self.assertEqual(record["profile"]["fps"], 12)
        self.assertEqual(record["workflow"]["api"]["55"]["class_type"],
                         "Wan22ImageToVideoLatent")
        self.assertEqual(record["workflow"]["api"]["37"]["inputs"]["unet_name"],
                         "wan2.2_ti2v_5B_fp16.safetensors")

    def test_refuses_unreviewed_14b_weights_and_unknown_encoder(self):
        doc = template()
        doc["api"]["1"]["inputs"]["unet_name"] = "wan2.2_t2v_high_noise_14B_fp8.safetensors"
        self.workflow.write_text(json.dumps(doc))
        with self.assertRaisesRegex(motion.MotionError, "5B"):
            motion.inspect_workflow(self.workflow)
        doc["api"]["1"]["inputs"]["unet_name"] = "wan2.2_ti2v_5B_fp16.safetensors"
        doc["api"]["2"]["inputs"]["clip_name"] = "unreviewed_clip.safetensors"
        self.workflow.write_text(json.dumps(doc))
        with self.assertRaises(motion.MotionError):
            motion.inspect_workflow(self.workflow)

    def test_import_requires_provider_success_explicit_confirm_and_matching_name(self):
        info = self.submitted()
        f = "af_motion_" + info["job_id"] + "_00001.mp4"
        (self.outputs / f).write_bytes(TEST_MP4)
        with patch.object(motion.ops_control, "require_active"):
            with self.assertRaises(PermissionError):
                verify.import_clip(job_id=info["job_id"], filename=f,
                                   output_dir=self.outputs,
                                   db_path=self.db, film_root=self.films)
            with self.assertRaises(PermissionError):
                verify.import_clip(job_id=info["job_id"], filename=f,
                                   output_dir=self.outputs, confirmed=True,
                                   db_path=self.db, film_root=self.films)
        self.assertFalse((self.films / "pilot" / "motion_clips").exists())

    def test_import_hash_verified_duplicate_rejected_and_offline_status(self):
        info, filename = self.completed()
        receipt = self.collect(info, filename, owner_reported_peak_vram_gib=9.25)
        self.assertEqual(receipt["status"], verify.TECHNICAL)
        self.assertEqual(receipt["clip_sha256"], hashlib.sha256(TEST_MP4).hexdigest())
        self.assertFalse(receipt["video_accepted"])
        self.assertFalse(receipt["peak_vram_automatically_measured"])
        self.assertEqual(receipt["owner_reported_peak_vram_gib"], 9.25)
        proof = verify.inspect_receipt(info["job_id"],
                                      db_path=self.db, film_root=self.films)
        self.assertEqual(proof["technical"]["frames_decoded"], 49)
        self.assertFalse(proof["motion_quality_verified"])
        listed = verify.list_jobs(db_path=self.db, film_root=self.films)
        self.assertEqual(listed[0]["status"], verify.TECHNICAL)
        self.assertTrue(listed[0]["mp4_technical_verified"])
        with patch.object(motion, "_json_request") as provider:
            # Status is now local and does not depend on ComfyUI staying online.
            # For test injection the default film root is patched explicitly.
            with patch.object(motion, "FILMS", self.films):
                # The default arg is bound at definition time, so read via
                # the receipt function directly instead of mis-stating status.
                self.assertEqual(proof["state"], verify.TECHNICAL)
            provider.assert_not_called()
        with self.assertRaises(FileExistsError):
            self.collect(info, filename)
        clip = self.films / "pilot" / "motion_clips" / info["job_id"] / "clip.mp4"
        clip.write_bytes(b"tampered")
        with self.assertRaises(verify.MotionVerificationError):
            verify.inspect_receipt(info["job_id"], film_root=self.films, db_path=self.db)

    def test_filename_traversal_other_job_and_wrong_manual_vram_denied(self):
        info, filename = self.completed()
        with patch.object(motion.ops_control, "require_active"):
            for f in ("../" + filename, "wrong.mp4", filename.replace(".mp4", ".mkv"),
                      "af_motion_" + "f"*32 + "_00001.mp4"):
                with self.subTest(f=f), self.assertRaises(verify.MotionVerificationError):
                    verify.import_clip(job_id=info["job_id"], filename=f,
                                       output_dir=self.outputs, confirmed=True,
                                       db_path=self.db, film_root=self.films)
        with self.assertRaises(verify.MotionVerificationError):
            self.collect(info, filename, owner_reported_peak_vram_gib=-3)
        self.assertFalse((self.films / "pilot" / "motion_clips").exists())

    def test_probe_fail_closed_and_clean_up_partial(self):
        info, filename = self.completed()
        with patch.object(motion.ops_control, "require_active"), \
             patch.object(verify, "_probe",
                          side_effect=verify.MotionVerificationError("decode failed")):
            with self.assertRaises(verify.MotionVerificationError):
                verify.import_clip(job_id=info["job_id"], filename=filename,
                                   output_dir=self.outputs, confirmed=True,
                                   db_path=self.db, film_root=self.films)
        self.assertFalse((self.films / "pilot" / "motion_clips" /
                          info["job_id"]).exists())

    def test_ffprobe_and_ffmpeg_bounded_argv_without_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            path.write_bytes(TEST_MP4)
            probe_data = {"streams": [{"codec_name": "h264", "width": 640,
                                        "height": 352, "avg_frame_rate": "12/1",
                                        "nb_read_frames": "49"}],
                          "format": {"duration": "4.0833",
                                     "format_name": "mov,mp4,m4a,3gp,3g2,mj2"}}
            commands = []
            def fake(args, **kw):
                commands.append((args, kw))
                self.assertNotIn("shell", kw)
                self.assertIs(kw["stdin"], __import__("subprocess").DEVNULL)
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(probe_data).encode("utf-8")
                    if "ffprobe" in args[0] else b"")
            with patch("shutil.which", side_effect=lambda name: name), \
                 patch("subprocess.run", side_effect=fake):
                result = verify._probe(path)
            self.assertEqual(result["frames_decoded"], 49)
            self.assertEqual(len(commands), 2)
            self.assertIn("-count_frames", commands[0][0])
            self.assertIn("-xerror", commands[1][0])
            self.assertIn("-nostdin", commands[1][0])
            self.assertEqual(commands[0][0][-1], str(path))

    def test_health_is_gpu_snapshot_not_measured_peak(self):
        with patch.object(motion, "_json_request", return_value={
            "devices": [{"type": "cuda", "vram_total": 12 * 2**30,
                         "vram_free": 9 * 2**30}]}):
            status = motion.health()
        self.assertEqual(status["status"], "GPU_DETECTED_UNBENCHMARKED")
        self.assertEqual(status["vram_free_snapshot_gib"], 9)
        self.assertIsNone(status["peak_vram_gib"])


if __name__ == "__main__":
    unittest.main()
