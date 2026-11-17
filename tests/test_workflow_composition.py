"""Exercise a composed owner workflow through HTTP and actual local tools."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agentforge import brain_planner, gateway
from tests import test_control_center_v1


def report(path):
    return {"template": "filesystem.report", "inputs": {"path": path, "content": "Evidence"}}


class WorkflowCompositionTests(unittest.TestCase):
    def test_rejects_recursive_duplicates_and_unbudgeted_tools(self):
        with TemporaryDirectory() as tmp, patch.object(gateway, "WORKSPACE", Path(tmp)):
            (Path(tmp) / "fixtures").mkdir()
            step = report("reports/test.md")
            with self.assertRaisesRegex(ValueError, "distinct"):
                brain_planner.make_plan("workflow.compose", {"steps": [step, step]})
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                brain_planner.make_plan("workflow.compose", {"steps": [step, {
                    "template": "workflow.compose", "inputs": {"steps": []}}]})
            with self.assertRaisesRegex(ValueError, "cap"):
                brain_planner.make_plan("workflow.compose", {"steps": [step, {
                    "template": "terminal.check",
                    "inputs": {"recipe": "python-version", "directory": "fixtures"},
                }]})

    def test_step_permission_is_not_inherited_and_previous_step_is_not_replayed(self):
        server = test_control_center_v1.TestControlCenterV1()
        server.setUp()
        self.addCleanup(server.tearDown)
        server.login()
        workspace = server.root / "workspace"
        workspace.mkdir()
        with patch.object(gateway, "WORKSPACE", workspace):
            code, result, _ = server.req("POST", "/api/goals/propose", {
                "ack": "PROPOSE", "title": "Two Markdown reports",
                "template": "workflow.compose",
                "inputs": {"steps": [report("reports/a.md"), report("reports/b.md")]},
            })
            self.assertEqual(code, 200, result)
            endpoint = "/api/goals/" + result["goal_id"]
            goal = server.req("GET", endpoint)[1]
            params = {"plan_sha256": goal["plan_sha256"]}
            self.assertEqual(server.req("POST", endpoint + "/approve", {
                **params, "ack": "APPROVE",
            })[0], 200)
            code, run, _ = server.req("POST", endpoint + "/run", {
                **params, "ack": "RUN", "grants": ["workspace.write"],
            })
            self.assertEqual((code, run["status"]), (200, "WAITING_APPROVAL"), run)
            self.assertTrue((workspace / "reports/a.md").is_file())
            self.assertFalse((workspace / "reports/b.md").exists())
            goal = server.req("GET", endpoint)[1]
            a_id = goal["step_runs"][0]["child_task_id"]
            code, run, _ = server.req("POST", endpoint + "/resume", {
                **params, "ack": "RESUME", "goal_updated_at": goal["updated_at"],
                "grants": ["workspace.write"],
            })
            self.assertEqual((code, run["status"]), (200, "SUCCEEDED"), run)
            self.assertEqual((workspace / "reports/b.md").read_text(), "Evidence")
            self.assertEqual(server.req("GET", endpoint)[1]["step_runs"][0]["child_task_id"], a_id)
