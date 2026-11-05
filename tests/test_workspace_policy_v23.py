"""V2.3 owner workspace settings: policy gates, durable audit and no budget claims."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import workspace_policy, prompt_intake
from agentforge.control_center_v1 import _owner_action


class WorkspacePolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / "workspace_policy.sqlite3"
        self.goals = self.root / "goals.sqlite3"

    def test_default_does_not_create_db(self):
        defaults = workspace_policy.read(db_path=self.db)
        self.assertEqual(1, defaults["max_estimated_model_calls"])
        self.assertTrue(defaults["website_enabled"])
        self.assertFalse(defaults["provider_billing_verified"])
        self.assertFalse(self.db.exists())

    def test_owner_confirmation_strict_types_and_audit(self):
        with self.assertRaises(PermissionError):
            workspace_policy.configure(max_estimated_model_calls=0,
                                       website_enabled=False, storyboard_enabled=True,
                                       db_path=self.db)
        with self.assertRaises(ValueError):
            workspace_policy.configure(max_estimated_model_calls=True,
                                       website_enabled=False, storyboard_enabled=True,
                                       confirm=True, db_path=self.db)
        with self.assertRaises(ValueError):
            workspace_policy.configure(max_estimated_model_calls=2,
                                       website_enabled="false", storyboard_enabled=True,
                                       confirm=True, db_path=self.db)
        saved = workspace_policy.configure(max_estimated_model_calls=0,
                                            website_enabled=False,
                                            storyboard_enabled=True,
                                            confirm=True, db_path=self.db)
        self.assertEqual("OWNER_SET", saved["source"])
        self.assertEqual(0, saved["max_estimated_model_calls"])
        self.assertFalse(saved["website_enabled"])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM changes").fetchone()[0])
            self.assertEqual(0, connection.execute("SELECT max_estimated_model_calls FROM policy").fetchone()[0])

    def test_policy_is_enforced_before_goal_creation(self):
        workspace_policy.configure(max_estimated_model_calls=0,
                                   website_enabled=True, storyboard_enabled=True,
                                   confirm=True, db_path=self.db)
        prompt = "Tạo landing page giới thiệu nệm ngủ, hotline 0879547988"
        with patch("agentforge.model.generate") as model:
            with self.assertRaises(PermissionError):
                prompt_intake.plan_request(prompt, brain_db_path=self.goals,
                                           policy_db_path=self.db)
            model.assert_not_called()
        self.assertFalse(self.goals.exists())
        workspace_policy.configure(max_estimated_model_calls=1,
                                   website_enabled=False, storyboard_enabled=True,
                                   confirm=True, db_path=self.db)
        with self.assertRaises(PermissionError):
            prompt_intake.plan_request(prompt, brain_db_path=self.goals,
                                       policy_db_path=self.db)
        self.assertFalse(self.goals.exists())

    def test_workspace_policy_api_is_allowlisted(self):
        with patch("agentforge.workspace_policy.configure", return_value={
            "max_estimated_model_calls": 0
        }) as saved:
            data = {"ack": "UPDATE_WORKSPACE_POLICY",
                    "max_estimated_model_calls": 0,
                    "website_enabled": False, "storyboard_enabled": False}
            with self.assertRaises(PermissionError):
                _owner_action(None, "/api/workspace/policy", {**data, "ack": "RUN"})
            with self.assertRaises(PermissionError):
                _owner_action(None, "/api/workspace/policy", {**data, "danger": "process"})
            result = _owner_action(None, "/api/workspace/policy", data)
            self.assertEqual(0, result["max_estimated_model_calls"])
            saved.assert_called_once_with(max_estimated_model_calls=0,
                                          website_enabled=False,
                                          storyboard_enabled=False,
                                          confirm=True)


if __name__ == "__main__":
    unittest.main()
