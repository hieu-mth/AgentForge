import tempfile
import unittest
from pathlib import Path

from agentforge.model_registry import ModelConfigError, load_models


class TestModelRegistry(unittest.TestCase):
    def test_local_primary(self):
        models = load_models()
        self.assertEqual(models["local_primary"]["provider"], "ollama")
        self.assertEqual(models["local_primary"]["model"], "qwen3:8b")

    def test_cloud_primary_uses_environment_references(self):
        models = load_models()
        self.assertNotIn("local_qwen", models)
        self.assertNotIn("cloud_optional", models)
        cloud = models["cloud_primary"]
        self.assertTrue(cloud["enabled"])
        self.assertEqual(cloud["provider"], "anthropic")
        self.assertEqual(cloud["api_key_env"], "ANTHROPIC_AUTH_TOKEN")
        self.assertEqual(cloud["base_url_env"], "ANTHROPIC_BASE_URL")
        self.assertNotIn("base_url", cloud)

    def test_missing_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ModelConfigError):
                load_models(Path(directory) / "missing.toml")

    def test_plaintext_api_key_is_rejected(self):
        self.assert_bad_model(
            'provider = "anthropic"\nmodel = "test"\n'
            'api_key_env = "ANTHROPIC_AUTH_TOKEN"\n'
            'base_url_env = "ANTHROPIC_BASE_URL"\n'
            'api_key = "a-real-secret-does-not-belong-here"\n'
            'enabled = true\n'
        )

    def test_inline_cloud_endpoint_is_rejected(self):
        self.assert_bad_model(
            'provider = "anthropic"\nmodel = "test"\n'
            'api_key_env = "ANTHROPIC_AUTH_TOKEN"\n'
            'base_url = "https://private.example/v1"\n'
            'enabled = true\n'
        )

    def test_invalid_environment_variable_reference_is_rejected(self):
        self.assert_bad_model(
            'provider = "anthropic"\nmodel = "test"\n'
            'api_key_env = "invalid-name"\n'
            'base_url_env = "ANTHROPIC_BASE_URL"\n'
            'enabled = true\n'
        )

    def test_unimplemented_provider_is_rejected(self):
        self.assert_bad_model(
            'provider = "openai"\nmodel = "some-model"\n'
            'api_key_env = "OPENAI_API_KEY"\n'
            'enabled = true\n'
        )

    def assert_bad_model(self, body):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.toml"
            path.write_text('[models.bad]\n' + body, encoding='utf-8')
            with self.assertRaises(ModelConfigError):
                load_models(path)


if __name__ == "__main__":
    unittest.main()
