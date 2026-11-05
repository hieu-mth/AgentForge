"""V2.6 owner revision workflow: SHA-bound feedback, gated planner, no model call."""
import unittest
from unittest.mock import patch

from agentforge import website_feedback as feedback
from agentforge.control_center_v1 import _owner_action


class WebsiteFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.proposal_id = "a" * 32
        self.sha = "b" * 64
        self.doc = {
            "sha256": self.sha,
            "brief": "Tạo trang nệm cao cấp, màu kem, hotline 0879547988.",
            "status": "PROPOSED_NOT_APPLIED",
        }
        self.policy = {"website_enabled": True, "max_estimated_model_calls": 1}

    def test_feedback_creates_new_goal_without_calling_model_or_mutating_source(self):
        comment = "Tăng độ nổi bật của hình nệm và làm hero hiện đại hơn."
        with patch("agentforge.product_builder._read_proposal", return_value=(self.doc, "proposal-path")), \
             patch("agentforge.workspace_policy.read", return_value=self.policy), \
             patch("agentforge.goal_preflight.require_ready"), \
             patch("agentforge.brain_planner.propose", return_value={"goal_id": "c" * 32}) as propose, \
             patch("agentforge.model.generate") as generate:
            result = feedback.request_revision(self.proposal_id, self.sha, comment)
        generate.assert_not_called()
        self.assertEqual("PLAN_CREATED", result["status"])
        self.assertTrue(result["original_preserved"])
        self.assertFalse(result["model_dispatched"])
        self.assertTrue(result["approval_required"])
        self.assertEqual(self.proposal_id, result["original_proposal_id"])
        arguments = propose.call_args
        self.assertEqual("website.draft", arguments.args[1])
        self.assertEqual(1, arguments.kwargs["max_model_calls"])
        self.assertEqual(0, arguments.kwargs["max_external_runs"])
        self.assertIn(comment, arguments.args[2]["brief"])
        self.assertIn("0879547988", arguments.args[2]["brief"])
        self.assertTrue(arguments.args[2]["slug"].startswith("rev-"))

    def test_feedback_limit_retains_last_char(self):
        full = "z" * feedback.MAX_FEEDBACK
        with patch("agentforge.product_builder._read_proposal", return_value=(self.doc, None)), \
             patch("agentforge.workspace_policy.read", return_value=self.policy), \
             patch("agentforge.goal_preflight.require_ready"), \
             patch("agentforge.brain_planner.propose", return_value={"goal_id": "c"*32}) as propose:
            feedback.request_revision(self.proposal_id, self.sha, full)
        brief = propose.call_args.args[2]["brief"]
        self.assertLessEqual(len(brief), 600)
        self.assertTrue(brief.endswith(full))

    def test_policy_and_sha_fail_closed(self):
        with patch("agentforge.product_builder._read_proposal", return_value=(self.doc, None)):
            with self.assertRaises(PermissionError):
                feedback.request_revision(self.proposal_id, "c"*64, "Đổi màu nền sang trắng.")
            with patch("agentforge.workspace_policy.read",
                       return_value={"website_enabled": False, "max_estimated_model_calls": 1}):
                with self.assertRaises(PermissionError):
                    feedback.request_revision(self.proposal_id, self.sha, "Đổi màu nền sang trắng.")
            with self.assertRaises(ValueError):
                feedback.request_revision(self.proposal_id, self.sha, "ngắn")

    def test_owner_api_requires_exact_ack_and_inspected_sha(self):
        route = "/api/proposals/" + self.proposal_id + "/revision"
        data = {"ack": "REQUEST_REVISION", "sha256": self.sha,
                "feedback": "Tăng hình ảnh nệm ở hero lên rõ hơn"}
        with patch("agentforge.website_feedback.request_revision",
                   return_value={"status": "PLAN_CREATED"}) as maker:
            with self.assertRaises(PermissionError):
                _owner_action(None, route, data, session={})
            with self.assertRaises(PermissionError):
                _owner_action(None, route, {**data, "ack": "EXECUTE"},
                              session={"reviewed_proposals": {self.proposal_id: self.sha}})
            with self.assertRaises(ValueError):
                _owner_action(None, route, {**data, "danger": "publish"},
                              session={"reviewed_proposals": {self.proposal_id: self.sha}})
            receipt = _owner_action(None, route, data,
                                    session={"reviewed_proposals": {self.proposal_id: self.sha}})
            self.assertEqual("PLAN_CREATED", receipt["status"])
            maker.assert_called_once()
            maker_args = maker.call_args
            self.assertEqual((self.proposal_id, self.sha, data["feedback"]), maker_args.args)


if __name__ == "__main__":
    unittest.main()
