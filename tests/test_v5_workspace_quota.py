"""V5.1 workspace policy quota must be actionable and never auto-escalated."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import brain_store, prompt_intake, workspace_policy

BRIEF = (
    "Tạo ứng dụng React quản lý cửa hàng demo. Yêu cầu AI Architect "
    "lập kiến trúc, AI Developer viết component, QA kiểm tra tĩnh "
    "và AI Reviewer phản biện kết quả."
)


class V5WorkspaceQuotaTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.brain=root/"brain.sqlite3"
        self.policy=root/"policy.sqlite3"

    def test_default_quota_blocks_without_creating_goal_or_invoking_model(self):
        self.assertEqual(workspace_policy.read(db_path=self.policy)[
            "max_estimated_model_calls"],1)
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaisesRegex(PermissionError, "WORKSPACE_MODEL_CAP_EXCEEDED") as caught:
                prompt_intake.plan_request(
                    BRIEF,max_model_calls=3,brain_db_path=self.brain,
                    policy_db_path=self.policy)
            model.assert_not_called()
        error=str(caught.exception)
        self.assertIn("cần 3 lượt",error)
        self.assertIn("hiện tại là 1",error)
        self.assertIn("Prompt Workspace",error)
        self.assertFalse(self.brain.exists())
        self.assertFalse(self.policy.exists())

    def test_owner_explicitly_changes_quota_then_only_plans_four_steps(self):
        workspace_policy.configure(
            max_estimated_model_calls=3,website_enabled=True,
            storyboard_enabled=True,confirm=True,db_path=self.policy)
        with (patch("agentforge.model.generate_json") as model,
              patch("agentforge.goal_preflight.require_ready")):
            receipt=prompt_intake.plan_request(
                BRIEF,max_model_calls=3,brain_db_path=self.brain,
                policy_db_path=self.policy)
            model.assert_not_called()
        self.assertEqual(receipt["status"],"PLAN_CREATED")
        self.assertEqual(receipt["template"],"webapp.company")
        self.assertFalse(receipt["model_dispatched"])
        goal=brain_store.get_goal(receipt["goal_id"],db_path=self.brain)
        self.assertEqual(goal["status"],"PLANNED")
        self.assertEqual([x["skill_id"] for x in goal["plan"]],[
            "webapp.architect","webapp.develop","webapp.audit","webapp.review"])
        self.assertEqual(sum(x["estimated_model_calls"] for x in goal["plan"]),3)
        self.assertEqual(workspace_policy.read(db_path=self.policy)[
            "max_estimated_model_calls"],3)

    def test_single_call_works_at_default_without_auto_elevating(self):
        text="Thiết kế một landing page cho nệm ngủ gia đình trên mobile."
        with (patch("agentforge.model.generate_json") as model,
              patch("agentforge.goal_preflight.require_ready")):
            receipt=prompt_intake.plan_request(
                text,max_model_calls=1,brain_db_path=self.brain,
                policy_db_path=self.policy)
            model.assert_not_called()
        self.assertEqual(receipt["template"],"website.draft")
        self.assertEqual(workspace_policy.read(db_path=self.policy)[
            "max_estimated_model_calls"],1)

    def test_two_call_cap_also_refuses_v5_and_does_not_change_limit(self):
        workspace_policy.configure(
            max_estimated_model_calls=2,website_enabled=True,
            storyboard_enabled=True,confirm=True,db_path=self.policy)
        with self.assertRaisesRegex(PermissionError,"hiện tại là 2"):
            prompt_intake.plan_request(BRIEF,max_model_calls=3,
                brain_db_path=self.brain,policy_db_path=self.policy)
        self.assertEqual(workspace_policy.read(db_path=self.policy)[
            "max_estimated_model_calls"],2)
        self.assertFalse(self.brain.exists())


if __name__=="__main__":
    unittest.main()
