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
        stats = {"lead_total": 3, "synthetic": False, "owner_reported_posts": 1,
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

    def test_retired_autopilot_api_cannot_reconfigure_policy(self):
        with patch("agentforge.autopilot_v13.configure") as configure:
            with self.assertRaisesRegex(ValueError, "Unknown mutation route"):
                _owner_action(None, "/api/autopilot/configure", {
                    "ack": "SET_DAILY_MODEL_POLICY", "enabled": False, "daily_cap": 0})
            configure.assert_not_called()

    def test_retired_draft_and_media_v15_approvals_are_not_dispatched(self):
        with patch("agentforge.quality_v14.decide") as draft, \
             patch("agentforge.media_workflow_v15.decide") as video:
            for path in ("/api/drafts/" + "b"*32 + "/decide",
                         "/api/videos/" + "b"*32 + "/decide"):
                with self.subTest(path=path), self.assertRaisesRegex(
                        ValueError, "Unknown mutation route"):
                    _owner_action(None, path, {"ack": "APPROVE"}, session={})
            draft.assert_not_called()
            video.assert_not_called()

    def test_no_unrestricted_publish_route(self):
        with self.assertRaises(ValueError):
            _owner_action(None, "/api/publish", {"ack": "PUBLISH"}, session={})


if __name__ == "__main__":
    unittest.main()
