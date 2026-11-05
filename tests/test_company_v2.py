"""V2 dashboard action and operating-scorecard regression tests (no model/network)."""
import unittest
from unittest.mock import patch

from agentforge import company_v2
from agentforge.control_center_v1 import _owner_action


class V2CompanyTests(unittest.TestCase):
    def test_company_report_never_invents_verified_revenue(self):
        policy = {"enabled": True, "daily_cap": 1}
        autopilot = {"used_today": 1, "jobs": []}
        inbox = {"business_context": {"business": "Tư vấn nệm ngủ"},
                 "reviews": [{"decision": "PENDING"}, {"decision": "APPROVED"}]}
        videos = {"productions": [{"status": "VIDEO_READY"},
                                   {"status": "APPROVED"}]}
        camps = [{"campaign": "nem-ngu", "synthetic": False}]
        stats = {"lead_total": 3, "owner_reported_posts": 1,
                 "owner_recorded_net_cash_vnd": 100000}
        with patch("agentforge.autopilot_v13.policy", return_value=policy), \
             patch("agentforge.autopilot_v13.report", return_value=autopilot), \
             patch("agentforge.quality_v14.inbox", return_value=inbox), \
             patch("agentforge.media_workflow_v15.report", return_value=videos), \
             patch("agentforge.growth_store.list_campaigns", return_value=camps), \
             patch("agentforge.growth_reports.report", return_value=stats), \
             patch("agentforge.ops_control.read", return_value={"mode": "ACTIVE"}):
            result = company_v2.report()
        self.assertEqual("2.0", result["version"])
        self.assertEqual(1, result["content"]["pending_ai_reviews"])
        self.assertEqual(1, result["content"]["owner_approved_local_videos"])
        self.assertEqual(3, result["business"]["owner_recorded_leads"])
        self.assertIsNone(result["business"]["bank_verified_profit_vnd"])
        self.assertFalse(result["real_business_validated"])
        self.assertFalse(result["automated_publication"])
        self.assertFalse(result["autonomous_financial_actions"])

    def test_no_campaign_blocks_real_business_validation(self):
        with patch("agentforge.autopilot_v13.policy", return_value={
            "enabled": False, "daily_cap": 0
        }), patch("agentforge.autopilot_v13.report", return_value={
            "used_today": 0
        }), patch("agentforge.quality_v14.inbox", return_value={
            "business_context": None, "reviews": []
        }), patch("agentforge.media_workflow_v15.report", return_value={
            "productions": []
        }), patch("agentforge.growth_store.list_campaigns", return_value=[]), \
             patch("agentforge.ops_control.read", return_value={"mode": "PAUSED"}):
            result = company_v2.report()
        self.assertIn("SET_BUSINESS_CONTEXT", result["launch_blockers"])
        self.assertIn("CREATE_REAL_CAMPAIGN", result["launch_blockers"])
        self.assertIn("OPERATIONS_PAUSED", result["launch_blockers"])

    def test_autopilot_configuration_requires_exact_ack(self):
        with patch("agentforge.autopilot_v13.configure", return_value={
            "enabled": False, "daily_cap": 0
        }) as configure:
            with self.assertRaises(PermissionError):
                _owner_action(None, "/api/autopilot/configure", {
                    "ack": "WRONG", "enabled": False, "daily_cap": 0
                })
            with self.assertRaises(ValueError):
                _owner_action(None, "/api/autopilot/configure", {
                    "ack": "SET_DAILY_MODEL_POLICY", "enabled": False,
                    "daily_cap": 0, "secret": "leak"
                })
            output = _owner_action(None, "/api/autopilot/configure", {
                "ack": "SET_DAILY_MODEL_POLICY", "enabled": False,
                "daily_cap": 0
            })
            self.assertEqual(0, output["daily_cap"])
            configure.assert_called_once_with(
                enabled=False, daily_cap=0, confirm=True)

    def test_ai_draft_approval_requires_reviewed_sha(self):
        with patch("agentforge.quality_v14.decide", return_value={
            "decision": "APPROVED"
        }) as decide:
            base = {"ack": "REVIEW_APPROVE", "decision": "APPROVE",
                    "output_sha": "a" * 64}
            with self.assertRaises(PermissionError):
                _owner_action(None, "/api/drafts/" + "b" * 32 + "/decide",
                              base, session={})
            decide.assert_not_called()
            session = {"reviewed_ai_drafts": {"b" * 32: "a" * 64}}
            result = _owner_action(
                None, "/api/drafts/" + "b" * 32 + "/decide",
                base, session=session)
            self.assertEqual("APPROVED", result["decision"])
            decide.assert_called_once_with("b" * 32, "APPROVE", "a" * 64,
                                           confirm=True)

    def test_no_unrestricted_publish_route(self):
        with self.assertRaises(ValueError):
            _owner_action(None, "/api/publish", {"ack": "PUBLISH"}, session={})


if __name__ == "__main__":
    unittest.main()
