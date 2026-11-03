import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import task_inbox


class TestTaskInbox(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp.name) / "company"
        self.patch = patch.object(task_inbox, "DATA_DIR", self.data_dir)
        self.patch.start()
        self.task_id = "a" * 32 + "-excel-automation-service-review"
        self.path = self.data_dir / "tasks" / (self.task_id.removesuffix("-review") + ".json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "task_id": self.task_id,
            "opportunity_id": "excel-automation-service",
            "kind": "SOURCE_REVIEW",
            "status": "PROPOSED",
            "source_urls": ["https://example.org/lead"],
            "execution_authorized": False,
            "spending_authorized": False,
        }), encoding="utf-8")

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_list_existing_task(self):
        tasks = task_inbox.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "PROPOSED")

    def test_defer_resume_and_permissions_stay_false(self):
        task = task_inbox.defer_task(self.task_id, "No direct customer evidence")
        self.assertEqual(task["status"], "DEFERRED")
        self.assertFalse(task["execution_authorized"])
        self.assertFalse(task["spending_authorized"])
        self.assertEqual(task_inbox.read_task(self.task_id)["status"], "DEFERRED")
        self.assertEqual(task_inbox.resume_task(self.task_id)["status"], "PROPOSED")
        self.assertEqual(len(task_inbox.read_task(self.task_id)["history"]), 2)

    def test_reject_invalid_id_and_path_traversal(self):
        for invalid in ("../outside", "a" * 32 + "-../outside-review", "x"):
            with self.assertRaises(ValueError):
                task_inbox.task_path(invalid)

    def test_refuses_unauthorized_permission_change(self):
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["spending_authorized"] = True
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(PermissionError):
            task_inbox.read_task(self.task_id)

    def test_invalid_transition_or_empty_reason(self):
        with self.assertRaises(ValueError):
            task_inbox.defer_task(self.task_id, " ")
        with self.assertRaises(ValueError):
            task_inbox.resume_task(self.task_id)


if __name__ == "__main__":
    unittest.main()
