import json
import unittest
from unittest.mock import patch

from agentforge import gateway, research_report
from tests import test_control_center_v1


class ResearchReportTests(unittest.TestCase):
    def test_retired_workspace_http_does_not_invoke_report_model(self):
        from tests.owner_http_fixture import OwnerHttpFixture
        fixture = OwnerHttpFixture("test_noop")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.login()
        with patch("agentforge.model._ollama_chat") as local, \
             patch("agentforge.model._anthropic_chat") as cloud:
            code, _, _ = fixture.req("POST", "/api/workspace/request", {
                "ack": "PLAN_ONLY", "max_model_calls": 1,
                "prompt": "Summarize evidence"})
            self.assertEqual(code, 400)
            local.assert_not_called()
            cloud.assert_not_called()



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
