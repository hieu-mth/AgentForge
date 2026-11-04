"""End-to-end S4 orchestration: S2 media -> two owner-gated S5 upload kits."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import brain_planner, brain_runner, brain_store, task_history


SCENES = [
    {"headline": "Chọn nệm", "caption": "Đánh giá nhu cầu trước khi mua.",
     "duration_seconds": 3},
    {"headline": "Tư vấn", "caption": "Tìm hiểu thêm về độ nâng đỡ.",
     "duration_seconds": 3},
]
INPUTS = {
    "campaign": "nem-pilot", "slug": "nem-pilot", "title": "Tư vấn chọn nệm",
    "description": "Các yếu tố để cân nhắc khi chọn nệm.",
    "scenes": SCENES, "rights_attested": True,
}
RUN_ID = "a" * 32


class TestLaunchLocalTemplate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.brain = self.root / "brain.sqlite3"
        self.tasks = self.root / "task.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_refuses_unapproved_rights_and_process_cap(self):
        with self.assertRaisesRegex(brain_store.BrainError, "attest"):
            brain_planner.propose(
                "Publish short", "growth.launch_local",
                {**INPUTS, "rights_attested": False}, db_path=self.brain,
                max_external_runs=1)
        with self.assertRaisesRegex(brain_store.BrainError, "cap"):
            brain_planner.propose(
                "Publish short", "growth.launch_local", INPUTS,
                db_path=self.brain)
        self.assertFalse(self.brain.exists())

    def test_six_step_plan_review_pause_for_process_and_manual_handoff(self):
        goal = brain_planner.propose(
            "Prepare channels for review", "growth.launch_local", INPUTS,
            max_external_runs=1, db_path=self.brain)
        self.assertEqual(goal["step_count"], 6)
        self.assertEqual([x["skill_id"] for x in goal["plan"]], [
            "media.compose", "media.quality_check", "media.video_render",
            "growth.bundle_prepare", "growth.bundle_prepare",
            "growth.quality_check"])
        self.assertNotIn("network", str(goal["plan"]))
        brain_store.approve_goal(goal["goal_id"], goal["plan_sha256"],
                              db_path=self.brain)
        bundle_calls = []
        def fake_bundle(campaign, channel, run_id, title, description,
                        confirm_rights=False, confirm_write=False):
            self.assertEqual(campaign, "nem-pilot")
            self.assertEqual(run_id, RUN_ID)
            self.assertTrue(confirm_rights)
            self.assertTrue(confirm_write)
            bundle_calls.append(channel)
            return {"status": "READY_FOR_OWNER_UPLOAD", "campaign": campaign,
                    "channel": channel, "package_id": "b" * 32,
                    "archive_path": "local.zip", "published": False}
        with patch("agentforge.media_assets.make_assets",
                   return_value={"run_id": RUN_ID, "project_slug": "nem-pilot",
                                 "status": "ASSETS_READY", "video_rendered": False}):
            with patch("agentforge.media_quality.check",
                       return_value={"run_id": RUN_ID, "status": "ASSETS_PASS",
                                     "failures": 0, "warnings": 0, "findings": []}):
                with patch("agentforge.media_render.render_video",
                           return_value={"run_id": RUN_ID,
                                         "status": "VIDEO_RENDERED",
                                         "video_path": "local.mp4",
                                         "quality_status": "VIDEO_PASS"}) as ffmpeg:
                    with patch("agentforge.growth_bundle.prepare",
                               side_effect=fake_bundle):
                        with patch("agentforge.growth_reports.quality_check",
                                   return_value={"status": "REVIEW_REQUIRED",
                                                 "failures": 0,
                                                 "warnings": 2,
                                                 "findings": []}):
                            first = brain_runner.execute(
                                goal["goal_id"],
                                grants=("workspace.write",),
                                brain_db_path=self.brain,
                                task_db_path=self.tasks)
                            self.assertEqual(first["status"], "WAITING_APPROVAL")
                            self.assertEqual(first["waiting_step"], 2)
                            self.assertIn("process.run", first["missing"])
                            self.assertEqual(bundle_calls, [])
                            ffmpeg.assert_not_called()
                            second = brain_runner.execute(
                                goal["goal_id"],
                                grants=("workspace.write", "process.run"),
                                confirm_external_run=True,
                                brain_db_path=self.brain,
                                task_db_path=self.tasks)
                            self.assertEqual(second["status"], "SUCCEEDED")
                            self.assertEqual(second["executed_steps"], 6)
                            ffmpeg.assert_called_once_with(
                                RUN_ID, confirm_external_run=True)
        self.assertEqual(bundle_calls, ["youtube", "tiktok"])
        observed = brain_store.get_goal(goal["goal_id"], db_path=self.brain)
        self.assertEqual(observed["status"], "SUCCEEDED")
        self.assertEqual(len(observed["steps"]), 6)
        self.assertTrue(all(x["status"]=="SUCCEEDED" for x in observed["steps"]))
        self.assertEqual(len(task_history.list_tasks(db_path=self.tasks)), 7)
        with self.assertRaises(brain_store.BrainError):
            brain_runner.execute(goal["goal_id"],
                                 brain_db_path=self.brain,
                                 task_db_path=self.tasks)


if __name__ == "__main__":
    unittest.main()
