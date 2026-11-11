"""Wave 4 safety/quality regression probes, all synthetic and local.

No paid inference, ComfyUI GPU, owner data, external requests or publishing.
"""
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from agentforge import model
from agentforge.ai import model_health, model_hub
from agentforge.features.media import visual_jobs
from agentforge.features.websites import structured_builder, image_studio
from agentforge.integrations import comfyui


OLLAMA = {"model": "test", "base_url": "http://127.0.0.1:11434",
          "system_prompt": "test"}
CLOUD = {"model": "test", "base_url": "https://gateway.example/v1",
         "api_key": "SYNTHETIC-NO-REAL-SECRET", "system_prompt": "test"}


class ModelEnvelopeTests(unittest.TestCase):
    def test_ollama_json_rejects_oversized_envelope_before_parse(self):
        raw = json.dumps({"message": {"content": "x" * 300}}).encode()
        with patch.object(model, "MAX_MODEL_RESPONSE_BYTES", 100), \
             patch.object(model.urllib.request, "urlopen",
                          return_value=io.BytesIO(raw)) as network:
            with self.assertRaisesRegex(RuntimeError, "safe size limit"):
                model._ollama_chat(OLLAMA, "test", None)
        network.assert_called_once()

    def test_cloud_json_rejects_oversized_envelope_without_retry(self):
        raw = json.dumps({"content": [{"type": "text", "text": "x" * 250}]}).encode()
        with patch.object(model, "MAX_MODEL_RESPONSE_BYTES", 80), \
             patch.object(model, "_cloud_open",
                          return_value=io.BytesIO(raw)) as network:
            with self.assertRaisesRegex(RuntimeError, "safe size limit"):
                model._anthropic_chat(CLOUD, "test", None)
        network.assert_called_once()

    def test_stream_readline_is_bounded_before_json_parse(self):
        line = b'{"message":{"content":"' + b"x" * 300 + b'"}}\n'
        with patch.object(model, "MAX_OLLAMA_STREAM_LINE_BYTES", 64), \
             patch.object(model.urllib.request, "urlopen",
                          return_value=io.BytesIO(line)) as network:
            with self.assertRaisesRegex(RuntimeError, "safe size limit"):
                model._ollama_chat(OLLAMA, "test", {"type": "object"},
                                   worker_id="webapp_developer")
        network.assert_called_once()

    def test_stream_wire_envelope_limits_repeated_metadata(self):
        body = b''.join(
            b'{"message":{"content":"a"},"done":false}\n' for _ in range(10))
        with patch.object(model, "MAX_OLLAMA_STREAM_WIRE_BYTES", 100), \
             patch.object(model.urllib.request, "urlopen",
                          return_value=io.BytesIO(body)) as network:
            with self.assertRaisesRegex(RuntimeError, "safe size limit"):
                model._ollama_chat(OLLAMA, "test", {"type": "object"},
                                   worker_id="webapp_developer")
        network.assert_called_once()

    def test_monotonic_budget_rejects_trickling_nonstream_response(self):
        clock = [0.0]
        class Trickle(io.BytesIO):
            def read1(self, size=-1):
                clock[0] += 1.1
                return super().read1(min(size, 2))
        raw = json.dumps({"message": {"content": "hello"}}).encode()
        with patch.object(model, "_request_timeout", return_value=2), \
             patch.object(model.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(model.urllib.request, "urlopen",
                          return_value=Trickle(raw)) as network:
            with self.assertRaisesRegex(TimeoutError, "total deadline"):
                model._ollama_chat(OLLAMA, "test", None)
        network.assert_called_once()

    def test_monotonic_budget_rejects_cloud_trickle_and_keeps_original_timeout(self):
        clock = [0.0]
        class Trickle(io.BytesIO):
            def read1(self, size=-1):
                clock[0] += 1.1
                return super().read1(min(size, 2))
        with patch.object(model, "_request_timeout", return_value=2), \
             patch.object(model.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(model, "_cloud_open",
                          return_value=Trickle(b'{"content":[]}')) as network:
            with self.assertRaisesRegex(TimeoutError, "total deadline"):
                model._anthropic_chat(CLOUD, "test", None)
        self.assertEqual(network.call_args.kwargs["timeout"], 2)
        network.assert_called_once()


class ImageLoopbackTests(unittest.TestCase):
    def test_unsafe_image_routes_fail_before_network(self):
        bad = ["/view?filename=../../secret&subfolder=&type=output",
               "//evil/collect", "/anything",
               "/view?filename=af_" + "0" * 32 + "_ok.png&subfolder=x&type=output",
               "/view?filename=af_" + "0" * 32 + "_ok.png&subfolder=&type=input",
               "/view?filename=af_" + "0" * 32 + "_ok.png&subfolder=&type=output&x=1",
               "/models/checkpoints?redirect=https://evil.example",
               "http://evil.example/view", "/prompt"]
        for path in bad:
            with self.subTest(path=path):
                with self.assertRaises(comfyui.ComfyUITransportError):
                    comfyui.request_image_bytes(path)
        with self.assertRaises(comfyui.ComfyUITransportError):
            comfyui.request_image_bytes("/history/" + "x" * 36)

    def test_image_transport_blocks_302_and_does_not_honor_environment_proxy(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.server.seen.append(self.path)
                if self.path == "/models/checkpoints":
                    self.send_response(302)
                    self.send_header("Location", "https://external.example/collect")
                else:
                    self.send_response(200)
                self.end_headers()
                self.wfile.write(b'["demo.safetensors"]')
            def log_message(self, *args): pass
        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            server.seen = []
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.dict(os.environ, {
                    "HTTP_PROXY": "http://proxy.invalid:9999",
                    "HTTPS_PROXY": "http://proxy.invalid:9999"}, clear=False):
                    with self.assertRaisesRegex(RuntimeError, "non-success"):
                        comfyui.request_image_bytes(
                            "/models/checkpoints", port=server.server_port)
                self.assertEqual(server.seen, ["/models/checkpoints"])
            finally:
                server.shutdown()
                thread.join(timeout=3)

    def test_image_studio_default_dispatch_uses_hardened_transport(self):
        with patch.object(image_studio._comfyui, "request_image_bytes",
                          return_value=b'[]') as hardened, \
             patch.object(image_studio.urllib.request, "urlopen") as unsafe:
            self.assertEqual(image_studio._request("/models/checkpoints"), b'[]')
        hardened.assert_called_once()
        unsafe.assert_not_called()

    def test_ollama_metadata_probe_does_not_use_proxy_or_follow_redirect(self):
        runtime = {"provider": "ollama", "base_url": "http://127.0.0.1:11434",
                   "model": "demo"}
        with patch.object(model_health.urllib.request, "build_opener") as build:
            build.return_value.open.side_effect = urllib.error.HTTPError(
                "http://127.0.0.1:11434/api/tags", 302, "moved", {}, None)
            result = model_health.check(resolve=lambda *_: runtime)
        self.assertEqual(result["status"], "UNAVAILABLE")
        handlers = build.call_args.args
        self.assertTrue(any(isinstance(h, urllib.request.ProxyHandler)
                            and not h.proxies for h in handlers))
        self.assertTrue(any(isinstance(h, urllib.request.HTTPRedirectHandler)
                            and h.redirect_request(
                                urllib.request.Request("http://127.0.0.1:11434/api/tags"),
                                None, 302, "moved", {},
                                "https://external.example") is None
                            for h in handlers))


class ProductQualityAndRoutingTests(unittest.TestCase):
    def test_distinct_scenes_survive_450_char_topic_with_policy_suffix(self):
        first = visual_jobs._prompt("M" * 450, "A sunny retail bedroom with timber floors", 0, "video")
        second = visual_jobs._prompt("M" * 450, "An overhead warehouse loading scene", 1, "video")
        for value in (first, second):
            self.assertLessEqual(len(value), 450)
            self.assertTrue(value.endswith("Full scene, clearly visible subject."))
            self.assertIn("No text, logos, watermark", value)
            self.assertIn("Product/subject:", value)
        self.assertIn("sunny retail bedroom", first)
        self.assertIn("overhead warehouse", second)
        self.assertNotEqual(first, second)

    def test_deterministic_routes_are_never_wired_to_model(self):
        routes = {x["id"]: x for x in model_hub.catalog()["routes"]}
        for name in ("analytics.quality_check", "growth.report"):
            route = routes[name]
            self.assertEqual(route["status"], "DETERMINISTIC")
            self.assertIsNone(route["model_ref"])
            self.assertEqual(route["kind"], "rules")
            self.assertFalse(route["runtime_wired"])

    def test_old_owner_routes_are_ignored_read_only_in_new_model_hub(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "legacy.sqlite3"
            with closing(sqlite3.connect(db_path)) as db, db:
                db.execute("CREATE TABLE hub_state(id INTEGER PRIMARY KEY, "
                           "revision INTEGER NOT NULL,payload TEXT NOT NULL)")
                db.execute("INSERT INTO hub_state VALUES(1,1,?)", (
                    json.dumps({"profiles": {}, "routes": {
                        "analytics.quality_check": "local_primary",
                        "growth.report": "cloud_primary"}}),))
            before = db_path.read_bytes()
            routes = {x["id"]: x for x in model_hub.catalog(
                db_path=db_path)["routes"]}
            self.assertEqual(db_path.read_bytes(), before)
            for name in ("analytics.quality_check", "growth.report"):
                self.assertEqual(routes[name]["source"], "legacy_inactive")
                self.assertIsNone(routes[name]["model_ref"])
                self.assertEqual(routes[name]["status"], "DETERMINISTIC")
            with self.assertRaises(ValueError):
                model_hub.change("SET_MODEL_ROUTE", expected_revision=1,
                                 db_path=db_path, task_id="growth.report",
                                 model_ref="local_primary")

    def test_compatibility_renderer_preserves_validated_theme_layout(self):
        # The default AI Designer has its own renderer; keep older helper valid.
        required = structured_builder.COPY_SCHEMA["required"]
        body = {"brand": "Gia đình", "headline": "Giải pháp giấc ngủ",
                "subtitle": "Tham khảo sản phẩm phù hợp",
                "introduction": "Tư vấn thông tin cơ bản",
                "call_to_action": "Liên hệ để được tư vấn",
                "highlights": [
                    {"title": "Vật liệu", "description": "Thảo luận về nhu cầu"},
                    {"title": "Kích thước", "description": "Tùy chọn khác nhau"},
                ]}
        self.assertEqual(set(body), set(required))
        selected = {**body, "theme": "ocean", "layout": "centered"}
        validated = structured_builder.validate_copy(selected)
        self.assertEqual(validated["theme"], "ocean")
        self.assertEqual(validated["layout"], "centered")
        html = structured_builder.render(selected)
        self.assertIn('data-af-theme="ocean"', html)
        self.assertIn('data-af-layout="centered"', html)


if __name__ == "__main__":
    unittest.main()
