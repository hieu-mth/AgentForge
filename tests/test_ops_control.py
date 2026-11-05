"""Owner emergency pause: file persistence, fail-closed, no new dispatch."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import ops_control, ops_daemon, brain_runner, brain_scheduler
from agentforge import brain_planner, brain_store, skill_runner


class TestOwnerOperationsPause(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ops_path = self.root / "local" / "ops_control.json"
        self.patcher = patch.object(ops_control, "STATE_FILE", self.ops_path)
        self.patcher.start()
        self.brain = self.root / "brain.sqlite3"
        self.tasks = self.root / "tasks.sqlite3"
        self.heartbeat = self.root / "heartbeat.json"

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_default_no_file_is_active_without_mutation(self):
        self.assertEqual(ops_control.read()["mode"], "ACTIVE")
        self.assertFalse(ops_control.read()["persisted"])
        self.assertTrue(ops_control.require_active())
        self.assertFalse(self.ops_path.exists())

    def test_explicit_confirmation_required_for_every_mutation(self):
        for mode in ("PAUSED", "ACTIVE"):
            with self.assertRaises(PermissionError):
                ops_control.set_mode(mode)
        with self.assertRaises(PermissionError):
            ops_control.set_mode("INVALID", confirm=True)
        self.assertFalse(self.ops_path.exists())

    def test_pause_blocks_skill_goal_and_scheduler_before_state_changes(self):
        planned = brain_planner.propose(
            "Read-only test", "campaign.review", {"dataset": "demo-local-test"},
            db_path=self.brain)
        brain_store.approve_goal(planned["goal_id"], planned["plan_sha256"],
                                 db_path=self.brain)
        out = ops_control.set_mode("PAUSED", confirm=True)
        self.assertTrue(out["persisted"])
        self.assertEqual(out["mode"], "PAUSED")
        with self.assertRaisesRegex(PermissionError, "OPERATIONS_PAUSED"):
            skill_runner.invoke("web.quality_check", {"slug": "nem-tu-van"},
                                db_path=self.tasks)
        with self.assertRaisesRegex(PermissionError, "OPERATIONS_PAUSED"):
            brain_runner.execute(planned["goal_id"], brain_db_path=self.brain,
                                 task_db_path=self.tasks)
        with self.assertRaisesRegex(PermissionError, "OPERATIONS_PAUSED"):
            brain_scheduler.tick(confirm_tick=True, db_path=self.brain,
                                 task_db_path=self.tasks)
        self.assertFalse(self.tasks.exists())
        self.assertEqual(brain_store.get_goal(planned["goal_id"],
                                             db_path=self.brain)["status"], "APPROVED")
        tick = ops_daemon.tick_once(db_path=self.brain, task_db_path=self.tasks,
                                   heartbeat_path=self.heartbeat)
        self.assertEqual(tick["status"], "OPERATIONS_PAUSED")
        self.assertEqual(tick["claimed"], [])
        self.assertEqual(ops_daemon.read_heartbeat(path=self.heartbeat)["status"], "PAUSED")
        self.assertFalse(self.tasks.exists())
        resumed = ops_control.set_mode("ACTIVE", confirm=True)
        self.assertEqual(resumed["mode"], "ACTIVE")
        self.assertTrue(ops_control.require_active())
        # Resuming does NOT execute the old approved Goal or create new tasks.
        self.assertFalse(self.tasks.exists())

    def test_corrupted_state_fails_closed_until_owner_resumes(self):
        self.ops_path.parent.mkdir(parents=True)
        self.ops_path.write_text("{bad json", encoding="utf-8")
        state = ops_control.read()
        self.assertEqual(state["mode"], "PAUSED")
        self.assertEqual(state["reason"], "INVALID_STATE")
        with self.assertRaisesRegex(PermissionError, "OPERATIONS_PAUSED"):
            ops_control.require_active()
        ops_control.set_mode("ACTIVE", confirm=True)
        self.assertEqual(ops_control.read()["mode"], "ACTIVE")

    def test_oversized_state_fails_closed(self):
        self.ops_path.parent.mkdir(parents=True)
        self.ops_path.write_bytes(b"x" * (ops_control.MAX_BYTES + 1))
        self.assertEqual(ops_control.read()["mode"], "PAUSED")


if __name__ == "__main__":
    unittest.main()
