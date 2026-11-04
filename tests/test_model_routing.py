import io
import json
import os
import unittest
from unittest.mock import patch

from agentforge import model


def fake_response(content):
    data = {"message": {"content": content}}
    return io.BytesIO(
        json.dumps(data).encode("utf-8")
    )


class TestModelRouting(unittest.TestCase):

    def test_legacy_model_configuration(self):
        with patch.dict(os.environ, {
            "AGENTFORGE_MODEL": "legacy-test-model",
            "AGENTFORGE_OLLAMA_URL":
                "http://127.0.0.1:11434",
        }):
            with patch.object(
                model.urllib.request,
                "urlopen",
                return_value=fake_response("OK"),
            ) as mocked:
                result = model.generate("Hello")

        self.assertEqual(result, "OK")

        request = mocked.call_args.args[0]
        payload = json.loads(request.data)

        self.assertEqual(
            payload["model"], "legacy-test-model"
        )
        self.assertEqual(
            payload["messages"][0]["content"],
            model.DEFAULT_TEXT_SYSTEM
        )

    def test_researcher_uses_registered_model(self):
        with patch.object(
            model.urllib.request,
            "urlopen",
            return_value=fake_response("Research ready"),
        ) as mocked:
            result = model.generate(
                "Research a business opportunity",
                worker_id="opportunity_researcher",
            )

        self.assertEqual(result, "Research ready")

        request = mocked.call_args.args[0]
        payload = json.loads(request.data)

        self.assertEqual(payload["model"], "qwen3:8b")
        self.assertIn(
            "Opportunity Researcher",
            payload["messages"][0]["content"]
        )

    def test_source_reviewer_structured_output(self):
        schema = {
            "type": "object",
            "properties": {
                "observations": {"type": "array"}
            }
        }

        with patch.object(
            model.urllib.request,
            "urlopen",
            return_value=fake_response(
                '{"observations": []}'
            ),
        ) as mocked:
            result = model.generate_json(
                "Review this source",
                schema,
                worker_id="source_reviewer",
            )

        self.assertEqual(
            result, {"observations": []}
        )

        request = mocked.call_args.args[0]
        payload = json.loads(request.data)

        self.assertEqual(payload["format"], schema)
        self.assertIn(
            "Source Reviewer",
            payload["messages"][0]["content"]
        )

    def test_unsupported_provider_rejected(self):
        profile = {
            "model": {
                "provider": "openai",
                "model": "cloud-test-model"
            },
            "instructions": "Test instructions"
        }

        with patch.object(
            model, "load_worker",
            return_value=profile
        ):
            with patch.object(
                model.urllib.request, "urlopen"
            ) as mocked:
                with self.assertRaises(NotImplementedError):
                    model.generate(
                        "Test",
                        worker_id="cloud_worker"
                    )

                mocked.assert_not_called()

    def test_unknown_worker_rejected_before_network(self):
        with patch.object(
            model.urllib.request, "urlopen"
        ) as mocked:
            with self.assertRaises(ValueError):
                model.generate(
                    "Test",
                    worker_id="unknown_worker"
                )

            mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
