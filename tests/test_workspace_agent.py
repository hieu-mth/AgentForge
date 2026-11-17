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
    def test_owner_goal_observes_search_then_reads_another_file_and_accepts(self):
        server = test_control_center_v1.TestControlCenterV1()
        server.setUp()
        self.addCleanup(server.tearDown)
        server.login()
        server.server.allow_external_actions = True
        root = server.root / "workspace"
        scope = root / "notes"
        scope.mkdir(parents=True)
        (scope / "policy.md").write_text("Timeout is 60 seconds. See runbook.", encoding="utf-8")
        (scope / "runbook.md").write_text("Restart only after checking active jobs.", encoding="utf-8")

        def inference(_runtime, serialized, _schema, **limits):
            request = json.loads(serialized)
            self.assertIn("timeout_seconds", limits)
            self.assertIn("max_output_tokens", limits)
            if request.get("prior_actions") == []:
                return json.dumps(action("search", -1, query="Timeout"))
            if request.get("prior_actions"):
                self.assertIn("60 seconds", request["evidence"][0]["excerpt"])
                self.assertEqual(request["prior_actions"][0]["tool"], "search")
                return json.dumps(action("read", 1, line=1))
            self.assertIn("active jobs", request["evidence"][1]["excerpt"])
            return json.dumps({"markdown": "Timeout is 60 seconds [1]. Check active jobs [2]."})

        runtime = {"model": "fixture", "provider": "ollama"}
        with (patch.object(gateway, "WORKSPACE", root),
              patch("agentforge.workspace_policy.read", return_value={"max_estimated_model_calls": 3}),
              patch("agentforge.research_report._runtime", return_value=runtime) as resolve,
              patch("agentforge.model._ollama_chat", side_effect=inference) as model):
            status, plan, _ = server.req("POST", "/api/workspace/request", {
                "ack": "PLAN_ONLY", "max_model_calls": 3,
                "prompt": "Đối chiếu quy định timeout và hướng dẫn xử lý trong workspace/notes.",
            })
            self.assertEqual(status, 200, plan)
            self.assertEqual(plan["template"], "workspace.analyze")
            model.assert_not_called()
            endpoint = "/api/goals/" + plan["goal_id"]
            auth = {"plan_sha256": server.req("GET", endpoint)[1]["plan_sha256"]}
            self.assertEqual(server.req("POST", endpoint + "/approve", {
                **auth, "ack": "APPROVE",
            })[0], 200)
            grants = {"grants": ["model.invoke", "workspace.write"],
                      "ack_external": "AUTHORIZE_EXTERNAL_TOOLS"}
            status, blocked, _ = server.req("POST", endpoint + "/run", {
                **auth, **grants, "ack": "RUN",
            })
            self.assertEqual((status, blocked["status"]), (200, "WAITING_APPROVAL"), blocked)
            model.assert_not_called()
            status, done, _ = server.req("POST", endpoint + "/resume", {
                **auth, **grants, "ack": "RESUME", "confirm_model_call": True,
                "goal_updated_at": server.req("GET", endpoint)[1]["updated_at"],
            })
            self.assertEqual((status, done["status"]), (200, "SUCCEEDED"), done)
            self.assertEqual(model.call_count, 3)
            resolve.assert_called_once_with(allow_cloud=False)
            goal = server.req("GET", endpoint)[1]
            self.assertEqual(goal["artifact_acceptance"]["status"], "READY_FOR_REVIEW")
            task = goal["step_runs"][0]["child_task_id"]
            artifact = "/api/artifacts/reports/" + task
            reviewed = server.req("GET", artifact)[1]
            self.assertIn("workspace/notes/policy.md", reviewed["content"])
            self.assertIn("workspace/notes/runbook.md", reviewed["content"])
            receipt = goal["artifact_acceptance"]
            status, accepted, _ = server.req("POST", artifact + "/decision", {
                "ack": "ACCEPT_ARTIFACT", "sha256": receipt["source_sha"],
                "expected_revision": receipt["revision"], "evidence_sha": receipt["evidence_sha"],
            })
            self.assertEqual((status, accepted["status"]), (200, "ACCEPTED"))

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
