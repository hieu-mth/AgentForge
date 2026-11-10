"""Pre-runtime public-repository source hygiene is filename/content bounded."""
import unittest
from agentforge.paths import REPOSITORY_ROOT
from scripts.check_source_hygiene import forbidden_path, has_token, inspect


class SourceHygieneTests(unittest.TestCase):
    def test_credentials_weights_and_generated_artifacts_never_tracked(self):
        banned = [
            "models/diffusion_models/wan2.2.safetensors",
            "workspace/films/episode.mp4", "data/company/state.sqlite3",
            ".venv/Scripts/python.exe", "dashboard/node_modules/react/index.js",
            "client_secret_123.json", "Demos/OAuthDesktopClient.json",
            "secrets/token.json", "keys/private.pem", ".env",
            ".env.production", "models/voices/voice.onnx",
        ]
        for path in banned:
            with self.subTest(path=path):
                self.assertTrue(forbidden_path(path))
        for path in ["agentforge/api/server.py", "docs/README.md",
                     "config/task_routes.toml", ".env.example",
                     "dashboard/src/App.jsx"]:
            with self.subTest(path=path):
                self.assertFalse(forbidden_path(path))

    def test_high_confidence_token_signatures(self):
        self.assertTrue(has_token("-----BEGIN " + "PRIVATE KEY-----"))
        self.assertTrue(has_token("ghp_" + "A" * 36))
        self.assertTrue(has_token("sk-ant-" + "B" * 40))
        self.assertTrue(has_token("AIza" + "C" * 38))
        self.assertFalse(has_token("ANTHROPIC_AUTH_TOKEN=replace-with-your-token"))
        self.assertFalse(has_token("Never commit an OAuth client secret."))

    def test_current_git_tree_has_no_prohibited_tracked_files(self):
        result = inspect(REPOSITORY_ROOT)
        self.assertEqual(result["status"], "PASS", result["problems"][:5])
        self.assertGreater(result["tracked_files"], 500)


if __name__ == "__main__":
    unittest.main()
