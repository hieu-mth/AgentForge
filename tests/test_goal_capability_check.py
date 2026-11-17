from unittest import TestCase
from unittest.mock import patch

from agentforge.ai import model_health, prompt_intake


class GoalCapabilityCheckTests(TestCase):
    def setUp(self):
        self.goal = {"current_step": 0, "plan": [{"skill_id": "web.create",
            "worker_id": "product_builder", "required_permissions": ["model.invoke"]}]}

    def test_metadata_never_means_model_readiness(self):
        runtime = {"provider": "ollama", "model": "local:tag", "model_ref": "local_primary"}
        with patch("agentforge.model.resolve_runtime", return_value=runtime), \
                patch.object(model_health, "check", return_value={"status": "READY"}):
            result = model_health.inspect_goal_step(self.goal)
        self.assertEqual((result["status"], result["loadability"]), ("CATALOG_PRESENT", "UNKNOWN"))
        self.assertFalse(result["inference_invoked"])

    def test_paid_provider_is_not_probed(self):
        runtime = {"provider": "anthropic", "model": "example", "model_ref": "cloud_primary",
                   "api_key": "do not expose"}
        with patch("agentforge.model.resolve_runtime", return_value=runtime), \
                patch.object(model_health, "check") as check:
            result = model_health.inspect_goal_step(self.goal)
        check.assert_not_called()
        self.assertEqual(result["status"], "CLOUD_NOT_PROBED")
        self.assertNotIn("api_key", result)

    def test_image_intake_does_not_create_a_placeholder_or_a_fake_goal(self):
        with patch("agentforge.features.websites.image_studio.health", return_value={
            "status": "UNAVAILABLE", "checkpoints": [],
        }), patch.object(prompt_intake.brain_planner, "propose") as propose:
            result = prompt_intake.plan_request("Tạo hình ảnh quảng cáo cho website cửa hàng nệm")
        propose.assert_not_called()
        self.assertEqual(result["status"], "CAPABILITY_BLOCKED")
        self.assertFalse(result["model_dispatched"])

    def test_scoped_local_check_uses_same_catalog_gate_as_execution(self):
        self.goal["plan"][0].update(skill_id="workspace.analyze", worker_id="opportunity_researcher")
        runtime = {"provider": "ollama", "model": "alias:tag", "model_ref": "local_primary",
                   "route_source": "owner", "base_url": "http://127.0.0.1:11434"}
        with patch("agentforge.model.resolve_runtime", return_value=runtime), \
                patch("agentforge.ops.runtime_certification._installed_local_model",
                      return_value=False) as probe:
            result = model_health.inspect_goal_step(self.goal)
        probe.assert_called_once_with("127.0.0.1", 11434, "alias:tag")
        self.assertEqual(result["status"], "LOCAL_MODEL_NOT_CONFIRMED")
        self.assertEqual(result["route_source"], "owner")
        self.assertFalse(result["inference_invoked"])
        self.assertFalse(result["automatic_fallback"])
