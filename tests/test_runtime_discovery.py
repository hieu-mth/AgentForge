"""Discovery must distinguish configuration, connection, and inference evidence."""
import json
import unittest
from unittest.mock import patch

from agentforge.integrations import comfyui
from agentforge.ops import discovery
from tests import test_control_center_v1


class RuntimeDiscoveryTests(unittest.TestCase):
    def test_ollama_catalog_is_installed_not_ready(self):
        with patch.object(discovery.probes, "_http_json", return_value={"models": [
            {"name": "local:tag", "size": 123, "details": {"family": "example"}},
        ]}) as request:
            status, models = discovery._ollama("http://127.0.0.1:11434")
        request.assert_called_once_with("127.0.0.1", 11434, "/api/tags", timeout=2)
        self.assertEqual(status["status"], "RUNNING")
        self.assertEqual(models[0]["status"], "INSTALLED")
        self.assertEqual(models[0]["loadability"], "UNKNOWN")
        self.assertEqual(models[0]["size_bytes"], 123)

    def test_ollama_connection_and_payload_failure(self):
        for error, expected in [(ConnectionRefusedError("SECRET"), "STOPPED"),
                                (TimeoutError("SECRET"), "DEGRADED"),
                                (ValueError("SECRET"), "ERROR")]:
            with self.subTest(expected=expected):
                with patch.object(discovery.probes, "_http_json", side_effect=error):
                    row, models = discovery._ollama("http://localhost:11434")
                self.assertEqual(row["status"], expected)
                self.assertNotIn("SECRET", str(row))
                self.assertEqual(models, [])

    def test_comfy_catalog_reports_partial_failure_and_discovery_only(self):
        def catalog(route, **kwargs):
            if route == "/models/clip":
                raise RuntimeError("unsupported route")
            return json.dumps(["observed.safetensors"]).encode()

        with patch.object(comfyui, "request_json", return_value={"devices": []}), \
                patch.object(comfyui, "request_image_bytes", side_effect=catalog):
            row, models = discovery._comfy(8188)
        self.assertEqual(row["status"], "DEGRADED")
        self.assertIn("clip", row["catalog_errors"])
        self.assertIn("loras", {m["type"] for m in models})
        self.assertTrue(all(m["loadability"] == "UNKNOWN" for m in models))
        for unsafe in ("/models/../../x", "/models/checkpoints?secret=x"):
            with self.assertRaises(ValueError):
                comfyui.validate_image_route(unsafe)
        with self.assertRaises(ValueError):
            comfyui.validate_image_route("/models/loras", has_body=True)

    def test_real_owner_http_snapshot(self):
        test = test_control_center_v1.TestControlCenterV1()
        test.setUp()
        try:
            self.assertEqual(test.req("GET", "/api/ops/discovery", cookie=False)[0], 401)
            test.login()
            code, result, _ = test.req("GET", "/api/ops/discovery")
            self.assertEqual(code, 200)
            self.assertGreater(result["hardware"]["disk"]["total_bytes"], 0)
            self.assertIn("os", result["hardware"])
            self.assertEqual(result["validation"]["capability_smoke"], "NOT_RUN")
        finally:
            test.tearDown()
