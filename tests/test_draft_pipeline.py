"""Draft schema, checkpoint lifecycle, and real local MP4 quality gate."""
import tempfile
import io
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext

from agentforge.features.film_studio import draft_pipeline as draft
from tests import owner_http_fixture


class DraftTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, value in (("DB", self.root / "drafts.sqlite3"), ("WORKSPACE_DIR", self.root)):
            override = patch.object(draft, name, value)
            override.start()
            self.addCleanup(override.stop)
        self.ident = "a" * 32
        self.brief = {"idea": "Chú mèo cam", "scene_count": 2, "ratio": "16:9", "seconds": 6}
        self.capacity = {"ram_available": 16 << 30, "commit_used": 8 << 30,
                         "commit_limit": 32 << 30, "vram_free_mib": 8000}
        capacity = patch.object(draft.draft_resources, "snapshot", return_value=self.capacity)
        capacity.start()
        self.addCleanup(capacity.stop)

    def board(self):
        scene = {"description": "Mèo ngắm rừng", "image_prompt": "Cat in a forest",
                 "character_ids": ["cat"], "audio": "Im lặng"}
        return {"title": "Mèo", "continuity": "Orange cat, morning", "scenes": [scene, scene]}

    def test_script_ranges_keep_exact_text_and_reject_insufficient_capacity(self):
        self.assertFalse(draft._needs_scene_analysis("Một chú mèo đi tìm bạn."))
        text = "Cảnh 1 — Miu nhìn ra cửa sổ 🐱\nMiu: Chào bạn!\n\nCảnh 2 — Miu chạy ra vườn."
        self.assertTrue(draft._needs_scene_analysis(text))
        ranges = draft._script_ranges(text, 2, 12)
        self.assertEqual("".join(text[start:end] for start,end in ranges), text)
        self.assertTrue(text[ranges[1][0]:].startswith("Cảnh 2"))
        with self.assertRaisesRegex(ValueError, "3 cảnh"):
            draft._script_ranges(text+"\nCảnh 3 — Trời tối.", 2, 12)
        with self.assertRaisesRegex(ValueError, "Thời lượng"):
            draft._script_ranges(text+"\nMiu: "+"chào "*50, 2, 6)

    def test_long_script_analysis_uses_bounded_excerpts_before_storyboard(self):
        source = "Cảnh 1 — Miu\n" + "Miu nhìn ra cửa sổ. 🐱\n" * 140 + "\nCảnh 2 — Miu chạy ra vườn."
        job = {"id": self.ident, "status": "RUNNING", "brief":{
            **self.brief, "idea": source}}
        provider = {"provider":"ollama", "model":"fixture"}
        excerpts = []
        def respond(profile, instructions, data, schema, comfy):
            if "excerpt" in data:
                excerpts.append(data["excerpt"])
                self.assertLessEqual(len(data["excerpt"]), 900)
                return {"facts": "Miu chờ bên cửa sổ."}
            self.assertLess(len(str(data)), len(source))
            return {"title":"Miu", "continuity":"Orange cat", "description":"Miu đợi",
                    "image_prompt":"Orange cat by a window", "audio":"Yên tĩnh"}
        with (patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", side_effect=respond)):
            draft._write_board(job, {"film.storyboard":provider, "image.generate":{}})
        board = draft._read(self.ident)["board"]
        self.assertEqual(len(board["scenes"]), 2)
        self.assertEqual("".join(excerpts), source[:board["scenes"][1]["script_range"][0]])
        self.assertEqual("".join(source[start:end] for start,end in
                                 (scene["script_range"] for scene in board["scenes"])), source)

    def test_long_vietnamese_script_http_sqlite_roundtrip_and_limit(self):
        client = owner_http_fixture.OwnerHttpFixture()
        client.setUp()
        self.addCleanup(client.doCleanups)
        client.server.allow_external_actions = True
        client.login()
        prefix = "Cảnh 1 — Miu nhìn ra cửa sổ.\nMiu: Chào bạn!\n"
        suffix = "\n\nCảnh 2 — Miu chạy ra vườn.\n"
        source = prefix + "🐱" * (20_000 - len(prefix) - len(suffix)) + suffix
        body = {**self.brief, "id":self.ident, "idea":source}
        with (patch.object(draft.model_hub, "draft_routes"), patch.object(draft.render, "_ffmpeg"),
              patch.object(draft, "_dispatch")):
            status, result, _ = client.req("POST", "/api/film/drafts/start", body)
            self.assertEqual(status, 200, result.get("message"))
            self.assertEqual(result["brief"]["idea"], source)
            status, result, _ = client.req("GET", "/api/film/drafts")
            self.assertEqual(status, 200)
            self.assertEqual(result["drafts"][0]["brief"]["idea"], source)
            status, error, _ = client.req("POST", "/api/film/drafts/start",
                                         {**body, "idea":source+"đ"})
            self.assertEqual(status, 400)
            self.assertIn("20,000", error["message"])

    def test_submission_validation_and_idempotence(self):
        with self.assertRaises(ValueError):
            draft.submit({"id": self.ident, **self.brief, "ratio": "4:3"})
        draft._save({"id": self.ident, "brief": self.brief, "status": "RUNNING"})
        self.assertEqual(draft.submit({"id": self.ident, **self.brief})["id"], self.ident)
        with self.assertRaises(ValueError):
            draft.submit({"id": self.ident, **self.brief, "idea": "Khác"})
        self.assertEqual(len(draft.list_drafts()), 1)

    def test_storyboard_rejects_unknown_cast_and_distributes_exact_duration(self):
        with self.assertRaisesRegex(ValueError, "unknown character"):
            draft._story(self.board(), 2, 7, {})
        result = draft._story(self.board(), 2, 7, {"cat": {}})
        self.assertEqual([scene["seconds"] for scene in result["scenes"]], [4, 3])

    def test_resume_reuses_previous_asset_and_generates_only_failed_scene(self):
        job = {"id": self.ident, "brief": self.brief, "status": "RUNNING", "stage": "IMAGES",
               "board": draft._story(self.board(), 2, 6, {"cat": {}}),
               "cast": {"cat": {"name": "Mèo", "appearance": "Lông cam"}}}
        folder = draft._folder(self.ident)
        folder.mkdir(parents=True)
        known = b"previously verified scene image"
        (folder / "scene-01.png").write_bytes(known)
        job["board"]["scenes"][0]["asset"] = draft._sha(known)
        draft._save(job)
        profile = {"provider": "comfyui", "model": "fixture.gguf", "flux": {"max_resolution": 768}}
        def missing_output(*args, **kwargs):
            self.assertEqual(draft._read(self.ident)["activity"], {
                "operation": "image", "provider": "comfyui", "model": "fixture.gguf", "scene": 2,
            })
            return {"status": "COMFYUI_STOPPED"}
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, {"image.generate": profile})),
              patch.object(draft.flux_runtime, "generate", side_effect=missing_output) as generate):
            draft._work(job, nullcontext())
            self.assertEqual(job["status"], "FAILED")
            self.assertEqual(job["error"], "ComfyUI scene result: COMFYUI_STOPPED")
            self.assertNotIn("activity", job)
            self.assertEqual(job["board"]["scenes"][1]["attempts"], 1)
            generate.assert_called_once()
        recovered = draft._read(self.ident)
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, {"image.generate": profile})),
              patch.object(draft.visual_jobs, "_row", side_effect=KeyError),
              patch.object(draft.flux_runtime, "generate", return_value={"status": "ASSET_READY"}) as generate,
              patch.object(draft.visual_jobs, "open_image_for_job",
                           return_value=nullcontext((io.BytesIO(b"new asset"), draft._sha(b"new asset")))),
              patch.object(draft, "_render", return_value="verified")):
            draft._work(recovered, nullcontext())
            generate.assert_called_once()
            self.assertIn("Lông cam", generate.call_args.args[0])
            self.assertTrue(generate.call_args.kwargs["scene"].endswith("/scene-02"))
        self.assertEqual((folder / "scene-01.png").read_bytes(), known)
        self.assertEqual(draft._read(self.ident)["status"], "REVIEW")

    def test_launcher_error_before_submission_keeps_scene_retry_budget(self):
        job = {"id": self.ident, "brief": self.brief,
               "board": draft._story(self.board(), 2, 6, {"cat": {}}),
               "cast": {"cat": {"name": "Miu", "appearance": "orange cat"}}}
        scene = job["board"]["scenes"][0]
        profile = {"flux": {"max_resolution": 768}}
        for error in ("COMFYUI_LAUNCHER_REQUIRED", "COMFYUI_ENDPOINT_MISMATCH"):
            with (self.subTest(error=error),
                  patch.object(draft.flux_runtime, "generate",
                               side_effect=draft.comfy_service.StartupError(error))):
                with self.assertRaisesRegex(draft.comfy_service.StartupError, error):
                    draft._image(job, 0, scene, 1, profile)
            self.assertEqual(scene["attempts"], 0)
            self.assertIsNone(scene["job_id"])

    def test_job_waits_on_ram_and_vram_and_preserves_scene_checkpoint(self):
        job = {"id": self.ident, "brief": self.brief, "status": "RUNNING", "stage": "IMAGES",
               "board": draft._story(self.board(), 2, 6, {"cat": {}}), "cast": {}}
        draft._save(job)
        with (patch.object(draft.model_hub, "draft_routes", return_value=(1, {"image.generate": {}})),
              patch.object(draft, "_image") as image):
            for field, reason in (("ram_available", "RAM_LOW"), ("vram_free_mib", "VRAM_LOW")):
                with self.subTest(reason=reason), patch.dict(self.capacity, {field: 1}):
                    draft._work(job, nullcontext())
                    self.assertEqual(draft._read(self.ident)["status"], "WAITING_RESOURCES")
                    self.assertEqual(draft._read(self.ident)["error"], reason)
            image.assert_not_called()
        self.assertTrue(all(scene["attempts"] == 0 for scene in job["board"]["scenes"]))

    def test_queue_limit_idempotence_and_queued_cancel(self):
        with (patch.object(draft.model_hub, "draft_routes"), patch.object(draft.render, "_ffmpeg"),
              patch.object(draft, "_queue_limit", return_value=1), patch.object(draft, "_dispatch")):
            submitted = draft.submit({"id": self.ident, **self.brief})
            self.assertEqual(submitted["status"], "QUEUED")
            self.assertEqual(submitted["created_at"], submitted["updated_at"])
            self.assertEqual(draft.submit({"id": self.ident, **self.brief})["id"], self.ident)
            with self.assertRaisesRegex(ValueError, "queue"):
                draft.submit({"id": "b" * 32, **self.brief})
            cancelled = draft.act(self.ident, "cancel", {})
            self.assertEqual(cancelled["status"], "CANCELLED")
            self.assertEqual(draft._read(self.ident)["created_at"], submitted["created_at"])
            self.assertEqual(draft.submit({"id": "b" * 32, **self.brief})["status"], "QUEUED")

    def test_running_cancel_keeps_committed_scene_and_skips_render(self):
        job = {"id": self.ident, "brief": self.brief, "status": "RUNNING", "stage": "IMAGES",
               "board": draft._story(self.board(), 2, 6, {"cat": {}}), "cast": {}}
        draft._save(job)

        def complete_scene(job, index, scene, revision, profile):
            scene["asset"] = "committed"
            draft._save(job)
            draft._cancellation(job["id"], mark=True)

        profile = {"base_url": "http://127.0.0.1:8188", "provider": "comfyui", "model": "fixture.gguf"}
        with (patch.object(draft.model_hub, "draft_routes", return_value=(1, {"image.generate": profile})),
              patch.object(draft.comfy_service, "require_other_queue_idle"),
              patch.object(draft.comfy_service, "require_idle_queue"),
              patch.object(draft, "_image", side_effect=complete_scene) as image,
              patch.object(draft, "_render") as render,
              patch.object(draft, "_release_idle_comfy") as release):
            draft._work(job, nullcontext())
            image.assert_called_once()
            render.assert_not_called()
            release.assert_called_once_with(profile)
        restored = draft._read(self.ident)
        self.assertEqual(restored["status"], "CANCELLED")
        self.assertEqual(restored["board"]["scenes"][0]["asset"], "committed")

    def test_comfy_offload_skipped_during_commit_pressure(self):
        with (patch.dict(self.capacity, {"commit_used": 31 << 30}),
              patch.object(draft.flux_runtime, "_json") as request):
            self.assertFalse(draft._release_idle_comfy({"base_url": "http://127.0.0.1:8188"}))
            request.assert_not_called()

    def test_ollama_500_does_not_retry(self):
        profile = {"id": "fixture", "model": "fixture", "base_url": "http://127.0.0.1:11434"}
        with (patch.object(draft.runtime, "_installed_local_model", return_value=True),
              patch.object(draft.runtime, "_http_json",
                           side_effect=draft.runtime.LocalProviderHTTPError(500)) as request,
              self.assertRaisesRegex(draft.ResourceWait, "OLLAMA_RESOURCE_OR_SERVER_ERROR")):
            draft._ask(profile, "Plan", {}, {}, {})
        request.assert_called_once()

    def test_local_render_integrity_and_review_checkpoint(self):
        try:
            from PIL import Image
            draft.render._ffmpeg()
        except (ImportError, RuntimeError):
            self.skipTest("Media extra unavailable")
        for ratio in ("16:9", "9:16"):
            with self.subTest(ratio=ratio):
                job = {"id": self.ident, "brief": {**self.brief, "ratio": ratio}, "status": "REVIEW",
                       "board": draft._story(self.board(), 2, 6, {"cat": {}})}
                folder = draft._folder(self.ident)
                folder.mkdir(parents=True, exist_ok=True)
                for i, scene in enumerate(job["board"]["scenes"], start=1):
                    path = folder / f"scene-{i:02d}.png"
                    Image.new("RGB", (256, 256), (150, i * 50, 80)).save(path)
                    scene["asset"] = draft._sha(path.read_bytes())
                job["video_sha"] = draft._render(job)
                draft._save(job)
                with self.assertRaisesRegex(ValueError, "current draft"):
                    draft.act(self.ident, "approve", {"sha256": "wrong"})
                edited = draft.act(self.ident, "edit", {
                    "index": 1, "description": "Sửa", "image_prompt": "New scene"})
                self.assertEqual(edited["board"]["scenes"][0]["asset"], job["board"]["scenes"][0]["asset"])
                self.assertIsNone(edited["board"]["scenes"][1]["asset"])
                self.assertIsNone(edited["video_sha"])
                draft._save(job)
                result = draft.act(self.ident, "approve", {"sha256": job["video_sha"]})
                self.assertEqual(result["status"], "APPROVED")
