import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import gateway


class TestToolGateway(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(
            gateway,
            "WORKSPACE",
            Path(self.temp.name).resolve()
        )
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_authorized_write_and_read(self):
        result = gateway.execute_tool(
            "write_file",
            {
                "path": "reports/test.txt",
                "content": "AgentForge works"
            }
        )

        self.assertEqual(result["status"], "created")

        content = gateway.execute_tool(
            "read_file",
            {"path": "reports/test.txt"}
        )

        self.assertEqual(content, "AgentForge works")

    def test_prevent_path_traversal(self):
        with self.assertRaises(PermissionError):
            gateway.read_file("../company.json")

    def test_prevent_absolute_path(self):
        with self.assertRaises(PermissionError):
            gateway.read_file(r"C:\Windows\win.ini")

    def test_prevent_unknown_tools(self):
        with self.assertRaises(PermissionError):
            gateway.execute_tool(
                "run_shell",
                {"command": "whoami"}
            )

    def test_idempotent_write(self):
        arguments = {
            "path": "reports/result.txt",
            "content": "Verified result"
        }

        first = gateway.execute_tool(
            "write_file", arguments
        )
        second = gateway.execute_tool(
            "write_file", arguments
        )

        self.assertEqual(first["status"], "created")
        self.assertEqual(
            second["status"],
            "already_exists_same_content"
        )

    def test_reject_conflicting_write(self):
        gateway.write_file("result.txt", "original")

        with self.assertRaises(RuntimeError):
            gateway.write_file("result.txt", "changed")


if __name__ == "__main__":
    unittest.main()
