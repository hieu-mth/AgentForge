"""V4.3 local-first V5 role routing: bounded calls, no fallback or cloud without consent."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import model
from agentforge.ai import role_routing
from agentforge.model_registry import ModelConfigError


class RoleRoutingTests(unittest.TestCase):
    def test_roles_default_to_enabled_local_profiles(self):
        plan = role_routing.pipeline_plan(max_model_calls=3)
        self.assertEqual(plan["model_calls"], 3)
        self.assertEqual(plan["external_runs"], 0)
        self.assertFalse(plan["automatic_fallback"])
        self.assertFalse(plan["cost_verified"])
        self.assertEqual([x["role"] for x in plan["roles"]],
                         ["architect", "developer", "reviewer"])
        self.assertTrue(all(x["provider"] == "ollama" for x in plan["roles"]))
        self.assertTrue(all(x["model_ref"] == "local_primary" for x in plan["roles"]))

    def test_budget_and_unknown_model_fail_before_invocation(self):
        with self.assertRaisesRegex(PermissionError, "MODEL_BUDGET_EXCEEDED"):
            role_routing.pipeline_plan(max_model_calls=2)
        with self.assertRaises(ValueError):
            role_routing.pipeline_plan(max_model_calls=True)
        with self.assertRaises(ValueError):
            role_routing.describe_role("finance")
        with self.assertRaises(ModelConfigError):
            role_routing.describe_role("architect", model_ref_override="nonexistent")

    def test_explicit_cloud_consent_is_required_for_role_overrides(self):
        with self.assertRaisesRegex(PermissionError, "CLOUD_MODEL_CONSENT_REQUIRED"):
            role_routing.describe_role("developer", model_ref_override="cloud_primary")
        configured = role_routing.describe_role("developer",
            model_ref_override="cloud_primary", cloud_consent=True)
        self.assertTrue(configured["remote"])
        self.assertEqual(configured["provider"], "anthropic")
        self.assertFalse(configured["fallback_allowed"])

    def test_cloud_credential_lookup_does_not_happen_without_owner_consent(self):
        with patch.dict(os.environ, {"AGENTFORGE_MODEL_REF": "cloud_primary",
                                      "AGENTFORGE_CLOUD_MODEL_CONSENT": "",
                                      "ANTHROPIC_BASE_URL": "",
                                      "ANTHROPIC_AUTH_TOKEN": ""}):
            with patch.object(model.urllib.request, "urlopen") as network:
                with self.assertRaisesRegex(PermissionError, "CLOUD_MODEL_CONSENT_REQUIRED"):
                    model.resolve_runtime("webapp_developer", model.DEFAULT_JSON_SYSTEM)
                network.assert_not_called()

    def test_v5_direct_model_check_loads_dotenv_before_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            envfile = Path(temp) / ".env"
            envfile.write_text(
                "AGENTFORGE_MODEL_REF=cloud_primary\\n"
                "AGENTFORGE_CLOUD_MODEL_CONSENT=YES\\n",
                encoding="utf-8",
            )
            with patch.object(role_routing, "DOTENV_PATH", envfile):
                with patch.dict(os.environ, {}, clear=True):
                    selected = role_routing.require_worker_model("webapp_architect")
                    self.assertEqual(selected["model_ref"], "cloud_primary")
                    self.assertEqual(selected["provider"], "anthropic")

    def test_v5_dotenv_cannot_override_process_consent_denial(self):
        with tempfile.TemporaryDirectory() as temp:
            envfile = Path(temp) / ".env"
            envfile.write_text(
                "AGENTFORGE_MODEL_REF=cloud_primary\\n"
                "AGENTFORGE_CLOUD_MODEL_CONSENT=YES\\n",
                encoding="utf-8",
            )
            with patch.object(role_routing, "DOTENV_PATH", envfile):
                with patch.dict(os.environ, {
                    "AGENTFORGE_MODEL_REF": "cloud_primary",
                    "AGENTFORGE_CLOUD_MODEL_CONSENT": "",
                }, clear=True):
                    with self.assertRaisesRegex(
                            PermissionError, "CLOUD_MODEL_CONSENT_REQUIRED"):
                        role_routing.require_worker_model("webapp_architect")

    def test_local_role_runtime_preserves_role_specific_prompt(self):
        with patch.dict(os.environ, {"AGENTFORGE_MODEL_REF": "local_primary"}):
            runtime = model.resolve_runtime("webapp_architect", model.DEFAULT_JSON_SYSTEM)
        self.assertEqual(runtime["provider"], "ollama")
        self.assertEqual(runtime["model_ref"], "local_primary")
        self.assertIn("AI Application Architect", runtime["system_prompt"])
        self.assertIn("Return valid structured JSON", runtime["system_prompt"])

    def test_no_unknown_worker_routing_and_no_secrets_in_plan(self):
        with self.assertRaises(ValueError):
            role_routing.require_worker_model("product_builder")
        plan = role_routing.pipeline_plan()
        self.assertNotIn("api_key", str(plan))
        self.assertNotIn("token", str(plan))


if __name__ == "__main__":
    unittest.main()
