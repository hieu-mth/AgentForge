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

            def registry_readiness(self, profile):
                return "READY"

            def probe(self, profile):
                return {"status": "PASS_RUNTIME"}

        adapter = Text()
        provider = "fixture_api"
        descriptor = {"label": "Fixture API", "connection": "local",
                      "model_label": "Model", "defaults": {"base_url": "http://127.0.0.1:9000"}}
        entry = registry.Registration("text", lambda: adapter, (provider,))
        def validate_options(profile, options):
            if options["variant"] not in {"fast", "quality"}:
                raise ValueError("Invalid fixture variant")
            return options

        profile_options = registry.ProfileOptions(({"id": "fixture", "label": "Fixture", "fields": [
            {"path": ["variant"], "kind": "text", "label": "Variant", "required": True}]},), validate_options)
        with (tempfile.TemporaryDirectory() as directory,
              patch.dict(registry.PROFILE_OPTIONS, {provider: profile_options}),
              patch.dict(registry.ADAPTERS, {provider: descriptor}),
              patch.object(registry, "REGISTRATIONS", (*registry.REGISTRATIONS, entry))):
            db = Path(directory) / "registry.sqlite3"
            for revision, model in enumerate(("fixture-a", "fixture-b")):
                profile = {"id": "fixture_text", "provider": provider, "model": model,
                           "enabled": True, "base_url": descriptor["defaults"]["base_url"], "variant": "fast"}
                with self.assertRaises(model_hub.ModelConfigError):
                    model_hub.validate_profile({**profile, "variant": "invalid"})
                result = model_hub.change("SAVE_MODEL_PROFILE", expected_revision=revision * 2,
                                          db_path=db, profile=profile)
                self.assertTrue(result["profiles"][0]["runtime_supported"])
                advertised = next(item for item in result["adapters"] if item["id"] == provider)
                self.assertEqual(advertised["profile_schema"]["option_variants"], profile_options.ui_variants)
                model_hub.change("SET_MODEL_ROUTE", expected_revision=revision * 2 + 1,
                                 db_path=db, task_id="general.text", model_ref=profile["id"])
                self.assertIs(orchestrator_policy.runtime_adapter("text", profile), adapter)
                self.assertIs(studio_runtime.text_adapter(profile), adapter)
                self.assertEqual(studio_runtime.text_adapter(profile).infer_structured(
                    profile, "", {"value": 7}, {}), {"model": model, "value": 7})
                self.assertEqual(model_hub.effective_models(db_path=db)["fixture_text"]["model"], model)
                self.assertEqual(model_hub.capability_readiness(profile["id"], "general.text",
                    expected_revision=revision * 2 + 2, db_path=db)["status"], "METADATA_COMPATIBLE")
                self.assertEqual(model_hub.probe_local_profile(profile["id"],
                    expected_revision=revision * 2 + 2, db_path=db)["status"], "PASS_RUNTIME")

    def test_cloud_options_are_independent_of_credentials(self):
        provider = "fixture_cloud"
        descriptor = {"label": "Fixture Cloud", "connection": "cloud",
                      "model_label": "Model", "defaults": {"base_url": ""},
                      "environment_defaults": {"base_url_env": "FIXTURE_URL", "api_key_env": "FIXTURE_KEY"}}
        options = registry.ProfileOptions(({"id": "quality", "label": "Quality", "fields": [
            {"path": ["quality"], "kind": "text", "label": "Quality", "required": True}]},),
            lambda profile, fields: fields)
        with (patch.dict(registry.ADAPTERS, {provider: descriptor}),
              patch.dict(registry.PROFILE_OPTIONS, {provider: options})):
            base = {"id": "cloud_fixture", "provider": provider, "model": "demo",
                    "enabled": True, "quality": "high"}
            direct = {**base, "base_url": "https://example.com/v1"}
            self.assertEqual(model_hub.validate_profile(direct, preview=True), direct)
            env = {**base, **descriptor["environment_defaults"]}
            self.assertEqual(model_hub.validate_profile(env), env)
            with self.assertRaises(model_hub.ModelConfigError):
                model_hub.validate_profile({**env, "api_key": "never accepted"})
            with self.assertRaises(model_hub.ModelConfigError):
                model_hub.validate_profile({key: value for key, value in env.items() if key != "quality"})

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
