"""Owner HTTP workflow with real filesystem writes in an isolated workspace."""
import hashlib
import unittest
from unittest.mock import patch

from agentforge import gateway
from tests import test_control_center_v1


class FilesystemWorkflowTests(unittest.TestCase):
    def test_request_approval_write_and_artifact_evidence(self):
        test = test_control_center_v1.TestControlCenterV1()
        test.setUp()
        try:
            test.login()
            workspace = test.root / "workspace"
            raw = "# Báo cáo\n\nDữ liệu kiểm thử.".encode()
            with patch.object(gateway, "WORKSPACE", workspace):
                code, result, _ = test.req("POST", "/api/workspace/request", {
                    "ack": "PLAN_ONLY", "max_model_calls": 0,
                    "prompt": "Tạo báo cáo workspace/e2e-test/report.md với nội dung: " + raw.decode(),
                })
                self.assertEqual(code, 200, result)
                path = "/api/goals/" + result["goal_id"]
                goal = test.req("GET", path)[1]
                auth = {"plan_sha256": goal["plan_sha256"]}
                self.assertEqual(goal["plan"][0]["skill_id"], "filesystem.report")
                self.assertFalse(workspace.exists())
                self.assertEqual(test.req("POST", path + "/approve", {**auth, "ack": "APPROVE"})[0], 200)
                self.assertFalse(workspace.exists())
                code, blocked, _ = test.req("POST", path + "/run", {**auth, "ack": "RUN", "grants": []})
                self.assertEqual((code, blocked["status"]), (200, "WAITING_APPROVAL"))
                self.assertFalse(workspace.exists())
                observed = test.req("GET", path)[1]
                code, outcome, _ = test.req("POST", path + "/resume", {
                    **auth, "ack": "RESUME", "goal_updated_at": observed["updated_at"],
                    "grants": ["workspace.write"],
                })
                self.assertEqual((code, outcome["status"]), (200, "SUCCEEDED"))
                self.assertEqual((workspace / "e2e-test" / "report.md").read_bytes(), raw)
                final = test.req("GET", path)[1]
                step = final["step_runs"][0]
                task = test.req("GET", "/api/tasks/" + step["child_task_id"])[1]
                self.assertEqual(task["report"]["report_path"], "workspace/e2e-test/report.md")
                self.assertEqual(task["report"]["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(task["report"]["status"], "VERIFIED")
                self.assertEqual(final["artifact_acceptance"]["status"], "READY_FOR_REVIEW")
                acceptance = final["artifact_acceptance"]
                decision = {"ack": "ACCEPT_ARTIFACT", "sha256": acceptance["source_sha"],
                            "expected_revision": acceptance["revision"],
                            "evidence_sha": acceptance["evidence_sha"]}
                report_path = "/api/artifacts/reports/" + step["child_task_id"]
                self.assertEqual(test.req("POST", report_path + "/decision", decision)[0], 400)
                code, reviewed, _ = test.req("GET", report_path)
                self.assertEqual(code, 200, reviewed)
                self.assertEqual(reviewed["content"], raw.decode())
                file = workspace / "e2e-test" / "report.md"
                file.write_bytes(b"changed")
                self.assertEqual(test.req("POST", report_path + "/decision", decision)[0], 400)
                self.assertEqual(test.req("GET", path)[1]["artifact_acceptance"]["status"],
                                 "NEEDS_VALIDATION")
                file.write_bytes(raw)
                code, accepted, _ = test.req("POST", report_path + "/decision", decision)
                self.assertEqual((code, accepted["status"]), (200, "ACCEPTED"))
                self.assertEqual(test.req("GET", path)[1]["artifact_acceptance"]["status"], "ACCEPTED")
        finally:
            test.tearDown()

    def test_no_overwrite_and_no_link_or_path_escape(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            with patch.object(gateway, "WORKSPACE", workspace):
                first = gateway.write_verified_report("reports/output.md", "First")
                self.assertEqual(gateway.write_verified_report("reports/output.md", "First"), first)
                with self.assertRaises(FileExistsError):
                    gateway.write_verified_report("reports/output.md", "Different")
                for path in ("../report.md", "reports/AUX.md", "reports/out.md:stream", "//host/share/out.md"):
                    with self.subTest(path=path), self.assertRaises((ValueError, PermissionError)):
                        gateway.write_verified_report(path, "Unsafe")
                victim = root / "external"
                victim.mkdir()
                try:
                    (workspace / "linked").symlink_to(victim, target_is_directory=True)
                except OSError:
                    return  # Developer mode may be disabled on Windows.
                with self.assertRaises(PermissionError):
                    gateway.write_verified_report("linked/output.md", "Unsafe")
                self.assertFalse(list(victim.iterdir()))

    def test_approved_terminal_runs_real_process_in_workspace(self):
        test = test_control_center_v1.TestControlCenterV1()
        test.setUp()
        try:
            test.login()
            workspace = test.root / "workspace"
            (workspace / "e2e-test").mkdir(parents=True)
            with patch.object(gateway, "WORKSPACE", workspace):
                request = {"ack": "PROPOSE", "title": "Check local Python",
                           "template": "terminal.check", "max_external_runs": 1,
                           "inputs": {"recipe": "python-version", "directory": "e2e-test"}}
                path = "/api/goals/propose"
                unsafe = {**request, "inputs": {**request["inputs"], "recipe": "python -c ..."}}
                self.assertEqual(test.req("POST", path, unsafe)[0], 400)
                code, goal, _ = test.req("POST", path, request)
                self.assertEqual((code, goal["status"]), (200, "PLANNED"))
                path = "/api/goals/" + goal["goal_id"]
                auth = {"plan_sha256": goal["plan_sha256"]}
                self.assertEqual(test.req("POST", path + "/approve", {**auth, "ack": "APPROVE"})[0], 200)
                execution = {**auth, "ack": "RUN", "grants": ["process.run"],
                             "ack_external": "AUTHORIZE_EXTERNAL_TOOLS", "confirm_external_run": True}
                self.assertEqual(test.req("POST", path + "/run", execution)[0], 400)
                test.server.allow_external_actions = True
                code, outcome, _ = test.req("POST", path + "/run", execution)
                self.assertEqual((code, outcome["status"]), (200, "SUCCEEDED"))
                child = test.req("GET", path)[1]["step_runs"][0]["child_task_id"]
                receipt = test.req("GET", "/api/tasks/" + child)[1]["report"]
                self.assertEqual((receipt["recipe"], receipt["exit_code"], receipt["stderr"]),
                                 ("python-version", 0, ""))
                self.assertTrue(receipt["stdout"].startswith("Python "))
        finally:
            test.tearDown()

    def test_timeout_has_failed_receipt_and_bounded_output(self):
        import subprocess
        import tempfile
        from pathlib import Path
        from agentforge import skill_runner, task_history
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            (workspace / "test").mkdir(parents=True)
            database = root / "tasks.db"
            with patch.object(gateway, "WORKSPACE", workspace), patch.object(
                    gateway.subprocess, "run",
                    side_effect=subprocess.TimeoutExpired("test", 5, output=b"a" * 4096)):
                result = skill_runner.invoke("terminal.check",
                    {"recipe": "python-version", "directory": "test", "confirm_external_run": True},
                    grants=["process.run"], confirm_external_run=True, db_path=database)
            self.assertEqual(result["status"], "FAILED")
            task = task_history.get_task(result["task_id"], db_path=database)
            self.assertEqual(task["error"], "TERMINAL_TIMEOUT")
            self.assertEqual(len(task["result"]["stdout"]), 2048)
