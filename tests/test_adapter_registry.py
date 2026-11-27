"""Model dispatch and catalog must use the same registered adapter."""
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge.ai import model_hub, orchestrator_policy, registry
from agentforge.features.film_studio import studio_runtime


class RegistryTests(unittest.TestCase):
    def test_registered_provider_uses_same_resolver_for_profile_route_and_inference(self):
        class Text:
            def infer_structured(self, profile, instructions, data, schema, **options):
                return {"model": profile["model"], "value": data["value"]}

        adapter = Text()
        provider = "fixture_api"
        descriptor = {"label": "Fixture API", "connection": "local",
                      "model_label": "Model", "defaults": {"base_url": "http://127.0.0.1:9000"}}
        entry = registry.Registration("text", lambda: adapter, (provider,))
        with (tempfile.TemporaryDirectory() as directory,
              patch.dict(registry.ADAPTERS, {provider: descriptor}),
              patch.object(registry, "REGISTRATIONS", (*registry.REGISTRATIONS, entry))):
            db = Path(directory) / "registry.sqlite3"
            for revision, model in enumerate(("fixture-a", "fixture-b")):
                profile = {"id": "fixture_text", "provider": provider, "model": model,
                           "enabled": True, "base_url": descriptor["defaults"]["base_url"]}
                result = model_hub.change("SAVE_MODEL_PROFILE", expected_revision=revision * 2,
                                          db_path=db, profile=profile)
                self.assertTrue(result["profiles"][0]["runtime_supported"])
                model_hub.change("SET_MODEL_ROUTE", expected_revision=revision * 2 + 1,
                                 db_path=db, task_id="general.text", model_ref=profile["id"])
                self.assertIs(orchestrator_policy.runtime_adapter("text", profile), adapter)
                self.assertIs(studio_runtime.text_adapter(profile), adapter)
                self.assertEqual(studio_runtime.text_adapter(profile).infer_structured(
                    profile, "", {"value": 7}, {}), {"model": model, "value": 7})
                self.assertEqual(model_hub.effective_models(db_path=db)["fixture_text"]["model"], model)

    def test_ambiguity_fails_closed(self):
        entry = registry.Registration("text", lambda: object(), ("ollama",))
        profile = {"provider": "ollama"}
        with patch.object(registry, "REGISTRATIONS", (*registry.REGISTRATIONS, entry)):
            with self.assertRaises(ValueError):
                studio_runtime.text_adapter(profile)
            self.assertIsNone(orchestrator_policy.runtime_adapter("text", profile))

    def test_resolver_and_policy_do_not_import_concrete_implementations(self):
        root = Path(__file__).resolve().parents[1]
        for filename in ("agentforge/ai/orchestrator_policy.py",
                         "agentforge/features/film_studio/studio_runtime.py"):
            tree = ast.parse((root / filename).read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.startswith("agentforge.features"):
                        self.assertEqual(module, "agentforge.features.film_studio.studio_contracts")
                elif isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name.startswith("agentforge.features")
                                         for alias in node.names))


if __name__ == "__main__":
    unittest.main()
