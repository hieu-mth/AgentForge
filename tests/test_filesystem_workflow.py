"""Owner HTTP workflow with real filesystem writes in an isolated workspace."""
import hashlib
import unittest
from unittest.mock import patch

from agentforge import gateway
from tests import test_control_center_v1


class FilesystemWorkflowTests(unittest.TestCase):
    def test_retired_workspace_intake_cannot_write_or_start_task(self):
        from tests.owner_http_fixture import OwnerHttpFixture
        fixture = OwnerHttpFixture("test_noop")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.login()
        folder = fixture.brain.parent / "workspace"
        with patch.object(gateway, "WORKSPACE", folder):
            code, _, _ = fixture.req("POST", "/api/workspace/request", {
                "ack": "PLAN_ONLY", "max_model_calls": 0,
                "prompt": "Tạo báo cáo workspace/e2e-test/report.md"})
        self.assertEqual(code, 400)
        self.assertFalse(folder.exists())
        self.assertFalse(fixture.tasks.exists())

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
