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
                self.assertIsNone(final["artifact_acceptance"])
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
