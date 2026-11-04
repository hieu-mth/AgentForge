import tempfile
import unittest
from pathlib import Path

from agentforge.model_registry import (
    ModelConfigError,
    load_models,
)


class TestModelRegistry(unittest.TestCase):

    def test_local_model(self):
        models = load_models()

        self.assertEqual(
            models["local_qwen"]["provider"], "ollama"
        )
        self.assertEqual(
            models["local_qwen"]["model"], "qwen3:8b"
        )

    def test_cloud_model_is_disabled(self):
        models = load_models()

        cloud = models["cloud_optional"]

        self.assertFalse(cloud["enabled"])
        self.assertEqual(
            cloud["api_key_env"], "OPENAI_API_KEY"
        )

    def test_missing_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.toml"

            with self.assertRaises(ModelConfigError):
                load_models(path)

    def test_plaintext_api_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.toml"

            path.write_text(
                '[models.unsafe]\n'
                'provider = "openai"\n'
                'model = "example"\n'
                'api_key_env = "OPENAI_API_KEY"\n'
                'api_key = "do-not-store-secrets-here"\n'
                'enabled = true\n',
                encoding="utf-8",
            )

            with self.assertRaises(ModelConfigError):
                load_models(path)


if __name__ == "__main__":
    unittest.main()
