"""V5.2: large Developer calls stream safely and use a bounded timeout.

No network, model inference or generated source execution occurs in this suite.
"""
import io
import json
import os
import socket
import unittest
from unittest.mock import patch
from urllib.error import URLError

from agentforge import model, skill_runner
from agentforge.model_registry import ModelConfigError


OLLAMA = {
    "provider": "ollama", "model": "qwen3:8b", "base_url": "http://127.0.0.1:11434",
    "system_prompt": "Trusted worker prompt",
}
CLOUD = {
    "model": "claude/claude-sonnet-5-5",
    "base_url": "https://gateway.example/v1",
    "api_key": "private-key-never-in-result",
    "system_prompt": "Trusted worker prompt",
}


def events(*items):
    return io.BytesIO(b"".join(
        json.dumps(item, ensure_ascii=False).encode("utf-8") + b"\n"
        for item in items
    ))


class DeveloperInferenceTests(unittest.TestCase):
    def test_local_developer_streams_one_request_and_assembles_complete_json(self):
        raw = events(
            {"message": {"content": '{"title": "Ứng'}, "done": False},
            {"message": {"content": ' dụng"}'}, "done": False},
            {"done": True, "message": {"content": ""}},
        )
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(model, "resolve_runtime", return_value=OLLAMA), \
             patch.object(model.urllib.request, "urlopen", return_value=raw) as network:
            result = model.generate_json(
                "Generate React", {"type": "object"},
                worker_id="webapp_developer")
        self.assertEqual(result, {"title": "Ứng dụng"})
        request = json.loads(network.call_args.args[0].data)
        self.assertTrue(request["stream"])
        self.assertEqual(network.call_args.kwargs["timeout"], 600)
        network.assert_called_once()

    def test_other_workers_remain_nonstreaming_with_original_180s_timeout(self):
        raw = io.BytesIO(json.dumps({"message": {"content": '{"ok":true}'}}).encode())
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(model, "resolve_runtime", return_value=OLLAMA), \
             patch.object(model.urllib.request, "urlopen", return_value=raw) as network:
            result = model.generate_json("Prompt", {"type": "object"},
                                         worker_id="source_reviewer")
        self.assertEqual(result, {"ok": True})
        self.assertFalse(json.loads(network.call_args.args[0].data)["stream"])
        self.assertEqual(network.call_args.kwargs["timeout"], 180)
        network.assert_called_once()

    def test_stream_metadata_overhead_does_not_exhaust_code_size_budget(self):
        content = '{"ok":true}'
        pieces = [{"message": {"content": char}, "done": False}
                  for char in content]
        raw = events(*pieces, {"done": True})
        # Raw NDJSON has repeated headers much larger than 256 bytes;
        # actual generated JSON is only 11 bytes.
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(model, "MAX_OLLAMA_DEVELOPER_STREAM_BYTES", 256), \
             patch.object(model.urllib.request, "urlopen",
                          return_value=raw) as network:
            output = model._ollama_chat(OLLAMA, "Prompt", {"type": "object"},
                                        worker_id="webapp_developer")
        self.assertEqual(json.loads(output), {"ok": True})
        network.assert_called_once()

    def test_stream_event_count_is_bounded(self):
        raw = events(
            {"message": {"content": "a"}, "done": False},
            {"message": {"content": "b"}, "done": False},
            {"message": {"content": "c"}, "done": False},
            {"done": True},
        )
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(model, "MAX_OLLAMA_DEVELOPER_STREAM_EVENTS", 2), \
             patch.object(model.urllib.request, "urlopen",
                          return_value=raw) as network:
            with self.assertRaisesRegex(RuntimeError, "safe size limit"):
                model._ollama_chat(OLLAMA, "Prompt", {"type": "object"},
                                   worker_id="webapp_developer")
        network.assert_called_once()

    def test_closed_stream_does_not_accept_partial_json_or_retry(self):
        partial = events({"message": {"content": '{"ok":true}'}, "done": False})
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(model.urllib.request, "urlopen",
                          return_value=partial) as network:
            with self.assertRaisesRegex(RuntimeError, "before done") as caught:
                model._ollama_chat(OLLAMA, "Prompt", {"type": "object"},
                                   worker_id="webapp_developer")
        network.assert_called_once()
        safe = skill_runner._safe_failure("webapp.develop", caught.exception)
        self.assertTrue(safe.startswith("MODEL_STREAM_INCOMPLETE:"), safe)

    def test_stream_size_limit_rejects_without_accepting_any_proposal(self):
        raw = events({"message": {"content": "x" * 100}, "done": True})
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(model, "MAX_OLLAMA_DEVELOPER_STREAM_BYTES", 40), \
             patch.object(model.urllib.request, "urlopen",
                          return_value=raw) as network:
            with self.assertRaisesRegex(RuntimeError, "safe size limit") as caught:
                model._ollama_chat(OLLAMA, "Prompt", {"type": "object"},
                                   worker_id="webapp_developer")
        network.assert_called_once()
        self.assertIn("MODEL_STREAM_TOO_LARGE",
                      skill_runner._safe_failure("webapp.develop", caught.exception))

    def test_invalid_stream_event_never_leaks_provider_message(self):
        secret = "token-DO-NOT-PERSIST"
        raw = events({"error": secret, "done": True})
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(model.urllib.request, "urlopen",
                          return_value=raw) as network:
            with self.assertRaisesRegex(RuntimeError, "invalid event") as caught:
                model._ollama_chat(OLLAMA, "Prompt", {"type": "object"},
                                   worker_id="webapp_developer")
        network.assert_called_once()
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn(secret, skill_runner._safe_failure(
            "webapp.develop", caught.exception))

    def test_explicit_developer_timeout_override_stays_bounded(self):
        with patch.dict(os.environ, {"AGENTFORGE_DEVELOPER_TIMEOUT_SECONDS":"900"},
                        clear=True):
            self.assertEqual(model._request_timeout("webapp_developer"), 900)
            self.assertEqual(model._request_timeout("webapp_architect"), 180)
        for invalid in ("0", "59", "901", "-1", "ten", "99999999"):
            with self.subTest(value=invalid), \
                 patch.dict(os.environ, {
                     "AGENTFORGE_DEVELOPER_TIMEOUT_SECONDS": invalid
                 }, clear=True), \
                 patch.object(model.urllib.request, "urlopen") as network:
                with self.assertRaises(ModelConfigError):
                    model._ollama_chat(OLLAMA, "Prompt", {"type": "object"},
                                       worker_id="webapp_developer")
                network.assert_not_called()

    def test_cloud_developer_uses_longer_timeout_without_retries(self):
        answer = {"stop_reason":"end_turn", "content":[
            {"type":"text","text":'{"ok":true}'}
        ]}
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(model, "_cloud_open",
                          return_value=io.BytesIO(json.dumps(answer).encode())) as network:
            output = model._anthropic_chat(
                CLOUD, "Prompt", {"type":"object"}, worker_id="webapp_developer")
        self.assertEqual(json.loads(output), {"ok": True})
        self.assertEqual(network.call_args.kwargs["timeout"], 600)
        self.assertEqual(json.loads(network.call_args.args[0].data)["max_tokens"], 8192)
        network.assert_called_once()

    def test_nested_urlerror_socket_timeout_uses_timeout_diagnostic(self):
        failure = URLError(socket.timeout("provider-PRIVATE"))
        safe = skill_runner._safe_failure("webapp.develop", failure)
        self.assertTrue(safe.startswith("MODEL_TIMEOUT:"), safe)
        self.assertNotIn("PRIVATE", safe)


if __name__ == "__main__":
    unittest.main()
