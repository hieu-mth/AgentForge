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

    def test_cancel_paused_workflow_keeps_receipts_and_prevents_resume(self):
        from agentforge import skill_runner, task_history

        server = test_control_center_v1.TestControlCenterV1()
        server.setUp()
        self.addCleanup(server.tearDown)
        server.login()
        workspace = server.root / "workspace"
        workspace.mkdir()
        with patch.object(gateway, "WORKSPACE", workspace):
            code, result, _ = server.req("POST", "/api/goals/propose", {
                "ack": "PROPOSE", "title": "Cancel after one report",
                "template": "workflow.compose",
                "inputs": {"steps": [report("reports/a.md"), report("reports/b.md")]},
            })
            self.assertEqual(code, 200, result)
            endpoint = "/api/goals/" + result["goal_id"]
            initial = server.req("GET", endpoint)[1]
            params = {"plan_sha256": initial["plan_sha256"]}
            self.assertEqual(server.req("POST", endpoint + "/approve", {
                **params, "ack": "APPROVE",
            })[0], 200)
            code, run, _ = server.req("POST", endpoint + "/run", {
                **params, "ack": "RUN", "grants": ["workspace.write"],
            })
            self.assertEqual((code, run["status"]), (200, "WAITING_APPROVAL"))
            current = server.req("GET", endpoint)[1]
            child = current["step_runs"][1]["child_task_id"]
            with self.assertRaises(PermissionError):
                skill_runner.resume_waiting(child, grants=["workspace.write"], db_path=server.taskdb)
            cancel = {**params, "ack": "CANCEL_PENDING_GOAL"}
            self.assertEqual(server.req("POST", endpoint + "/cancel", {
                **cancel, "goal_updated_at": initial["updated_at"],
            })[0], 400)
            code, receipt, _ = server.req("POST", endpoint + "/cancel", {
                **cancel, "goal_updated_at": current["updated_at"],
            })
            self.assertEqual((code, receipt["status"]), (200, "CANCELLED"), receipt)
            self.assertEqual(task_history.get_task(child, db_path=server.taskdb)["status"], "CANCELLED")
            self.assertEqual(server.req("POST", endpoint + "/resume", {
                **params, "ack": "RESUME", "goal_updated_at": receipt["updated_at"],
                "grants": ["workspace.write"],
            })[0], 400)
            self.assertTrue((workspace / "reports/a.md").is_file())
            self.assertFalse((workspace / "reports/b.md").exists())

    def test_rejected_report_can_be_revised_as_new_immutable_artifact(self):
        server = test_control_center_v1.TestControlCenterV1()
        server.setUp()
        self.addCleanup(server.tearDown)
        server.login()
        workspace = server.root / "workspace"
        workspace.mkdir()

        def execute(goal_id):
            endpoint = "/api/goals/" + goal_id
            goal = server.req("GET", endpoint)[1]
            sha = {"plan_sha256": goal["plan_sha256"]}
            self.assertEqual(server.req("POST", endpoint + "/approve", {
                **sha, "ack": "APPROVE",
            })[0], 200)
            status, receipt, _ = server.req("POST", endpoint + "/run", {
                **sha, "ack": "RUN", "grants": ["workspace.write"],
            })
            self.assertEqual((status, receipt["status"]), (200, "SUCCEEDED"), receipt)
            return server.req("GET", endpoint)[1]["step_runs"][0]["child_task_id"]

        def decide(path, doc, decision):
            acceptance = doc["artifact_acceptance"]
            return server.req("POST", path + "/decision", {
                "ack": decision, "sha256": doc["sha256"],
                "expected_revision": acceptance["revision"],
                "evidence_sha": acceptance["evidence_sha"],
            })

        with patch.object(gateway, "WORKSPACE", workspace):
            status, goal, _ = server.req("POST", "/api/goals/propose", {
                "ack": "PROPOSE", "title": "Source report", **report("reports/a.md"),
            })
            self.assertEqual(status, 200, goal)
            source_id = execute(goal["goal_id"])
            endpoint = "/api/artifacts/reports/" + source_id
            source = server.req("GET", endpoint)[1]
            body = {"ack": "PROPOSE_REPORT_REVISION", "sha256": source["sha256"], "content": "Corrected"}
            self.assertEqual(server.req("POST", endpoint + "/revise", body)[0], 400)
            self.assertEqual(decide(endpoint, source, "REJECT_ARTIFACT")[0], 200)
            status, draft, _ = server.req("POST", endpoint + "/revise", body)
            self.assertEqual(status, 200, draft)
            revised = "/api/artifacts/reports/" + execute(draft["goal_id"])
            new = server.req("GET", revised)[1]
            self.assertEqual(new["content"], "Corrected")
            self.assertNotEqual(source["sha256"], new["sha256"])
            self.assertEqual((workspace / "reports/a.md").read_text(), "Evidence")
            self.assertEqual(decide(revised, new, "ACCEPT_ARTIFACT")[1]["status"], "ACCEPTED")
