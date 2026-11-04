"""S4 goal planning, safe delegation and durable crash/approval regression."""
import hashlib
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agentforge import brain_planner as planner
from agentforge import brain_runner as runner
from agentforge import brain_scheduler as scheduler
from agentforge import brain_store as store
from agentforge import skill_runner, task_history
from agentforge import analytics_pipeline, analytics_store


STORY = [
    {"headline": "Nệm phù hợp", "caption": "Tư vấn theo nhu cầu.", "duration_seconds": 3},
    {"headline": "Trao đổi cùng nhau", "caption": "Liên hệ để tìm hiểu.", "duration_seconds": 3},
]


class TestS4Brain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.brain_db = self.root / "brain.sqlite3"
        self.task_db = self.root / "tasks.sqlite3"
        self.analytics_db = self.root / "analytics.sqlite3"
        self.inbox = self.root / "workspace" / "analytics" / "inbox"
        self.patches = [
            patch.object(store, "DB", self.brain_db),
            patch.object(task_history, "DEFAULT_DB", self.task_db),
            patch.object(analytics_store, "DB", self.analytics_db),
            patch.object(analytics_store, "INBOX", self.inbox),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def _plan(self, template="campaign.review", inputs=None, **opts):
        if inputs is None:
            inputs = {"dataset": "demo-research", "campaign": "nem-shorts"}
        return planner.propose(
            "Review content campaign", template, inputs,
            db_path=self.brain_db, **opts)

    def _approve(self, goal):
        return store.approve_goal(
            goal["goal_id"], goal["plan_sha256"], db_path=self.brain_db)

    def _run(self, goal, **kwargs):
        return runner.execute(
            goal["goal_id"], brain_db_path=self.brain_db,
            task_db_path=self.task_db, **kwargs)

    def test_plan_never_executes_without_digest_approval(self):
        goal = self._plan()
        self.assertEqual(goal["status"], "PLANNED")
        self.assertEqual(goal["step_count"], 4)
        self.assertFalse(self.task_db.exists())
        self.assertFalse(goal["spending_authorized"])
        with self.assertRaisesRegex(store.BrainError, "digest mismatch"):
            store.approve_goal(goal["goal_id"], "0" * 64, db_path=self.brain_db)
        with self.assertRaisesRegex(store.BrainError, "approved"):
            self._run(goal)
        self.assertFalse(self.task_db.exists())
        self.assertEqual(self._approve(goal)["status"], "APPROVED")
        with self.assertRaises(store.BrainError):
            self._approve(goal)

    def test_fixed_template_rejects_arbitrary_skills_and_unsafe_inputs(self):
        with self.assertRaises(store.BrainError):
            self._plan(template="tool.exec", inputs={"command": "rm -rf"})
        with self.assertRaises(store.BrainError):
            self._plan(inputs={"dataset": "demo-research", "shell": "anything"})
        with self.assertRaises(store.BrainError):
            self._plan(template="website.browser", inputs={})
        with self.assertRaises(store.BrainError):
            self._plan(template="media.produce", inputs={
                "slug": "nem-s2", "title": "Tư vấn nệm", "scenes": STORY})
        self.assertFalse(self.brain_db.exists())

    def test_model_call_cap_and_external_process_cap(self):
        with self.assertRaisesRegex(store.BrainError, "cap"):
            self._plan(template="creative.storyboard", inputs={
                "topic": "nệm", "audience": "khách mới", "goal": "tư vấn"})
        with self.assertRaisesRegex(store.BrainError, "cap"):
            self._plan(template="research.discovery", inputs={
                "topic": "Nghiên cứu thị trường nệm năm nay"})
        with self.assertRaisesRegex(store.BrainError, "cap"):
            self._plan(template="media.produce", inputs={
                "slug": "nem-s2", "title": "Tư vấn nệm",
                "scenes": STORY})
        goal = self._plan(template="media.produce", inputs={
            "slug": "nem-s2", "title": "Tư vấn nệm", "scenes": STORY},
            max_external_runs=1)
        self.assertEqual(goal["step_count"], 3)
        self.assertEqual(goal["limits"]["max_external_runs"], 1)

    def test_actual_campaign_goal_executes_four_existing_skills(self):
        seed = analytics_pipeline.synthetic_demo()
        self.assertEqual(seed["status"], "SUCCEEDED")
        goal = self._plan(inputs={
            "dataset": seed["dataset"], "campaign": "nem-shorts"})
        self._approve(goal)
        with patch("agentforge.model.generate") as model:
            output = self._run(goal)
            model.assert_not_called()
        self.assertEqual(output["status"], "SUCCEEDED")
        self.assertEqual(output["executed_steps"], 4)
        task = task_history.get_task(output["task_id"], db_path=self.task_db)
        self.assertEqual(task["status"], "SUCCEEDED")
        children = [x for x in task_history.list_tasks(
            db_path=self.task_db) if x["parent_id"] == output["task_id"]]
        self.assertEqual(len(children), 4)
        self.assertEqual([s["status"] for s in store.get_goal(
            goal["goal_id"], db_path=self.brain_db)["steps"]], ["SUCCEEDED"] * 4)
        with self.assertRaises(store.BrainError):
            self._run(goal)
        # Eight existing S3 tasks, then S4 parent + four delegated skills.
        self.assertEqual(len(task_history.list_tasks(db_path=self.task_db)), 13)

    def test_write_and_process_gate_wait_and_resume_independently(self):
        goal = self._plan(template="media.produce", inputs={
            "slug": "nem-s2", "title": "Tư vấn nệm", "scenes": STORY},
            max_external_runs=1)
        self._approve(goal)
        with patch("agentforge.media_assets.make_assets") as create:
            pending = self._run(goal)
            create.assert_not_called()
        self.assertEqual(pending["status"], "WAITING_APPROVAL")
        self.assertIn("workspace.write", pending["missing"])
        brain = store.get_goal(goal["goal_id"], db_path=self.brain_db)
        first_child = brain["steps"][0]["child_task_id"]
        self.assertEqual(task_history.get_task(
            first_child, db_path=self.task_db)["status"], "WAITING_APPROVAL")
        with patch("agentforge.media_assets.make_assets", return_value={
            "run_id": "a" * 32, "project_slug": "nem-s2",
            "status": "ASSETS_READY", "video_rendered": False,
        }) as create:
            with patch("agentforge.media_quality.check", return_value={
                "run_id": "a" * 32, "status": "ASSETS_PASS",
                "failures": 0, "warnings": 0, "findings": [],
            }) as quality:
                with patch("agentforge.media_render.render_video") as video:
                    second = self._run(goal, grants=("workspace.write",))
                    video.assert_not_called()
                    create.assert_called_once()
                    quality.assert_called_once_with("a" * 32)
        self.assertEqual(second["status"], "WAITING_APPROVAL")
        self.assertEqual(second["waiting_step"], 2)
        self.assertIn("process.run", second["missing"])
        self.assertIn("confirm_external_run", second["missing"])
        state = store.get_goal(goal["goal_id"], db_path=self.brain_db)
        self.assertEqual([s["status"] for s in state["steps"]],
                         ["SUCCEEDED", "SUCCEEDED", "WAITING_APPROVAL"])
        with patch("agentforge.media_render.render_video", return_value={
            "run_id": "a" * 32, "status": "VIDEO_RENDERED",
            "video_path": "offline.mp4", "quality_status": "VIDEO_PASS",
        }) as video:
            final = self._run(goal, grants=("workspace.write", "process.run"),
                              confirm_external_run=True)
            video.assert_called_once_with("a" * 32, confirm_external_run=True)
        self.assertEqual(final["status"], "SUCCEEDED")
        self.assertEqual(final["executed_steps"], 3)
        self.assertEqual(len(task_history.list_tasks(db_path=self.task_db)), 4)

    def test_web_quality_failure_prevents_browser_even_if_permission_given(self):
        goal = self._plan(template="website.browser",
                          inputs={"slug": "nem-tu-van"})
        self._approve(goal)
        with patch("agentforge.product_quality.check_project", return_value={
            "status": "FAIL", "failures": 1, "warnings": 0,
            "findings": [{"rule": "inline_events", "severity": "FAIL"}],
            "sha256": "a" * 64,
        }) as quality:
            with patch("agentforge.browser_validation.validate") as browser:
                result = self._run(
                    goal, grants=("browser.run",), confirm_browser_run=True)
                quality.assert_called_once()
                browser.assert_not_called()
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("Quality gate", result["error"])
        self.assertEqual(store.get_goal(goal["goal_id"],
                                       db_path=self.brain_db)["status"], "FAILED")

    def test_tampered_plan_detected_before_creating_task(self):
        goal = self._plan()
        self._approve(goal)
        with closing(sqlite3.connect(self.brain_db)) as conn, conn:
            conn.execute("UPDATE goals SET plan_json=? WHERE goal_id=?",
                         ('[{"skill_id":"web.create"}]', goal["goal_id"]))
        with self.assertRaisesRegex(store.BrainError, "SHA"):
            self._run(goal)
        self.assertFalse(self.task_db.exists())

    def test_ambiguous_dispatch_marks_interrupted_no_retries(self):
        goal = self._plan()
        self._approve(goal)
        with patch.object(skill_runner, "invoke",
                          side_effect=RuntimeError("possibly already executed")) as tool:
            result = self._run(goal)
        tool.assert_called_once()
        self.assertEqual(result["status"], "INTERRUPTED")
        current = store.get_goal(goal["goal_id"], db_path=self.brain_db)
        self.assertEqual(current["steps"][0]["status"], "DISPATCHING")
        with patch.object(skill_runner, "invoke") as tool:
            with self.assertRaises(store.BrainError):
                self._run(goal)
            tool.assert_not_called()

    def test_explicit_recovery_does_not_retry_or_affect_other_tasks(self):
        goal = self._plan()
        self._approve(goal)
        parent = task_history.create_task("workflow", "brain.goal",
                                          {"goal_id": goal["goal_id"]},
                                          db_path=self.task_db)
        task_history.transition(parent, "RUNNING", db_path=self.task_db)
        store.change_state(goal["goal_id"], "RUNNING", expected="APPROVED",
                           parent_task_id=parent, db_path=self.brain_db)
        unrelated = task_history.create_task("skill", "web.quality_check", {},
                                             db_path=self.task_db)
        task_history.transition(unrelated, "RUNNING", db_path=self.task_db)
        result = runner.recover(brain_db_path=self.brain_db, task_db_path=self.task_db)
        self.assertEqual(result["interrupted_goals"], 1)
        self.assertEqual(task_history.get_task(parent, db_path=self.task_db)["status"],
                         "INTERRUPTED")
        self.assertEqual(task_history.get_task(unrelated, db_path=self.task_db)["status"],
                         "RUNNING")
        self.assertEqual(runner.recover(brain_db_path=self.brain_db,
                                        task_db_path=self.task_db)["interrupted_goals"], 0)

    def test_scheduler_only_readonly_and_once_per_due_slot(self):
        future = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
        with self.assertRaises(PermissionError):
            scheduler.create_schedule(
                "Run an approved browser", "website.browser",
                {"slug": "nem-tu-van"}, future.isoformat(), 60,
                confirm_schedule=True, db_path=self.brain_db,
                now=future-timedelta(hours=1))
        with self.assertRaises(PermissionError):
            scheduler.create_schedule(
                "A read-only schedule", "campaign.review",
                {"dataset": "demo-test"}, future.isoformat(), 60,
                db_path=self.brain_db, now=future-timedelta(hours=1))
        result = scheduler.create_schedule(
            "Review campaign every hour", "campaign.review",
            {"dataset": "demo-test"}, future.isoformat(), 60,
            confirm_schedule=True, db_path=self.brain_db,
            now=future-timedelta(hours=1))
        self.assertEqual(result["status"], "ACTIVE")
        self.assertEqual(scheduler.list_schedules(db_path=self.brain_db)[0]["status"],
                         "ACTIVE")
        with self.assertRaises(PermissionError):
            scheduler.tick(db_path=self.brain_db, now=future)
        with patch.object(runner, "execute", return_value={
            "status": "SUCCEEDED", "goal_id": "a" * 32,
        }) as run:
            t1 = scheduler.tick(confirm_tick=True, db_path=self.brain_db,
                                task_db_path=self.task_db, now=future)
            run.assert_called_once()
            t2 = scheduler.tick(confirm_tick=True, db_path=self.brain_db,
                                task_db_path=self.task_db, now=future)
        self.assertEqual(len(t1["claimed"]), 1)
        self.assertEqual(len(t2["claimed"]), 0)
        current = store.get_goal(t1["claimed"][0]["goal_id"],
                                 db_path=self.brain_db)
        self.assertEqual(current["status"], "APPROVED")
        self.assertEqual(current["source_schedule_id"], result["schedule_id"])
        self.assertEqual(len(scheduler.list_schedules(db_path=self.brain_db)), 1)
        self.assertEqual(scheduler.set_schedule_status(
            result["schedule_id"], "PAUSED",
            confirm_write=True, db_path=self.brain_db)["status"], "PAUSED")
        with self.assertRaises(PermissionError):
            scheduler.set_schedule_status(result["schedule_id"], "ACTIVE",
                                          db_path=self.brain_db)

    def test_schedule_digest_blocks_template_changes_without_reapproval(self):
        future = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
        schedule = scheduler.create_schedule(
            "Review campaign", "campaign.review", {"dataset": "demo-test"},
            future.isoformat(), 60, confirm_schedule=True, db_path=self.brain_db,
            now=future - timedelta(hours=1))
        with closing(sqlite3.connect(self.brain_db)) as conn, conn:
            conn.execute("UPDATE schedules SET plan_sha256=? WHERE schedule_id=?",
                         ("0" * 64, schedule["schedule_id"]))
        with patch.object(runner, "execute") as execute:
            with self.assertRaisesRegex(store.BrainError, "plan changed"):
                scheduler.tick(confirm_tick=True, db_path=self.brain_db,
                               task_db_path=self.task_db, now=future)
            execute.assert_not_called()
        self.assertEqual(store.list_goals(db_path=self.brain_db), [])
        self.assertEqual(scheduler.list_schedules(
            db_path=self.brain_db)[0]["next_due_utc"], future.isoformat())

    def test_owner_memory_is_explicit_and_revisioned(self):
        with self.assertRaises(PermissionError):
            store.set_memory("marketing.goal", "Focus on useful answers",
                             "owner:interview", db_path=self.brain_db)
        a = store.set_memory(
            "marketing.goal", "Focus on useful answers", "owner:interview",
            confirm_write=True, db_path=self.brain_db)
        b = store.set_memory(
            "marketing.goal", "Keep evidence first", "owner:decision-2",
            confirm_write=True, db_path=self.brain_db)
        self.assertEqual((a["revision"], b["revision"]), (1, 2))
        result = store.list_memory(db_path=self.brain_db)
        self.assertEqual(result[0]["note"], "Keep evidence first")
        self.assertEqual(result[0]["evidence_ref"], "owner:decision-2")

    def test_no_implicit_cloud_or_ad_spend_in_demo(self):
        from agentforge import company_brain
        with patch("agentforge.model.generate") as model:
            with patch("subprocess.run") as process:
                with patch("urllib.request.urlopen") as network:
                    with self.assertRaises(PermissionError):
                        company_brain.demo(confirm_demo=False)
                    outcome = company_brain.demo(confirm_demo=True)
                    model.assert_not_called()
                    process.assert_not_called()
                    network.assert_not_called()
        self.assertEqual(outcome["status"], "SUCCEEDED")
        self.assertTrue(outcome["synthetic"])
        self.assertEqual(outcome["planned_steps"], 4)
        self.assertEqual(outcome["completed_steps"], 4)
        self.assertFalse(outcome["spending_authorized"])
        self.assertFalse(outcome["autonomous_background_running"])


if __name__ == "__main__":
    unittest.main()
