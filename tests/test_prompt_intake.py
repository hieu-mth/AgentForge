"""Prompt-first workspace intake tests. No model calls or process execution."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge.prompt_intake import plan_request
from agentforge import brain_store
from agentforge.control_center_v1 import _owner_action


class PromptWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "goals.sqlite3"

    def test_landing_page_creates_owner_gated_plan_not_model_call(self):
        prompt = "Tạo landing page bán nệm cho gia đình, hotline 0879547988, trang đẹp mobile."
        with patch("agentforge.model.generate") as model:
            result = plan_request(prompt, brain_db_path=self.db)
            model.assert_not_called()
        self.assertEqual("PLAN_CREATED", result["status"])
        self.assertTrue(result["requires_owner_approval"])
        self.assertFalse(result["model_dispatched"])
        goal = brain_store.get_goal(result["goal_id"], db_path=self.db)
        self.assertEqual("PLANNED", goal["status"])
        self.assertEqual("website.draft", goal["template"])
        self.assertIn("0879547988", goal["inputs"]["brief"])
        self.assertEqual("web.create", goal["plan"][0]["skill_id"])

    def test_extended_owner_brief_uses_characters_not_words(self):
        from agentforge.prompt_intake import MAX_PROMPT
        self.assertEqual(MAX_PROMPT, 6000)
        prompt = "Tạo website tư vấn nệm tại Việt Nam. " + ("Nội dung chi tiết tiếng Việt. " * 175)
        self.assertGreater(len(prompt), 600)
        self.assertLessEqual(len(prompt), MAX_PROMPT)
        with patch("agentforge.model.generate_json") as model:
            submitted = plan_request(prompt, brain_db_path=self.db)
            model.assert_not_called()
        goal = brain_store.get_goal(submitted["goal_id"], db_path=self.db)
        self.assertEqual(goal["inputs"]["brief"], prompt.strip())
        self.assertEqual(goal["plan"][0]["payload"]["brief"], prompt.strip())
        with self.assertRaises(ValueError):
            plan_request("Tạo website " + "x" * MAX_PROMPT, brain_db_path=self.db)

    def test_unknown_or_multiple_intents_do_not_create_goal(self):
        for prompt in ("Hãy giúp tôi vận hành toàn bộ doanh nghiệp và tự mua quảng cáo",
                       "Tạo landing page và kịch bản video quảng cáo nệm ngay lập tức"):
            result = plan_request(prompt, brain_db_path=self.db)
            self.assertEqual("NEEDS_CLARIFICATION", result["status"])

    def test_external_process_or_invalid_budget_rejected(self):
        prompt = "Tạo website giới thiệu nệm ngủ cho gia đình thật chuyên nghiệp"
        with self.assertRaises(PermissionError):
            plan_request(prompt, max_external_runs=1, brain_db_path=self.db)
        with self.assertRaises(ValueError):
            plan_request(prompt, max_model_calls=0, brain_db_path=self.db)

    def test_builder_error_codes_do_not_echo_untrusted_text(self):
        from agentforge.skill_runner import _safe_failure
        marker = "private-raw-model-output"
        messages = [
            (ValueError("Builder HTML appears truncated " + marker), "HTML_INCOMPLETE"),
            (ValueError("Static quality gate FAIL: " + marker), "HTML_QUALITY_FAILED"),
            (ValueError("Generated HTML too large " + marker), "HTML_TOO_LARGE"),
            (RuntimeError(marker), "BUILDER_EXECUTION_FAILED"),
        ]
        for error, code in messages:
            output = _safe_failure("web.create", error)
            self.assertTrue(output.startswith(code), output)
            self.assertNotIn(marker, output)

    def test_api_rejects_invalid_ack_and_extra_fields(self):
        with self.assertRaises(PermissionError):
            _owner_action(None, "/api/workspace/request",
                          {"ack": "RUN", "prompt": "Tạo landing page cho nệm ngủ",
                           "max_model_calls": 1})
        with self.assertRaises(PermissionError):
            _owner_action(None, "/api/workspace/request",
                          {"ack": "PLAN_ONLY", "prompt": "Tạo landing page cho nệm ngủ",
                           "max_model_calls": 1, "grants": ["model.invoke"]})


if __name__ == "__main__":
    unittest.main()
