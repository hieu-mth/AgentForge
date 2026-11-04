"""Gateway diagnostics for C8B: bounded output, safe failures, no retry."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import model, product_builder, product_revision


def response(obj):
    return io.BytesIO(json.dumps(obj).encode("utf-8"))


class TestGatewayOutputBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch_dotenv = patch.object(
            model, "DOTENV_PATH", Path(self.tmp.name) / "missing.env")
        self.patch_dotenv.start()
        self.cloud = patch.dict(os.environ, {
            "AGENTFORGE_MODEL_REF": "cloud_primary",
            "ANTHROPIC_BASE_URL": "https://gateway.example/v1",
            "ANTHROPIC_AUTH_TOKEN": "do-not-leak-secret-token",
        }, clear=True)
        self.cloud.start()

    def tearDown(self):
        self.cloud.stop()
        self.patch_dotenv.stop()
        self.tmp.cleanup()

    def call(self, obj, *, worker_id=None, schema=None):
        with patch.object(model.urllib.request, "urlopen",
                          return_value=response(obj)) as network:
            if schema is None:
                text = model.generate("Make HTML", worker_id=worker_id)
            else:
                text = model.generate_json("Return JSON", schema,
                                           worker_id=worker_id)
        payload = json.loads(network.call_args.args[0].data)
        return text, payload, network.call_count

    def test_builder_receives_larger_budget(self):
        text, payload, calls = self.call(
            {"content": [{"type": "text", "text": "<html></html>"}]},
            worker_id="product_builder")
        self.assertEqual(text, "<html></html>")
        self.assertEqual(payload["max_tokens"], 8192)
        self.assertEqual(calls, 1)

    def test_research_text_keeps_existing_budget(self):
        text, payload, calls = self.call(
            {"content": [{"type": "text", "text": "OK"}]},
            worker_id="opportunity_researcher")
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertEqual(text, "OK")
        self.assertEqual(calls, 1)

    def test_unscoped_text_keeps_existing_budget(self):
        _, payload, _ = self.call(
            {"content": [{"type": "text", "text": "OK"}]})
        self.assertEqual(payload["max_tokens"], 2048)

    def test_json_keeps_original_budget_in_builder(self):
        result, payload, calls = self.call(
            {"content": [{"type": "text", "text": '{"ok":true}'}]},
            worker_id="product_builder",
            schema={"type": "object"})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(payload["max_tokens"], 4096)
        self.assertEqual(calls, 1)

    def test_thinking_only_exhausted_budget_is_reported(self):
        obj = {"stop_reason": "max_tokens", "usage": {"output_tokens": 8192},
               "content": [{"type": "thinking", "thinking": "private reasoning"}]}
        with patch.object(model.urllib.request, "urlopen",
                          return_value=response(obj)) as net:
            with self.assertRaisesRegex(RuntimeError, "stopped at max_tokens") as raised:
                model.generate("Make HTML", worker_id="product_builder")
            self.assertEqual(net.call_count, 1)
        error = str(raised.exception)
        self.assertIn("output_tokens=8192", error)
        self.assertIn("block_types=['thinking']", error)
        self.assertIn("max_tokens=8192", error)
        self.assertNotIn("private reasoning", error)
        self.assertNotIn("do-not-leak-secret-token", error)

    def test_truncated_partial_html_is_rejected_even_with_text(self):
        obj = {"stop_reason": "max_tokens",
               "content": [{"type": "text", "text": "<html><body>partial"}]}
        with patch.object(model.urllib.request, "urlopen",
                          return_value=response(obj)) as net:
            with self.assertRaisesRegex(RuntimeError, "Incomplete output rejected"):
                model.generate("Make HTML", worker_id="product_builder")
            net.assert_called_once()

    def test_thinking_only_end_turn_reports_content_types(self):
        obj = {"stop_reason": "end_turn",
               "content": [{"type": "thinking", "thinking": "reasoning"}]}
        with patch.object(model.urllib.request, "urlopen",
                          return_value=response(obj)):
            with self.assertRaisesRegex(RuntimeError, "no text content") as raised:
                model.generate("Make HTML", worker_id="product_builder")
        self.assertIn("block_types=['thinking']", str(raised.exception))
        self.assertIn("stop_reason='end_turn'", str(raised.exception))
        self.assertNotIn("reasoning", str(raised.exception))

    def test_no_content_array_has_diagnostic(self):
        with patch.object(model.urllib.request, "urlopen",
                          return_value=response({"stop_reason": "end_turn"})):
            with self.assertRaisesRegex(RuntimeError, "no content blocks") as raised:
                model.generate("Make HTML", worker_id="product_builder")
        self.assertIn("max_tokens=8192", str(raised.exception))

    def test_tools_only_response_is_not_treated_as_text(self):
        with patch.object(model.urllib.request, "urlopen",
                          return_value=response({
                              "stop_reason": "tool_use",
                              "content": [{"type": "tool_use", "name": "run"}]})) as net:
            with self.assertRaisesRegex(RuntimeError, "no text content"):
                model.generate("Make HTML", worker_id="product_builder")
            net.assert_called_once()

    def test_multiple_valid_text_blocks_still_work(self):
        text, _, _ = self.call({
            "stop_reason": "end_turn",
            "content": [
                {"type": "thinking", "thinking": "private reasoning"},
                {"type": "text", "text": "Part A"},
                {"type": "text", "text": "Part B"},
            ],
        }, worker_id="product_builder")
        self.assertEqual(text, "Part A\nPart B")

    def test_malformed_response_is_not_silently_accepted(self):
        with patch.object(model.urllib.request, "urlopen",
                          return_value=response(["unexpected"])):
            with self.assertRaisesRegex(RuntimeError, "must be a JSON object"):
                model.generate("Make HTML", worker_id="product_builder")

    def test_revision_failure_keeps_product_and_creates_no_proposal(self):
        root = Path(self.tmp.name) / "repo"
        file = root / "workspace" / "products" / "shop-landing" / "index.html"
        file.parent.mkdir(parents=True)
        original = ('<!doctype html><html lang="vi"><head><title>Demo</title>'
                    '</head><body><h1>Old page</h1></body></html>')
        file.write_text(original, encoding="utf-8")
        builder_root = root / "data" / "company" / "product_builder"
        obj = {"stop_reason": "max_tokens", "content": [
            {"type": "thinking", "thinking": "not an html page"}]}
        with (patch.object(product_builder, "ROOT", root),
              patch.object(product_builder, "PRODUCTS", file.parent.parent),
              patch.object(model.urllib.request, "urlopen",
                           return_value=response(obj)) as net):
            with self.assertRaisesRegex(RuntimeError, "stopped at max_tokens"):
                product_revision.propose(
                    "shop-landing", "Improve mobile pricing layout, preserve text.")
            net.assert_called_once()
        self.assertEqual(file.read_text(encoding="utf-8"), original)
        self.assertFalse((builder_root / "revisions").exists())


if __name__ == "__main__":
    unittest.main()
