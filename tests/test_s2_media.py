"""S2 local media E2E, integrity, consent and existing S1 policy regression."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
import wave
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from agentforge import media_assets as assets
from agentforge import media_quality as quality
from agentforge import media_render as render
from agentforge import media_pipeline as pipeline
from agentforge import skill_runner, task_history

HAS_MEDIA = (importlib.util.find_spec("PIL") is not None
             and importlib.util.find_spec("imageio_ffmpeg") is not None)


def demo(slug="nem-s2-pilot"):
    return {"slug": slug, "title": "Gợi ý chọn nệm", "scenes": [
        {"headline": "Chọn nệm phù hợp",
         "caption": "Tìm hiểu nhu cầu và không gian ngủ.", "duration_seconds": 3},
        {"headline": "Tư vấn theo nhu cầu",
         "caption": "Cân nhắc kích thước và độ nâng đỡ.", "duration_seconds": 3},
    ]}


@unittest.skipUnless(HAS_MEDIA, "Install S2 extras: pip install -e '.[media]'")
class TestS2Media(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "workspace" / "media"
        self.inputs = self.root / "workspace" / "media_inputs"
        self.db = self.root / "data" / "s1_tasks.sqlite3"
        self.patches = [
            patch.object(assets, "ROOT", self.root),
            patch.object(assets, "OUTPUTS", self.output),
            patch.object(assets, "INPUTS", self.inputs),
            patch.object(task_history, "DEFAULT_DB", self.db),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def build(self, payload=None):
        return assets.make_assets(demo() if payload is None else payload)

    def test_storyboard_prompt_contract_matches_media_validator(self):
        valid = {
            "title": "Video tư vấn nệm ngủ",
            "scenes": [
                {"headline": "Chọn đúng nệm", "caption": "Tìm hiểu nhu cầu sử dụng.",
                 "duration_seconds": 5},
                {"headline": "Liên hệ tư vấn", "caption": "Trao đổi để chọn nệm phù hợp.",
                 "duration_seconds": 5},
            ],
        }
        with patch("agentforge.model.generate_json", return_value=valid) as generate:
            result = pipeline.suggest_copy("Tạo video nệm: " + "x" * 1500,
                                           "Khách hàng", "Lập kịch bản")
        self.assertEqual(result["title"], valid["title"])
        self.assertEqual(result["status"], "DRAFT_NOT_VERIFIED")
        schema = generate.call_args.args[1]
        self.assertEqual(schema["properties"]["title"]["maxLength"], 88)
        scene = schema["properties"]["scenes"]["items"]
        self.assertFalse(scene["additionalProperties"])
        self.assertEqual(scene["properties"]["headline"]["maxLength"], 68)
        self.assertEqual(scene["properties"]["caption"]["maxLength"], 180)
        self.assertEqual(scene["properties"]["duration_seconds"]["maximum"], 8)
        self.assertIn("TOTAL duration", generate.call_args.args[0])
        for changed, field in [
            ({**valid, "title": "x" * 89}, "title"),
            ({**valid, "scenes": [dict(valid["scenes"][0], duration_seconds=9),
                                  valid["scenes"][1]]}, "scenes"),
            ({**valid, "scenes": [dict(valid["scenes"][0], caption="x" * 181),
                                  valid["scenes"][1]]}, "scenes"),
            ({**valid, "extra": "untrusted"}, "fields"),
        ]:
            with self.subTest(field=field), patch("agentforge.model.generate_json",
                                                  return_value=changed):
                with self.assertRaises(assets.MediaError) as raised:
                    pipeline.suggest_copy("Viết nội dung video", "Khách hàng",
                                          "Lập kịch bản")
                self.assertEqual(str(raised.exception),
                                 "STORYBOARD_SCHEMA_INVALID: " + field)

    def test_storyboard_diagnostics_redact_untrusted_response(self):
        secret = "private-model-response-or-api-key"
        cases = [
            (assets.MediaError("STORYBOARD_SCHEMA_INVALID: title"),
             "STORYBOARD_SCHEMA_INVALID"),
            (assets.MediaError("STORYBOARD_SCHEMA_INVALID: " + secret),
             "STORYBOARD_VALIDATION_FAILED"),
            (assets.MediaError("STORYBOARD_INPUT_INVALID: topic"),
             "STORYBOARD_INPUT_INVALID"),
            (RuntimeError("Gateway response stopped at max_tokens (" + secret + ")"),
             "STORYBOARD_OUTPUT_LIMIT"),
            (json.JSONDecodeError(secret, "{", 0),
             "STORYBOARD_MODEL_JSON_INVALID"),
            (RuntimeError(secret), "STORYBOARD_MODEL_RUNTIME_FAILED"),
        ]
        for error, code in cases:
            with self.subTest(code=code):
                message = skill_runner._safe_failure("media.copy_draft", error)
                self.assertTrue(message.startswith(code + ":"), message)
                self.assertNotIn(secret, message)

    def test_original_png_wav_srt_and_quality(self):
        receipt = self.build()
        self.assertFalse(receipt["video_rendered"])
        self.assertEqual(receipt["duration_seconds"], 6)
        path = self.output / receipt["run_id"]
        from PIL import Image
        with Image.open(path / "scene_01.png") as frame:
            self.assertEqual(frame.size, assets.SIZE)
            self.assertEqual(frame.format, "PNG")
        with wave.open(str(path / "ambient.wav"), "rb") as song:
            self.assertEqual(song.getframerate(), 16000)
            self.assertEqual(song.getnframes(), 6 * 16000)
        captions = (path / "captions.srt").read_text(encoding="utf-8")
        self.assertIn("00:00:00,000 --> 00:00:03,000", captions)
        self.assertIn("00:00:03,000 --> 00:00:06,000", captions)
        self.assertIn("Cân nhắc kích thước", captions)
        result = quality.check(receipt["run_id"])
        self.assertEqual(result["status"], "ASSETS_PASS")
        self.assertEqual(result["failures"], 0)
        self.assertFalse(result["video_verified"])

    def test_validates_deep_story_and_prevents_side_effects(self):
        for bad in [
            {**demo(), "slug": "../outside"},
            {**demo(), "scenes": []},
            {**demo(), "scenes": [{**demo()["scenes"][0], "duration_seconds": True},
                                  demo()["scenes"][1]]},
            {**demo(), "title": "\x00"},
            {**demo(), "price": "invented"},
        ]:
            with self.subTest(bad=repr(bad)[:60]):
                with self.assertRaises((assets.MediaError, ValueError)):
                    assets.make_assets(bad)
        self.assertFalse(self.output.exists())

    def test_owner_photo_requires_attestation_and_flat_path(self):
        from PIL import Image
        self.inputs.mkdir(parents=True)
        Image.new("RGB", (640, 480), (200, 180, 160)).save(self.inputs / "my-photo.jpg")
        p = {**demo(), "photo_name": "my-photo.jpg"}
        with self.assertRaises(PermissionError):
            self.build(p)
        with self.assertRaises(assets.MediaError):
            self.build({**p, "rights_confirmed": True, "photo_name": "../bad.jpg"})
        result = self.build({**p, "rights_confirmed": True})
        report = quality.check(result["run_id"])
        self.assertEqual(report["status"], "ASSETS_PASS")
        self.assertEqual(report["warnings"], 1)
        self.assertEqual(report["findings"][0]["rule"], "photo_rights")

    def test_studio_video_uses_two_verified_independent_shot_images(self):
        import hashlib
        import io
        from PIL import Image
        ids = ["a"*32, "b"*32]
        originals = []
        for color in [(225, 155, 128), (76, 145, 195)]:
            buffer = io.BytesIO()
            Image.new("RGB", (768, 512), color).save(buffer, format="PNG")
            originals.append(buffer.getvalue())
        plan = {"mode": "studio", "motion": "slow_zoom", "image_job_ids": ids}
        def image_for_job(job_id):
            return originals[ids.index(job_id)], "image/png"
        with patch("agentforge.asset_preview.image_for_job", side_effect=image_for_job) as review:
            receipt = self.build({**demo(), "visual_plan": plan})
            self.assertEqual(review.call_count, 2)
        folder, manifest = assets.load_manifest(receipt["run_id"])
        self.assertEqual(manifest["visual_plan"], plan)
        self.assertEqual([x["sha256"] for x in manifest["studio_image_receipts"]],
                         [hashlib.sha256(x).hexdigest() for x in originals])
        self.assertNotEqual(assets._sha(folder/"scene_01.png"),
                            assets._sha(folder/"scene_02.png"))
        self.assertEqual(quality.check(receipt["run_id"])["status"], "ASSETS_PASS")
        movie = render.render_video(receipt["run_id"], confirm_external_run=True)
        self.assertEqual(movie["status"], "VIDEO_RENDERED")
        self.assertEqual(quality.check(receipt["run_id"])["status"], "VIDEO_PASS")

    def test_studio_plan_invalid_before_any_media_is_written(self):
        for plan in [
            {"mode":"studio","motion":"slow_zoom","image_job_ids":[]},
            {"mode":"studio","motion":"slow_zoom","image_job_ids":["a"*32,"a"*32]},
            {"mode":"studio","motion":"zoom-fast","image_job_ids":["a"*32,"b"*32]},
            {"mode":"classic","motion":"static","image_job_ids":["a"*32]},
            {"mode":"studio","motion":"slow_pan","image_job_ids":["../bad","b"*32]},
            {"mode":"studio","motion":"slow_zoom","image_job_ids":["a"*32,"b"*32],"custom_node":"unsafe"},
        ]:
            with self.subTest(plan=plan):
                with self.assertRaises(assets.MediaError):
                    self.build({**demo(), "visual_plan": plan})
        self.assertFalse(self.output.exists())

    def test_studio_source_provenance_fails_if_manifest_is_modified(self):
        from PIL import Image
        import io
        image=io.BytesIO()
        Image.new("RGB",(512,512),"navy").save(image,format="PNG")
        with patch("agentforge.asset_preview.image_for_job",
                   return_value=(image.getvalue(),"image/png")):
            # Distinct IDs are checked by validated job refs, not image bytes.
            result=self.build({**demo(),"visual_plan":{
                "mode":"studio","motion":"slow_pan",
                "image_job_ids":["a"*32,"b"*32]}})
        folder,manifest=assets.load_manifest(result["run_id"])
        manifest["studio_image_receipts"][0]["sha256"]="not-a-sha"
        (folder/"manifest.json").write_text(
            json.dumps(manifest,ensure_ascii=False),encoding="utf-8")
        report=quality.check(result["run_id"])
        self.assertEqual(report["status"],"FAIL")
        self.assertIn("manifest",[f["rule"] for f in report["findings"]])

    def test_non_destructive_image_edit(self):
        generated = self.build()
        folder = self.output / generated["run_id"]
        before = (folder / "scene_01.png").read_bytes()
        edited = quality.edit_image(generated["run_id"], 1, "warm")
        self.assertEqual(edited["status"], "EDIT_CREATED")
        self.assertNotEqual(Path(edited["image_path"]).read_bytes(), before)
        self.assertEqual((folder / "scene_01.png").read_bytes(), before)
        self.assertEqual(quality.check(generated["run_id"])["status"], "ASSETS_PASS")
        with self.assertRaises(assets.MediaError):
            quality.edit_image(generated["run_id"], 9, "warm")

    def test_integrity_refuses_modified_caption_or_image(self):
        result = self.build()
        folder = self.output / result["run_id"]
        (folder / "captions.srt").write_text("BAD", encoding="utf-8")
        report = quality.check(result["run_id"])
        self.assertEqual(report["status"], "FAIL")
        self.assertGreater(report["failures"], 0)
        with self.assertRaises(assets.MediaError):
            render.render_video(result["run_id"], confirm_external_run=True)
        self.assertFalse((folder / "video.mp4").exists())

    def test_srt_timing_mismatch_cannot_pass_even_with_updated_checksum(self):
        result = self.build()
        folder, manifest = assets.load_manifest(result["run_id"])
        file = folder / "captions.srt"
        source = file.read_text(encoding="utf-8")
        file.write_text(source.replace("00:00:03,000", "00:00:04,000", 1),
                        encoding="utf-8")
        manifest["artifacts"]["captions.srt"] = assets._sha(file)
        (folder / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        report = quality.check(result["run_id"])
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("media_decode", [x["rule"] for x in report["findings"]])

    def test_video_consent_blocks_external_tool_and_no_overwrite(self):
        receipt = self.build()
        with patch.object(render, "_run_process") as process:
            with self.assertRaises(PermissionError):
                render.render_video(receipt["run_id"])
            process.assert_not_called()
        self.assertFalse((self.output / receipt["run_id"] / "video.mp4").exists())

    def test_real_mp4_production_and_decode(self):
        receipt = self.build()
        result = render.render_video(receipt["run_id"], confirm_external_run=True)
        self.assertEqual(result["status"], "VIDEO_RENDERED")
        self.assertEqual(result["quality_status"], "VIDEO_PASS")
        video = Path(result["video_path"])
        self.assertGreater(video.stat().st_size, 9000)
        self.assertEqual(quality.check(receipt["run_id"])["status"], "VIDEO_PASS")
        self.assertEqual(quality.check(receipt["run_id"])["failures"], 0)
        with self.assertRaises(FileExistsError):
            render.render_video(receipt["run_id"], confirm_external_run=True)
        self.assertEqual(assets.load_manifest(receipt["run_id"])[1]["published"], False)

    def test_task_history_integration_and_policy_gates(self):
        payload = demo()
        with patch("agentforge.model.generate_json") as model:
            out = skill_runner.invoke("media.compose", payload, db_path=self.db)
            model.assert_not_called()
        self.assertEqual(out["status"], "WAITING_APPROVAL")
        self.assertIn("workspace.write", out["missing"])
        ready = skill_runner.resume_waiting(
            out["task_id"], grants=("workspace.write",), db_path=self.db)
        self.assertEqual(ready["status"], "SUCCEEDED")
        run_id = ready["result"]["run_id"]
        with patch.object(render, "render_video") as encoder:
            pending = skill_runner.invoke(
                "media.video_render", {"run_id": run_id, "confirm_external_run": False},
                grants=("workspace.write", "process.run"),
                confirm_external_run=True, db_path=self.db)
            self.assertEqual(pending["status"], "WAITING_APPROVAL")
            self.assertIn("input.confirm_external_run", pending["missing"])
            encoder.assert_not_called()
        with patch.object(render, "render_video", return_value={
            "run_id": run_id, "status": "VIDEO_RENDERED",
            "video_path": "local.mp4", "quality_status": "VIDEO_PASS",
        }) as encoder:
            passed = skill_runner.invoke(
                "media.video_render", {"run_id": run_id, "confirm_external_run": True},
                grants=("workspace.write", "process.run"),
                confirm_external_run=True, db_path=self.db)
            encoder.assert_called_once_with(run_id, confirm_external_run=True)
        self.assertEqual(passed["status"], "SUCCEEDED")
        events = task_history.get_task(passed["task_id"], db_path=self.db)["events"]
        self.assertIn("POLICY_GRANTED", [e["name"] for e in events])
        self.assertEqual(len(task_history.list_tasks(db_path=self.db)), 3)

    def test_draft_requires_model_approval_and_owner_review(self):
        data = {"topic": "Tư vấn chọn nệm", "audience": "Khách hàng mới",
                "goal": "Khuyến khích trao đổi nhu cầu"}
        with patch("agentforge.model.generate_json") as model:
            pending = skill_runner.invoke("media.copy_draft", data, db_path=self.db)
            model.assert_not_called()
        with patch("agentforge.model.generate_json", return_value={
            "title": "Tư vấn nệm",
            "scenes": demo()["scenes"],
        }) as model:
            ok = skill_runner.resume_waiting(
                pending["task_id"], grants=("model.invoke", "workspace.propose"),
                confirm_model_call=True, db_path=self.db)
            self.assertEqual(model.call_args.kwargs["worker_id"], "media_producer")
        self.assertEqual(ok["status"], "SUCCEEDED")
        self.assertTrue(ok["result"]["review_required"])
        self.assertFalse(ok["result"]["verified_claims"])
        self.assertEqual(len([x for x in self.output.glob("*") if x.is_dir()]), 0)

    def test_tts_never_executes_without_approval_and_voice_is_verified(self):
        receipt = self.build()
        with patch.object(render, "_run_process") as process:
            with self.assertRaises(PermissionError):
                render.make_voiceover(receipt["run_id"], "windows")
            process.assert_not_called()
        def fake_voice_command(engine, folder, voice):
            return ["dummy", "voice"], None
        def fake_tts(cmd, *, cwd, timeout=180, input_text=None):
            with wave.open(str(cwd / "voiceover.partial.wav"), "wb") as sound:
                sound.setnchannels(1)
                sound.setsampwidth(2)
                sound.setframerate(16000)
                sound.writeframes(b"\x00\x00" * 16000)
        with patch.object(render, "_voice_command", side_effect=fake_voice_command):
            with patch.object(render, "_run_process", side_effect=fake_tts) as process:
                done = render.make_voiceover(
                    receipt["run_id"], "windows", confirm_external_run=True)
                process.assert_called_once()
        self.assertEqual(done["status"], "VOICEOVER_CREATED")
        self.assertEqual(quality.check(receipt["run_id"])["status"], "ASSETS_PASS")
        self.assertTrue((self.output / receipt["run_id"] / "voiceover.wav").is_file())

    def test_cli_quality_fail_is_not_a_false_success(self):
        receipt = self.build()
        bad_report = {"run_id": receipt["run_id"], "status": "FAIL",
                      "failures": 1, "warnings": 0,
                      "findings": [{"rule": "artifact_integrity",
                                    "severity": "FAIL", "message": "mismatch"}]}
        with patch("agentforge.media_quality.check", return_value=bad_report):
            with patch("sys.argv", ["media_pipeline", "check", receipt["run_id"]]):
                with redirect_stdout(StringIO()) as stdout:
                    with self.assertRaises(SystemExit) as exit_call:
                        pipeline.main()
        self.assertEqual(exit_call.exception.code, 2)
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["result"]["status"], "FAIL")

    def test_cli_single_command_produces_real_video_with_task_history(self):
        args = ["media_pipeline", "demo", "nem-s2-cli",
                "--render-video", "--confirm-media-run"]
        with patch("sys.argv", args), redirect_stdout(StringIO()) as stdout:
            pipeline.main()
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["assets"]["status"], "SUCCEEDED")
        self.assertEqual(result["video"]["status"], "SUCCEEDED")
        self.assertTrue(Path(result["video"]["result"]["video_path"]).is_file())
        self.assertEqual(quality.check(result["assets"]["result"]["run_id"])["status"],
                         "VIDEO_PASS")
        self.assertEqual(len(task_history.list_tasks(db_path=self.db)), 2)


if __name__ == "__main__":
    unittest.main()
