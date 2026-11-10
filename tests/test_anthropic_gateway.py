import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import model
from agentforge.model_registry import ModelConfigError


def answer(text):
    return io.BytesIO(json.dumps({"content": [{"type": "text", "text": text}]}).encode())


class TestAnthropicGateway(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch_dotenv = patch.object(model, "DOTENV_PATH", Path(self.temp.name) / "missing.env")
        self.patch_dotenv.start()

    def tearDown(self):
        self.patch_dotenv.stop()
        self.temp.cleanup()

    def cloud_env(self, **kwargs):
        values = {
            "AGENTFORGE_MODEL_REF": "cloud_primary",
            "ANTHROPIC_BASE_URL": "https://gateway.example/v1",
            "ANTHROPIC_AUTH_TOKEN": "secret-for-unit-tests",
        }
        values.update(kwargs)
        return patch.dict(os.environ, values, clear=True)

    def test_worker_routes_to_gateway_messages_api(self):
        with self.cloud_env():
            with patch.object(model, "_cloud_open", return_value=answer("OK")) as mocked:
                result = model.generate("Hello", worker_id="opportunity_researcher")
        self.assertEqual(result, "OK")
        request = mocked.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://gateway.example/v1/messages")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-for-unit-tests")
        self.assertEqual(request.get_header("Anthropic-version"), "2023-06-01")
        self.assertEqual(payload["model"], "claude/claude-sonnet-5-5")
        self.assertIn("Opportunity Researcher", payload["system"])
        self.assertNotIn("think", payload)
        self.assertNotIn("format", payload)

    def test_source_reviewer_structured_json_prompt(self):
        schema = {"type": "object", "properties": {"observations": {"type": "array"}}}
        with self.cloud_env():
            with patch.object(model, "_cloud_open", return_value=answer('{"observations": []}')) as mocked:
                result = model.generate_json("Find quotes", schema, worker_id="source_reviewer")
        self.assertEqual(result, {"observations": []})
        payload = json.loads(mocked.call_args.args[0].data)
        self.assertIn("SCHEMA:", payload["system"])
        self.assertIn("Source Reviewer", payload["system"])
        self.assertNotIn("format", payload)

    def test_no_worker_uses_same_cloud_override(self):
        with self.cloud_env():
            with patch.object(model, "_cloud_open", return_value=answer("OK")) as mocked:
                self.assertEqual(model.generate("Hello"), "OK")
        self.assertTrue(mocked.call_args.args[0].full_url.endswith("/messages"))

    def test_missing_token_blocks_before_network(self):
        with self.cloud_env(ANTHROPIC_AUTH_TOKEN=""):
            with patch.object(model, "_cloud_open") as mocked:
                with self.assertRaises(ModelConfigError):
                    model.generate("Hello")
                mocked.assert_not_called()

    def test_missing_url_blocks_before_network(self):
        with self.cloud_env(ANTHROPIC_BASE_URL=""):
            with patch.object(model, "_cloud_open") as mocked:
                with self.assertRaises(ModelConfigError):
                    model.generate("Hello")
                mocked.assert_not_called()

    def test_http_url_is_rejected_before_network(self):
        with self.cloud_env(ANTHROPIC_BASE_URL="http://gateway.example/v1"):
            with patch.object(model, "_cloud_open") as mocked:
                with self.assertRaises(ModelConfigError):
                    model.generate("Hello")
                mocked.assert_not_called()

    def test_empty_gateway_content_is_an_error(self):
        with self.cloud_env():
            raw = io.BytesIO(b'{"content": [{"type": "tool_use"}]}')
            with patch.object(model, "_cloud_open", return_value=raw):
                with self.assertRaises(RuntimeError):
                    model.generate("Hello")

    def test_invalid_json_is_rejected(self):
        with self.cloud_env():
            with patch.object(model, "_cloud_open", return_value=answer("plain text")):
                with self.assertRaises(json.JSONDecodeError):
                    model.generate_json("Respond JSON", {"type": "object"})

    def test_dotenv_loads_machine_specific_model(self):
        envfile = Path(self.temp.name) / ".env"
        envfile.write_text(
            "AGENTFORGE_MODEL_REF=cloud_primary\n"
            "ANTHROPIC_BASE_URL=https://gateway.example/v1\n"
            "ANTHROPIC_AUTH_TOKEN=unit-test-value\n",
            encoding="utf-8",
        )
        with patch.object(model, "DOTENV_PATH", envfile):
            with patch.dict(os.environ, {}, clear=True):
                runtime = model.resolve_runtime(None, model.DEFAULT_TEXT_SYSTEM)
        self.assertEqual(runtime["provider"], "anthropic")
        self.assertEqual(runtime["model_ref"], "cloud_primary")

    def test_process_environment_overrides_dotenv(self):
        envfile = Path(self.temp.name) / ".env"
        envfile.write_text("AGENTFORGE_MODEL_REF=cloud_primary\n", encoding="utf-8")
        with patch.object(model, "DOTENV_PATH", envfile):
            with patch.dict(os.environ, {"AGENTFORGE_MODEL_REF": "local_primary"}, clear=True):
                runtime = model.resolve_runtime(None, model.DEFAULT_TEXT_SYSTEM)
        self.assertEqual(runtime["provider"], "ollama")
        self.assertEqual(runtime["model_ref"], "local_primary")


if __name__ == "__main__":
    unittest.main()
