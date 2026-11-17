import json
import unittest
from unittest.mock import patch

from agentforge import gateway, research_report
from tests import test_control_center_v1


class ResearchReportTests(unittest.TestCase):
    def test_http_approval_through_real_report_and_owner_acceptance(self):
        self._check_http_workflow("ollama", "_ollama_chat")

    def test_http_approval_through_cloud_report_and_owner_acceptance(self):
        self._check_http_workflow("anthropic", "_anthropic_chat")

    def _check_http_workflow(self, provider, transport):
        test = test_control_center_v1.TestControlCenterV1()
        test.setUp()
        try:
            test.login()
            test.server.allow_external_actions = True
            workspace = test.root / "workspace"
            (workspace / "docs").mkdir(parents=True)
            (workspace / "docs" / "runtime.md").write_text("Private local evidence", encoding="utf-8")
            url = "https://docs.python.org/3/library/pathlib.html"
            with patch.object(gateway, "WORKSPACE", workspace), \
                    patch("agentforge.workspace_policy.read", return_value={
                        "website_enabled": True, "storyboard_enabled": True,
                        "max_estimated_model_calls": 3}), \
                    patch.object(research_report, "_runtime", return_value={"model": "fixture:model", "provider": provider}), \
                    patch.object(research_report.model, transport, side_effect=[
                        json.dumps({"query": "Python filesystem documentation"}),
                        json.dumps({"file": 0, "source": 0}),
                        json.dumps({"markdown": "Evidence from [1] and [2]."}),
                    ]) as inference, \
                    patch.object(research_report.web_tools, "web_search", return_value=[
                        {"url": "https://unapproved.example/skip"}, {"url": url},
                    ]) as search, \
                    patch.object(research_report.source_reader, "fetch_page",
                                 return_value={"text_excerpt": "Public evidence"}) as fetch:
                code, planned, _ = test.req("POST", "/api/workspace/request", {
                    "ack": "PLAN_ONLY", "max_model_calls": 3,
                    "prompt": "Đọc Markdown trong workspace/docs, tra cứu về Python rồi tổng hợp báo cáo.",
                })
                self.assertEqual(code, 200, planned)
                self.assertEqual(planned["template"], "research.report")
                inference.assert_not_called()
                path = "/api/goals/" + planned["goal_id"]
                sha = test.req("GET", path)[1]["plan_sha256"]
                auth = {"plan_sha256": sha}
                self.assertEqual(test.req("POST", path + "/approve", {**auth, "ack": "APPROVE"})[0], 200)
                external = {"ack_external": "AUTHORIZE_EXTERNAL_TOOLS", "confirm_model_call": True}
                code, wait, _ = test.req("POST", path + "/run", {**auth, **external, "ack": "RUN",
                                                             "grants": ["model.invoke"]})
                self.assertEqual((code, wait["status"]), (200, "WAITING_APPROVAL"))
                inference.assert_not_called()
                revision = test.req("GET", path)[1]["updated_at"]
                code, done, _ = test.req("POST", path + "/resume", {
                    **auth, **external, "ack": "RESUME", "goal_updated_at": revision,
                    "grants": ["model.invoke", "workspace.write", "network.search", "network.read"],
                })
                self.assertEqual((code, done["status"]), (200, "SUCCEEDED"), done)
                self.assertEqual(inference.call_count, 3)
                prompts = [json.loads(call.args[1]) for call in inference.call_args_list]
                self.assertNotIn("Private local evidence", json.dumps(prompts[:2]))
                self.assertEqual(prompts[2]["[1]"], "Private local evidence")
                search.assert_called_once_with("Python filesystem documentation", limit=5)
                fetch.assert_called_once_with(url, allowed_hosts=research_report.PUBLIC_HOSTS)
                goal = test.req("GET", path)[1]
                acceptance = goal["artifact_acceptance"]
                self.assertEqual(acceptance["status"], "READY_FOR_REVIEW")
                report_path = "/api/artifacts/reports/" + goal["step_runs"][0]["child_task_id"]
                reviewed = test.req("GET", report_path)[1]
                output, = (workspace / "research-reports").glob("*.md")
                self.assertEqual(reviewed["content"], output.read_text(encoding="utf-8"))
                self.assertIn(url, reviewed["content"])
                code, accepted, _ = test.req("POST", report_path + "/decision", {
                    "ack": "ACCEPT_ARTIFACT", "sha256": acceptance["source_sha"],
                    "expected_revision": acceptance["revision"], "evidence_sha": acceptance["evidence_sha"],
                })
                self.assertEqual((code, accepted["status"]), (200, "ACCEPTED"))
        finally:
            test.tearDown()

    def test_cloud_process_override_requires_owner_consent(self):
        env = {
            "AGENTFORGE_MODEL_REF": "cloud_primary",
            "ANTHROPIC_BASE_URL": "https://gateway.example/v1",
            "ANTHROPIC_AUTH_TOKEN": "fixture-token",
        }
        with patch.dict("os.environ", env, clear=True), \
                patch.object(research_report.model, "load_dotenv"), \
                patch.object(research_report.runtime_health, "_http_json") as probe:
            with self.assertRaisesRegex(PermissionError, "CLOUD_MODEL_CONSENT_REQUIRED"):
                research_report._runtime()
            with patch.dict("os.environ", {"AGENTFORGE_CLOUD_MODEL_CONSENT": "YES"}):
                runtime = research_report._runtime()
            self.assertEqual(runtime["provider"], "anthropic")
            probe.assert_not_called()

    def test_unsafe_choices_and_unapproved_sources_are_rejected(self):
        for index in (-1, True, 1, "../../README.md"):
            with self.subTest(index=index), self.assertRaises(ValueError):
                research_report._choice(index, ["file.md"])
        urls = ["http://docs.python.org/3/", "https://docs.python.org/3/?data=1",
                "https://127.0.0.1/", "https://unknown.example/page"]
        self.assertEqual(research_report._sources([{"url": url} for url in urls]), [])
