import io
import json
import os
import unittest
from unittest.mock import patch

from agentforge import model
from agentforge.model_registry import ModelConfigError


def fake_response(content):
    return io.BytesIO(json.dumps({"message": {"content": content}}).encode())


class TestModelRouting(unittest.TestCase):
    def setUp(self):
        # Local routing tests must not inherit cloud selection from the user's .env.
        self.env_patch = patch.dict(os.environ, {"AGENTFORGE_MODEL_REF": "local_primary"})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()

    def test_default_no_worker_uses_registry(self):
        with patch.object(model.urllib.request, "urlopen", return_value=fake_response("OK")) as mocked:
            result = model.generate("Hello")
        self.assertEqual(result, "OK")
        request = mocked.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "qwen3:8b")
        self.assertEqual(payload["messages"][0]["content"], model.DEFAULT_TEXT_SYSTEM)
        self.assertTrue(request.full_url.endswith("/api/chat"))

    def test_researcher_uses_registered_model(self):
        with patch.object(model.urllib.request, "urlopen", return_value=fake_response("Research ready")) as mocked:
            result = model.generate("Research an opportunity", worker_id="opportunity_researcher")
        self.assertEqual(result, "Research ready")
        payload = json.loads(mocked.call_args.args[0].data)
        self.assertEqual(payload["model"], "qwen3:8b")
        self.assertIn("Opportunity Researcher", payload["messages"][0]["content"])

    def test_source_reviewer_structured_output(self):
        schema = {"type": "object", "properties": {"observations": {"type": "array"}}}
        with patch.object(model.urllib.request, "urlopen", return_value=fake_response('{"observations": []}')) as mocked:
            result = model.generate_json("Review source", schema, worker_id="source_reviewer")
        self.assertEqual(result, {"observations": []})
        payload = json.loads(mocked.call_args.args[0].data)
        self.assertEqual(payload["format"], schema)
        self.assertIn("Source Reviewer", payload["messages"][0]["content"])

    def test_unknown_model_reference_fails_before_network(self):
        with patch.dict(os.environ, {"AGENTFORGE_MODEL_REF": "does_not_exist"}):
            with patch.object(model.urllib.request, "urlopen") as mocked:
                with self.assertRaises(ModelConfigError):
                    model.generate("Test", worker_id="opportunity_researcher")
                mocked.assert_not_called()

    def test_unknown_worker_rejected_before_network(self):
        with patch.object(model.urllib.request, "urlopen") as mocked:
            with self.assertRaises(ValueError):
                model.generate("Test", worker_id="unknown_worker")
            mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
