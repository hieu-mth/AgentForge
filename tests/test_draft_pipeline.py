"""Draft schema, checkpoint lifecycle, and real local MP4 quality gate."""
import tempfile
import io
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext

from agentforge.features.film_studio import draft_pipeline as draft


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
        profile = {"flux": {"max_resolution": 768}}
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, {"image.generate": profile})),
              patch.object(draft.flux_runtime, "generate", return_value={"status": "OUTPUT_MISSING"}) as generate):
            draft._work(job, nullcontext())
            self.assertEqual(job["status"], "FAILED")
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
            self.assertEqual(draft.submit({"id": self.ident, **self.brief})["status"], "QUEUED")
            self.assertEqual(draft.submit({"id": self.ident, **self.brief})["id"], self.ident)
            with self.assertRaisesRegex(ValueError, "queue"):
                draft.submit({"id": "b" * 32, **self.brief})
            self.assertEqual(draft.act(self.ident, "cancel", {})["status"], "CANCELLED")
            self.assertEqual(draft.submit({"id": "b" * 32, **self.brief})["status"], "QUEUED")

    def test_running_cancel_keeps_committed_scene_and_skips_render(self):
        job = {"id": self.ident, "brief": self.brief, "status": "RUNNING", "stage": "IMAGES",
               "board": draft._story(self.board(), 2, 6, {"cat": {}}), "cast": {}}
        draft._save(job)

        def complete_scene(job, index, scene, revision, profile):
            scene["asset"] = "committed"
            draft._save(job)
            draft._cancellation(job["id"], mark=True)

        profile = {"base_url": "http://127.0.0.1:8188"}
        with (patch.object(draft.model_hub, "draft_routes", return_value=(1, {"image.generate": profile})),
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
