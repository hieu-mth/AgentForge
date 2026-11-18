import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agentforge import gateway, workspace_agent
from tests import test_control_center_v1


def action(tool, file, line=0, query=""):
    return {"tool": tool, "file": file, "start_line": line, "query": query}


class WorkspaceAgentTests(unittest.TestCase):
    def test_retired_workspace_owner_goal_does_not_start_model(self):
        from tests.owner_http_fixture import OwnerHttpFixture
        fixture = OwnerHttpFixture("test_noop")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.login()
        fixture.server.allow_external_actions = True
        with patch("agentforge.model._ollama_chat") as model:
            code, _, _ = fixture.req("POST", "/api/workspace/request", {
                "ack": "PLAN_ONLY", "max_model_calls": 3,
                "prompt": "Đối chiếu timeout và runbook"})
            self.assertEqual(code, 400)
            model.assert_not_called()

    def test_bad_tool_arguments_and_sources_stop_publication(self):
        with TemporaryDirectory() as tmp, patch.object(gateway, "WORKSPACE", Path(tmp)):
            scope = Path(tmp) / "notes"
            scope.mkdir()
            (scope / "a.md").write_text("source text", encoding="utf-8")
            cases = [
                ([action("read", "../outside", 1)], "INVALID_ACTION"),
                ([action("exec", 0, 1)], "INVALID_ACTION"),
                ([action("read", 0, 1), action("read", 0, 1)], "REPEATED_ACTION"),
                ([action("read", 0, 1), action("search", 0, query="source"),
                  {"markdown": "Invented [9]."}], "INVALID_REPORT"),
            ]
            for responses, error in cases:
                with (self.subTest(error=error),
                      patch("agentforge.research_report._runtime", return_value={"model": "fixture"}),
                      patch("agentforge.research_report._ask", side_effect=responses),
                      self.assertRaisesRegex(ValueError, error)):
                    workspace_agent.run("Summarize these approved notes.", "notes",
                                        "agent-reports/" + "a" * 32 + ".md")
            self.assertFalse((Path(tmp) / "agent-reports").exists())

    @unittest.skipUnless(os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"),
                         "requires POSIX no-follow path walk")
    def test_read_refuses_parent_symlink_inserted_after_validation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "report.md").write_text("secret", encoding="utf-8")
            folder = root / "notes"
            folder.mkdir(parents=True)
            file = folder / "report.md"
            file.write_text("original", encoding="utf-8")

            def replaced_after_check(_):
                folder.rename(root / "old")
                folder.symlink_to(outside, target_is_directory=True)
                return file

            with (patch.object(gateway, "WORKSPACE", root),
                  patch.object(gateway, "safe_path", side_effect=replaced_after_check),
                  self.assertRaises(OSError)):
                gateway.read_file("notes/report.md")

    @unittest.skipUnless(os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW")
                         and {os.mkdir, os.link, os.unlink} <= os.supports_dir_fd,
                         "requires POSIX anchored report write")
    def test_report_does_not_publish_into_parent_replaced_by_symlink(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            outside = Path(tmp) / "outside"
            outside.mkdir()
            parent = root / "reports"
            parent.mkdir(parents=True)
            original_write = gateway._write_report_at

            def replaced_after_check(path, target, raw):
                parent.rename(root / "old")
                parent.symlink_to(outside, target_is_directory=True)
                return original_write(path, target, raw)

            with (patch.object(gateway, "WORKSPACE", root),
                  patch.object(gateway, "_write_report_at", side_effect=replaced_after_check),
                  self.assertRaises(OSError)):
                gateway.write_verified_report("reports/report.md", "approved content")
            self.assertFalse(list(outside.iterdir()))
