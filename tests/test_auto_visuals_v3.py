"""Offline V3 auto visual jobs and Owner-gated storyboard requests."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from agentforge.features.media import visual_jobs
from agentforge.api.routes import media as media_routes
from agentforge import quality_v14

STORY = {
    "title": "Video quảng cáo nệm ngủ",
    "scenes": [
        {"headline": "Phòng ngủ có nệm", "caption": "Giường với nệm trắng",
         "duration_seconds": 5},
        {"headline": "Cận cảnh nệm", "caption": "Bề mặt vải mềm mại",
         "duration_seconds": 5},
    ],
    "status": "DRAFT_NOT_VERIFIED",
    "review_required": True,
    "verified_claims": False,
}


class AutoVisualV3Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "visuals.sqlite3"
        self.files = Path(temp.name) / "images"
        self.checkpoint = "commercial.safetensors"
        self.recorded = []

    def submit(self, purpose="video", source_sha=None):
        def dispatch(route, **kwargs):
            self.assertEqual(route, "/prompt")
            self.recorded.append(kwargs["payload"])
            return json.dumps({"prompt_id": str(uuid4())}).encode()
        with patch("agentforge.ops_control.require_active"), \
             patch("agentforge.features.websites.image_studio.health",
                   return_value={"status": "READY", "checkpoints": [self.checkpoint]}), \
             patch("agentforge.features.websites.image_studio._request",
                   side_effect=dispatch):
            return visual_jobs.submit(
                purpose, "Quảng cáo nệm ngủ", ["Phòng ngủ sáng sớm", "Cận cảnh nệm"],
                self.checkpoint, confirm_generation=True,
                source_sha=source_sha, db_path=self.db)

    def test_two_shots_use_trusted_model_graph_and_persist_source_sha(self):
        sha = "a"*64
        with patch("agentforge.ops_control.require_active"):
            with self.assertRaises(PermissionError):
                visual_jobs.submit("video", "nệm", ["cảnh"], self.checkpoint,
                                   db_path=self.db)
        self.assertFalse(self.db.exists())
        result = self.submit(source_sha=sha)
        self.assertEqual(result["gpu_jobs_submitted"], 2)
        self.assertEqual(len(self.recorded), 2)
        for call in self.recorded:
            graph = call["prompt"]
            self.assertEqual(graph["1"]["class_type"], "CheckpointLoaderSimple")
            self.assertIn("nệm", graph["2"]["inputs"]["text"])
            self.assertIn("No text", graph["2"]["inputs"]["text"])
        report = visual_jobs.report(db_path=self.db)
        self.assertEqual(len(report["jobs"]), 2)
        self.assertTrue(all(x["source_sha"] == sha for x in report["jobs"]))
        self.assertTrue(all(x["status"] == "SUBMITTED" for x in report["jobs"]))

    def test_successful_collection_has_png_and_sha_provenance(self):
        from PIL import Image
        result = self.submit()
        job_id = result["job_ids"][0]
        record = visual_jobs._row(job_id, db_path=self.db)
        content = io.BytesIO()
        Image.new("RGB", (768, 512), (220, 170, 140)).save(content, format="PNG")
        def fake_request(path, **kwargs):
            if path.startswith("/history/"):
                return json.dumps({record["provider_id"]: {
                    "status": {"status_str": "success", "completed": True},
                    "outputs": {"7": {"images": [{
                        "filename": "af_" + job_id + "_00001_.png",
                        "subfolder": "", "type": "output",
                    }]}}
                }}).encode()
            if path.startswith("/view?"):
                return content.getvalue()
            raise AssertionError(path)
        with patch("agentforge.ops_control.require_active"), \
             patch("agentforge.features.websites.image_studio._request",
                   side_effect=fake_request):
            imported = visual_jobs.collect(job_id, confirm_import=True,
                db_path=self.db, output_root=self.files)
        self.assertEqual(imported["status"], "ASSET_READY")
        bytes_out, mime = visual_jobs.image_for_job(
            job_id, db_path=self.db, output_root=self.files)
        self.assertEqual(bytes_out, content.getvalue())
        self.assertEqual(mime, "image/png")
        (self.files / (job_id + ".png")).write_bytes(b"tampered")
        with self.assertRaises(PermissionError):
            visual_jobs.image_for_job(job_id, db_path=self.db,
                                      output_root=self.files)

    def test_website_subject_and_attachment_use_source_sha(self):
        import hashlib
        from PIL import Image
        from agentforge import image_studio_v24, web_assets
        temp = self.db.parent
        site = temp / "my-site"
        site.mkdir()
        html = ('<!doctype html><html><head><title>Premium nệm ngủ</title>'
                '</head><body><main><h1>Tư vấn chọn nệm ngủ</h1>'
                '<p>Nệm phù hợp gia đình</p></main></body></html>')
        (site/"index.html").write_text(html, encoding="utf-8")
        html_sha = hashlib.sha256(html.encode()).hexdigest()
        with patch.object(web_assets, "_project", return_value=site):
            topic = visual_jobs.website_subject("my-site")
        self.assertIn("nệm ngủ", topic)
        result = self.submit(purpose="website", source_sha=html_sha)
        ident = result["job_ids"][0]
        buffer = io.BytesIO()
        Image.new("RGB", (768, 512), (200, 180, 160)).save(buffer, format="PNG")
        self.files.mkdir()
        (self.files / (ident+".png")).write_bytes(buffer.getvalue())
        sha = hashlib.sha256(buffer.getvalue()).hexdigest()
        with visual_jobs._db(self.db, create=True) as db:
            db.execute("UPDATE visual_jobs SET asset_sha=?,status='ASSET_READY' WHERE job_id=?",
                       (sha, ident))
        other_sha = "f"*64
        with patch.object(visual_jobs, "OUTPUTS", self.files), \
             patch.object(web_assets, "_project", return_value=site), \
             patch.object(web_assets, "_path", side_effect=lambda slug, name: site/"assets"/name), \
             patch.object(web_assets, "list_images", return_value=[]), \
             patch.object(image_studio_v24, "DB", temp/"image_studio.sqlite3"), \
             patch("agentforge.ops_control.require_active"), \
             patch.object(image_studio_v24, "attach",
                          return_value={"status":"ATTACHED","published":False}) as attach:
            with self.assertRaises(PermissionError):
                visual_jobs.attach_website(ident, "my-site", sha, other_sha,
                                           confirm_attach=True, db_path=self.db)
            self.assertFalse((site/"assets").exists())
            out=visual_jobs.attach_website(ident, "my-site", sha, html_sha,
                                           confirm_attach=True, db_path=self.db)
            self.assertEqual(out["status"], "ATTACHED")
            self.assertEqual((site/"assets"/("af-ai-"+ident+".png")).read_bytes(),
                             buffer.getvalue())
            attach.assert_called_once_with(ident,sha,html_sha,confirm_attach=True)

    def test_missing_comfy_checkpoint_fails_before_ledger_or_gpu(self):
        with patch("agentforge.ops_control.require_active"), \
             patch("agentforge.features.websites.image_studio.health",
                   return_value={"status":"UNAVAILABLE", "checkpoints":[]}), \
             patch("agentforge.features.websites.image_studio._request") as req:
            with self.assertRaises(PermissionError):
                visual_jobs.submit("image", "nệm ngủ", ["ảnh nệm"], self.checkpoint,
                                   confirm_generation=True, db_path=self.db)
            req.assert_not_called()
        self.assertFalse(self.db.exists())

    def test_video_generation_requires_inspected_task_sha_and_external_mode(self):
        ident="b"*32
        sha=quality_v14._sha(STORY)
        server=SimpleNamespace(allow_external_actions=True, task_db_path=None)
        req={"ack":"GENERATE_STORYBOARD_VISUALS", "task_id":ident,
             "source_sha":sha, "checkpoint":self.checkpoint}
        with patch("agentforge.task_history.get_task", return_value={
            "skill_id":"media.copy_draft", "status":"SUCCEEDED", "result":STORY,
        }), patch("agentforge.features.media.visual_jobs.submit",
                 return_value={"status":"SUBMITTED"}) as submit:
            with self.assertRaises(PermissionError):
                media_routes.handle(server, "/api/visuals/generate-for-task", req, session={})
            out=media_routes.handle(
                server, "/api/visuals/generate-for-task", req,
                session={"inspected_storyboard_tasks":{ident:sha}})
            self.assertEqual(out["status"], "SUBMITTED")
            args,kwargs=submit.call_args
            self.assertEqual(args[0],"video")
            self.assertEqual(len(args[2]),2)
            self.assertEqual(kwargs["source_sha"],sha)
            self.assertTrue(kwargs["confirm_generation"])
            submit.assert_called_once()
            server.allow_external_actions=False
            with self.assertRaises(PermissionError):
                media_routes.handle(
                    server, "/api/visuals/generate-for-task", req,
                    session={"inspected_storyboard_tasks":{ident:sha}})


if __name__ == "__main__":
    unittest.main()
