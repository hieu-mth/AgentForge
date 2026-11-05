"""Offline V1.5 regression tests: local owner gates, provenance, immutable video review.

Media renderer and S1 dispatch are mocked. No real subprocess, model, or upload.
"""
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import autopilot_v13, media_workflow_v15 as workflow
from agentforge import quality_v14 as quality

PROFILE = {
    "business": "Tư vấn nệm ngủ gia đình",
    "industry": "Nệm ngủ gia đình",
    "focus_phrases": ["nệm", "nệm ngủ"],
    "blocked_phrases": ["nem chua", "nem nướng"],
}
STORY = {
    "slug": "nem-ngu-v15-pilot",
    "title": "Tư vấn chọn nệm ngủ",
    "scenes": [
        {"headline": "Chọn nệm ngủ thế nào?", "caption": "Tìm hiểu độ nâng đỡ của nệm.",
         "duration_seconds": 5},
        {"headline": "Nệm phù hợp nhu cầu", "caption": "Trao đổi nhu cầu trước khi chọn nệm.",
         "duration_seconds": 5},
    ]
}
ASSETS = {"status": "ASSETS_PASS", "failures": 0}
VIDEO = {"status": "VIDEO_PASS", "failures": 0, "video_verified": True}
RUN_ID = "a" * 32
TASK_ID = "b" * 32
VID_SHA = "c" * 64


class MediaWorkflowV15Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "video.sqlite3"
        self.autopilot_db = Path(temp.name) / "ai.sqlite3"
        quality.set_profile(PROFILE, confirm=True, db_path=self.autopilot_db)

    def prep(self, *, storyboard=None, source_job_id=None, source_sha=None):
        with patch("agentforge.skill_runner.invoke", return_value={
            "status": "SUCCEEDED", "task_id": TASK_ID, "result": {"run_id": RUN_ID}
        }) as invoked, patch("agentforge.media_quality.check", return_value=ASSETS):
            result = workflow.prepare(
                storyboard or STORY, confirm_edit=True, db_path=self.db,
                autopilot_db_path=self.autopilot_db,
                source_job_id=source_job_id, source_output_sha=source_sha)
            self.assertEqual("media.compose", invoked.call_args.args[0])
            self.assertEqual(("workspace.write",), invoked.call_args.kwargs["grants"])
            self.assertNotIn("confirm_model_call", invoked.call_args.kwargs)
        return result

    def produced(self):
        result = self.prep()
        with patch("agentforge.skill_runner.invoke", return_value={
            "status": "SUCCEEDED", "task_id": "d" * 32,
            "result": {"video_path": "D:/AgentForge/workspace/media/video.mp4"}
        }) as invoked, patch("agentforge.media_quality.check", return_value=VIDEO), \
             patch("agentforge.media_assets.load_manifest", return_value=(
                 Path("D:/AgentForge/workspace/media"), {"artifacts": {"video.mp4": VID_SHA},
                  "slug": STORY["slug"], "title": STORY["title"],
                  "scenes": STORY["scenes"]}
             )):
            rendered = workflow.render(result["production_id"],
                                       confirm_local_process=True, db_path=self.db)
            self.assertEqual("media.video_render", invoked.call_args.args[0])
            self.assertTrue(invoked.call_args.kwargs["confirm_external_run"])
            self.assertEqual({"workspace.write", "process.run"},
                             set(invoked.call_args.kwargs["grants"]))
        return rendered

    def test_prepare_local_uses_no_model_and_persists(self):
        result = self.prep()
        self.assertEqual(0, result["model_calls"])
        self.assertEqual("ASSETS_READY", result["status"])
        self.assertEqual(1, len(workflow.report(db_path=self.db)["productions"]))

    def test_prepare_requires_owner_confirmation(self):
        with patch("agentforge.skill_runner.invoke") as run:
            with self.assertRaises(PermissionError):
                workflow.prepare(STORY, db_path=self.db,
                                 autopilot_db_path=self.autopilot_db)
            run.assert_not_called()

    def test_wrong_domain_storyboard_fails_before_media_write(self):
        bad = {**STORY, "scenes": [
            {"headline": "Nem chua", "caption": "Món nem chua ngon.",
             "duration_seconds": 5},
            {"headline": "Nem nướng", "caption": "Ăn nem nướng.",
             "duration_seconds": 5}
        ]}
        with patch("agentforge.skill_runner.invoke") as run:
            with self.assertRaises(PermissionError):
                workflow.prepare(bad, confirm_edit=True,
                                 db_path=self.db, autopilot_db_path=self.autopilot_db)
            run.assert_not_called()

    def test_unsupported_fields_disallowed(self):
        with self.assertRaises(ValueError):
            workflow.prepare({**STORY, "publish": True}, confirm_edit=True,
                             db_path=self.db, autopilot_db_path=self.autopilot_db)

    def test_link_rejected_ai_source_without_copying_its_output(self):
        job = autopilot_v13.submit("media.copy_draft", {
            "topic": "Tư vấn nệm ngủ", "audience": "Người mua nệm",
            "goal": "Nội dung nệm ngủ"
        }, db_path=self.autopilot_db)
        src_sha = "e" * 64
        with closing(autopilot_v13._connect(self.autopilot_db, create=True)) as db:
            db.execute("""INSERT INTO content_reviews VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (job["job_id"], TASK_ID, "media.copy_draft", src_sha,
                        None, "PASS_HEURISTIC", '["test"]', "REJECTED", None, "today"))
        result = self.prep(source_job_id=job["job_id"], source_sha=src_sha)
        self.assertEqual(job["job_id"], result["source_job_id"])
        row = workflow.report(db_path=self.db)["productions"][0]
        self.assertEqual(result["storyboard_sha"], row["storyboard_sha"])

    def test_unreviewed_ai_source_cannot_be_linked(self):
        job = autopilot_v13.submit("media.copy_draft", {
            "topic": "Tư vấn nệm ngủ", "audience": "Người mua nệm",
            "goal": "Nội dung nệm ngủ"
        }, db_path=self.autopilot_db)
        with patch("agentforge.skill_runner.invoke") as invoked:
            with self.assertRaises(PermissionError):
                workflow.prepare(STORY, confirm_edit=True, db_path=self.db,
                                 autopilot_db_path=self.autopilot_db,
                                 source_job_id=job["job_id"],
                                 source_output_sha="e" * 64)
            invoked.assert_not_called()

    def test_ffmpeg_requires_explicit_confirm_and_once_claim(self):
        first = self.prep()
        with patch("agentforge.skill_runner.invoke") as invoked:
            with self.assertRaises(PermissionError):
                workflow.render(first["production_id"], db_path=self.db)
            invoked.assert_not_called()
        result = self.produced_for(first["production_id"])
        self.assertEqual("VIDEO_READY", result["status"])
        with self.assertRaises(PermissionError):
            workflow.render(first["production_id"], confirm_local_process=True,
                            db_path=self.db)

    def produced_for(self, production_id):
        with patch("agentforge.skill_runner.invoke", return_value={
            "status": "SUCCEEDED", "task_id": "d" * 32,
            "result": {"video_path": "local/video.mp4"}
        }), patch("agentforge.media_quality.check", return_value=VIDEO), \
             patch("agentforge.media_assets.load_manifest", return_value=(
                 Path("local"), {"artifacts": {"video.mp4": VID_SHA},
                  "slug": STORY["slug"], "title": STORY["title"],
                  "scenes": STORY["scenes"]}
             )):
            return workflow.render(production_id, confirm_local_process=True,
                                   db_path=self.db)

    def test_renderer_failure_is_not_retried_or_automatically_approved(self):
        first = self.prep()
        with patch("agentforge.skill_runner.invoke", side_effect=RuntimeError("ffmpeg failed")):
            with self.assertRaises(RuntimeError):
                workflow.render(first["production_id"], confirm_local_process=True,
                                db_path=self.db)
        row = workflow.report(db_path=self.db)["productions"][0]
        self.assertEqual("RENDERING", row["status"])
        with self.assertRaises(PermissionError):
            workflow.render(first["production_id"], confirm_local_process=True,
                            db_path=self.db)

    def test_video_approval_requires_sha_and_qa(self):
        item = self.produced()
        with self.assertRaises(PermissionError):
            workflow.decide(item["production_id"], "APPROVE", VID_SHA, db_path=self.db)
        with self.assertRaises(PermissionError):
            workflow.decide(item["production_id"], "APPROVE", "f"*64,
                            confirm_review=True, db_path=self.db)
        with patch("agentforge.media_quality.check", return_value=VIDEO), \
             patch("agentforge.media_assets.load_manifest", return_value=(
                 Path("local"), {"artifacts": {"video.mp4": VID_SHA},
                  "slug": STORY["slug"], "title": STORY["title"],
                  "scenes": STORY["scenes"]}
             )):
            result = workflow.decide(item["production_id"], "APPROVE", VID_SHA,
                                     confirm_review=True, db_path=self.db)
        self.assertEqual("APPROVED", result["decision"])
        self.assertFalse(result["published"])
        self.assertFalse(result["upload_authorized"])
        with self.assertRaises(PermissionError):
            workflow.decide(item["production_id"], "REJECT", VID_SHA,
                            confirm_review=True, db_path=self.db)

    def test_video_qa_failure_prevents_approval(self):
        item = self.produced()
        with patch("agentforge.media_quality.check", return_value={
            "status": "FAIL", "failures": 1
        }), patch("agentforge.media_assets.load_manifest", return_value=(
            Path("local"), {"artifacts": {"video.mp4": VID_SHA},
                            "slug": STORY["slug"], "title": STORY["title"],
                            "scenes": STORY["scenes"]}
        )):
            with self.assertRaises(PermissionError):
                workflow.decide(item["production_id"], "APPROVE", VID_SHA,
                                confirm_review=True, db_path=self.db)

    def test_modified_storyboard_manifest_blocks_render(self):
        prepared = self.prep()
        modified = {"artifacts": {"video.mp4": VID_SHA},
                    "slug": STORY["slug"], "title": STORY["title"] + " tampered",
                    "scenes": STORY["scenes"]}
        with patch("agentforge.media_assets.load_manifest",
                   return_value=(Path("local"), modified)), \
             patch("agentforge.skill_runner.invoke") as invoked:
            with self.assertRaises(PermissionError):
                workflow.render(prepared["production_id"], confirm_local_process=True,
                                db_path=self.db)
            invoked.assert_not_called()

    def test_dashboard_prepare_api_requires_matching_owner_ack(self):
        from agentforge.control_center_v1 import _owner_action
        with patch("agentforge.media_workflow_v15.prepare",
                   return_value={"status": "ASSETS_READY"}) as action:
            with self.assertRaises(PermissionError):
                _owner_action(None, "/api/media/prepare",
                              {"ack": "wrong", "storyboard": STORY})
            action.assert_not_called()
            result = _owner_action(None, "/api/media/prepare",
                                   {"ack": "PREPARE_EDITED_STORYBOARD",
                                    "storyboard": STORY})
            self.assertEqual("ASSETS_READY", result["status"])
            self.assertTrue(action.call_args.kwargs["confirm_edit"])

    def test_emergency_pause_prevents_preparation_and_render(self):
        with patch("agentforge.ops_control.require_active", side_effect=PermissionError("PAUSED")):
            with self.assertRaises(PermissionError):
                workflow.prepare(STORY, confirm_edit=True, db_path=self.db,
                                 autopilot_db_path=self.autopilot_db)
        prepared = self.prep()
        with patch("agentforge.ops_control.require_active", side_effect=PermissionError("PAUSED")):
            with self.assertRaises(PermissionError):
                workflow.render(prepared["production_id"], confirm_local_process=True,
                                db_path=self.db)


if __name__ == "__main__":
    unittest.main()
