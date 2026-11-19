"""Draft schema, checkpoint lifecycle, and real local MP4 quality gate."""
import tempfile
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
              patch.object(draft.visual_jobs, "image_for_job", return_value=(b"new asset", "image/png")),
              patch.object(draft, "_render", return_value="verified")):
            draft._work(recovered, nullcontext())
            generate.assert_called_once()
            self.assertIn("Lông cam", generate.call_args.args[0])
            self.assertTrue(generate.call_args.kwargs["scene"].endswith("/scene-02"))
        self.assertEqual((folder / "scene-01.png").read_bytes(), known)
        self.assertEqual(draft._read(self.ident)["status"], "REVIEW")

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
