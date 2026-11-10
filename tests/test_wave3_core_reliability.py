"""Wave 3 independent regression probes for recovery, inspection and GPU quota.

Only local temporary SQLite/HTTP fixtures; never calls a paid model, launches
ComfyUI/GPU/FFmpeg or modifies real Owner state.
"""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from agentforge import (
    autopilot_v13, brain_runner, brain_store, ops_doctor,
    quality_v14, task_history,
)
from agentforge.features.film_studio import motion_comfy, long_form
from tests.test_film_motion_comfy import template, sample_plan


class Wave3RecoveryAndHealthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.brain = self.root / "data" / "company" / "goals.sqlite3"
        self.tasks = self.root / "data" / "company" / "tasks.sqlite3"

    def goal(self, title="Older running goal"):
        created = brain_store.create_goal(
            title, "website.browser", {},
            [{"skill_id": "web.quality_check"}], db_path=self.brain)
        brain_store.approve_goal(
            created["goal_id"], created["plan_sha256"], db_path=self.brain)
        return created

    def test_exact_id_recovery_covers_old_goal_and_preserves_dispatch_marker(self):
        old = self.goal()
        parent = task_history.create_task(
            "workflow", "brain.goal", {"goal_id": old["goal_id"]}, db_path=self.tasks)
        task_history.transition(parent, "RUNNING", db_path=self.tasks)
        brain_store.change_state(
            old["goal_id"], "RUNNING", expected="APPROVED",
            parent_task_id=parent, db_path=self.brain)
        child = task_history.create_task(
            "skill", "web.quality_check", {}, parent_id=parent, db_path=self.tasks)
        task_history.transition(child, "RUNNING", db_path=self.tasks)
        brain_store.claim_step(old["goal_id"], 0, "web.quality_check",
                              db_path=self.brain)
        # Crash after child dispatch but before its result was stored.
        with closing(sqlite3.connect(self.brain)) as db, db:
            db.execute("UPDATE step_runs SET child_task_id=? WHERE goal_id=?",
                       (child, old["goal_id"]))

        unrelated = task_history.create_task(
            "skill", "web.quality_check", {}, db_path=self.tasks)
        task_history.transition(unrelated, "RUNNING", db_path=self.tasks)
        for i in range(115):
            brain_store.create_goal(
                "Newer plan %03d" % i, "website.browser", {},
                [{"skill_id": "web.quality_check"}], db_path=self.brain)
        recent = brain_store.list_goals(db_path=self.brain, limit=100)
        self.assertNotIn(old["goal_id"], {g["goal_id"] for g in recent})
        self.assertEqual(brain_store.count_status("RUNNING", db_path=self.brain), 1)
        self.assertEqual(task_history.count_status("RUNNING", db_path=self.tasks), 3)
        report = brain_runner.recover(brain_db_path=self.brain, task_db_path=self.tasks)
        self.assertEqual(report, {"interrupted_goals": 1, "automatic_replay": False})
        detail = brain_store.get_goal(old["goal_id"], db_path=self.brain)
        self.assertEqual(detail["status"], "INTERRUPTED")
        self.assertEqual(detail["steps"][0]["status"], "DISPATCHING")
        self.assertEqual(detail["steps"][0]["child_task_id"], child)
        self.assertEqual([e["name"] for e in detail["events"]].count("INTERRUPTED"), 1)
        self.assertEqual(task_history.get_task(parent, db_path=self.tasks)["status"],
                         "INTERRUPTED")
        self.assertEqual(task_history.get_task(child, db_path=self.tasks)["status"],
                         "INTERRUPTED")
        self.assertEqual(task_history.get_task(unrelated, db_path=self.tasks)["status"],
                         "RUNNING")
        self.assertEqual(brain_runner.recover(
            brain_db_path=self.brain, task_db_path=self.tasks)["interrupted_goals"], 0)
        self.assertEqual(brain_store.recover(db_path=self.brain), 0)

    def test_doctor_global_counts_do_not_hide_old_running_history(self):
        old = self.goal()
        brain_store.change_state(old["goal_id"], "RUNNING", expected="APPROVED",
                                 db_path=self.brain)
        oldest = task_history.create_task(
            "skill", "web.quality_check", {}, db_path=self.tasks)
        task_history.transition(oldest, "RUNNING", db_path=self.tasks)
        for i in range(110):
            brain_store.create_goal(
                "Newer planned goal %03d" % i, "website.browser", {},
                [{"skill_id": "web.quality_check"}], db_path=self.brain)
        for i in range(205):
            task_history.create_task(
                "skill", "web.quality_check", {"index": i}, db_path=self.tasks)
        self.assertEqual(task_history.list_tasks(db_path=self.tasks, limit=200)
                         .count({"status": "RUNNING"}), 0)
        self.assertEqual(brain_store.count_status("RUNNING", db_path=self.brain), 1)
        self.assertEqual(task_history.count_status("RUNNING", db_path=self.tasks), 1)
        with patch.object(ops_doctor.skill_registry, "load_registry",
                          return_value={"web.quality_check": {}}), \
             patch.object(ops_doctor.ops_daemon, "read_heartbeat",
                          return_value={"status": "NOT_RUNNING", "fresh": False}), \
             patch.object(ops_doctor.ops_control, "read",
                          return_value={"mode": "ACTIVE", "reason": None}):
            result = ops_doctor.inspect(
                paths={"tasks": self.tasks, "goals": self.brain},
                backup_dir=self.root / "none", task_db=self.tasks,
                brain_db=self.brain)
        self.assertEqual(result["running_tasks"], 1)
        self.assertEqual(result["running_goals"], 1)
        self.assertIn("inflight_tasks_manual_review",
                      {x["rule"] for x in result["findings"]})

    def test_missing_sqlite_read_and_recover_never_create_files(self):
        self.assertEqual(task_history.list_tasks(db_path=self.tasks), [])
        self.assertEqual(task_history.count_status("RUNNING", db_path=self.tasks), 0)
        self.assertEqual(task_history.recover(db_path=self.tasks), 0)
        with self.assertRaises(KeyError):
            task_history.get_task("f" * 32, db_path=self.tasks)
        self.assertEqual(brain_store.list_goals(db_path=self.brain), [])
        self.assertEqual(brain_store.count_status("RUNNING", db_path=self.brain), 0)
        self.assertEqual(brain_store.recover(db_path=self.brain), 0)
        self.assertEqual(brain_store.recover(db_path=self.brain, return_ids=True), [])
        self.assertFalse(self.tasks.exists())
        self.assertFalse(self.brain.exists())
        self.assertFalse(self.brain.parent.exists())

    def test_task_inspection_is_read_only_on_existing_sqlite(self):
        task = task_history.create_task(
            "skill", "web.quality_check", {"sensitive": "not logged"},
            db_path=self.tasks)
        with closing(sqlite3.connect(self.tasks)) as db:
            before = [tuple(x) for x in db.execute(
                "SELECT name,sql FROM sqlite_master ORDER BY name")]
            events = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self.assertEqual(task_history.get_task(task, db_path=self.tasks)["status"],
                         "QUEUED")
        self.assertEqual(len(task_history.list_tasks(db_path=self.tasks)), 1)
        self.assertEqual(task_history.count_status("QUEUED", db_path=self.tasks), 1)
        with closing(sqlite3.connect(self.tasks)) as db:
            after = [tuple(x) for x in db.execute(
                "SELECT name,sql FROM sqlite_master ORDER BY name")]
            self.assertEqual(events, db.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        self.assertEqual(before, after)
        self.assertFalse((self.tasks.parent / (self.tasks.name + "-journal")).exists())


class Wave3LegacyQualityInspectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "autopilot.sqlite3"

    def test_absent_quality_inbox_is_pure_read(self):
        self.assertEqual(quality_v14.inbox(db_path=self.db),
                         {"business_context": None, "reviews": []})
        self.assertFalse(autopilot_v13.policy(db_path=self.db)["enabled"])
        self.assertFalse(self.db.exists())

    def test_existing_v13_schema_is_not_migrated_during_inspection(self):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("CREATE TABLE policy (singleton INTEGER PRIMARY KEY, "
                       "enabled INTEGER, daily_cap INTEGER, updated_utc TEXT)")
            db.execute("INSERT INTO policy VALUES(1,0,0,'old')")
        before = self.db.read_bytes()
        with closing(sqlite3.connect(self.db)) as db:
            tables_before = [r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        self.assertEqual(quality_v14.inbox(db_path=self.db),
                         {"business_context": None, "reviews": []})
        self.assertFalse(autopilot_v13.policy(db_path=self.db)["enabled"])
        self.assertEqual(self.db.read_bytes(), before)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(tables_before, [r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
        self.assertNotIn("content_reviews", tables_before)


class Wave3FilmTerminalFailureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.films = self.root / "films"
        self.db = self.root / "motion.sqlite3"
        self.workflow = self.root / "reviewed.json"
        self.workflow.write_text(json.dumps(template()), encoding="utf-8")
        self.plan = sample_plan(seconds=8)
        long_form.save_plan(self.films, "pilot", self.plan)
        self.shots = [x["shot_id"] for x in self.plan["shots"]]
        self.assertGreaterEqual(len(self.shots), 2)
        self.prompt = "Original cinematic fox in a wooded scene with gentle tracking camera."

    def submit(self, shot):
        with patch.object(motion_comfy.ops_control, "require_active"), \
             patch.object(motion_comfy, "health",
                          return_value={"status": "GPU_DETECTED_UNBENCHMARKED"}), \
             patch.object(motion_comfy, "_json_request",
                          return_value={"prompt_id": str(uuid4())}) as transport:
            result = motion_comfy.submit_shot(
                film_slug="pilot", shot_id=shot,
                plan_sha=self.plan["plan_sha256"], prompt=self.prompt,
                workflow_path=self.workflow,
                workflow_sha=motion_comfy.inspect_workflow(self.workflow)["sha256"],
                seed=7, confirmed=True, film_root=self.films, db_path=self.db)
            transport.assert_called_once()
            return result

    def provider(self, job):
        with closing(sqlite3.connect(self.db)) as db:
            return db.execute(
                "SELECT provider_id FROM motion_jobs WHERE job_id=?",
                (job["job_id"],)).fetchone()[0]

    def test_terminal_error_persists_failed_releases_quota_no_retry(self):
        first = self.submit(self.shots[0])
        pid = self.provider(first)
        with patch.object(motion_comfy, "_json_request", return_value={
                pid: {"status": {"status_str": "running", "completed": False}}}):
            view = motion_comfy.job_status(first["job_id"], db_path=self.db)
        self.assertEqual(view["status"], "PROVIDER_QUEUED_OR_UNKNOWN")
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT state FROM motion_jobs").fetchone()[0],
                             "SUBMITTED")
        with patch.object(motion_comfy, "_json_request", return_value={
                pid: {"status": {"status_str": "error", "completed": False}}}):
            result = motion_comfy.job_status(first["job_id"], db_path=self.db)
        self.assertEqual(result["status"], "PROVIDER_FAILED")
        self.assertFalse(result["video_verified"])
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT state FROM motion_jobs").fetchone()[0],
                             "FAILED")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM motion_jobs WHERE "
                                        "state IN ('SUBMITTED','SUBMITTING')").fetchone()[0], 0)
        with patch.object(motion_comfy, "_json_request") as provider:
            self.assertEqual(motion_comfy.job_status(
                first["job_id"], db_path=self.db)["status"], "PROVIDER_FAILED")
            provider.assert_not_called()
        next_shot = self.submit(self.shots[1])
        self.assertEqual(next_shot["status"], "SUBMITTED")
        self.assertNotEqual(next_shot["job_id"], first["job_id"])

    def test_unknown_or_missing_provider_history_keeps_quota_reserved(self):
        first = self.submit(self.shots[0])
        with patch.object(motion_comfy, "_json_request", return_value={}):
            self.assertEqual(motion_comfy.job_status(
                first["job_id"], db_path=self.db)["status"],
                "PROVIDER_QUEUED_OR_UNKNOWN")
        with self.assertRaises(PermissionError):
            self.submit(self.shots[1])
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT state FROM motion_jobs").fetchone()[0],
                             "SUBMITTED")


if __name__ == "__main__":
    unittest.main()
