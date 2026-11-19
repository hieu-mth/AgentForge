"""Local runtime discovery remains a read-only metadata probe."""
import unittest
from unittest.mock import patch

from agentforge.ops import discovery


class RuntimeDiscoveryTests(unittest.TestCase):
    def test_comfy_catalog_error_does_not_change_runtime_health(self):
        with (patch.object(discovery.comfyui, "request_json", return_value={"devices": []}) as stats,
              patch.object(discovery, "_comfy_catalog_at_port", return_value=([], "TIMEOUT"))):
            service, _ = discovery._comfy(8188)
        stats.assert_called_once_with("/system_stats", port=8188, timeout=5)
        self.assertEqual(service["status"], "RUNNING")
        self.assertTrue(service["catalog_errors"])
        self.assertTrue(service["checked_at"])

    def test_comfy_distinguishes_auth_timeout_and_connection_errors(self):
        for error, expected in (
            (discovery.comfyui.ComfyHTTPError(401), "AUTH_REQUIRED"),
            (TimeoutError(), "COMFYUI_TIMEOUT"),
            (ConnectionRefusedError(), "COMFYUI_UNAVAILABLE"),
        ):
            with self.subTest(expected=expected), patch.object(discovery.comfyui, "request_json", side_effect=error):
                service, models = discovery._comfy(8188)
                self.assertEqual(service["error"], expected)
                self.assertEqual(models, [])

    def test_version_check_is_bounded(self):
        with patch.object(discovery, "_command", return_value="ffmpeg version 7\n"):
            report = discovery._software("ffmpeg", "ffmpeg", "-version")
            self.assertEqual(report["status"], "READY")
            self.assertEqual(report["id"], "ffmpeg")

    def test_ollama_catalog_does_not_invoke_inference(self):
        result = {"models": [
            {"name": "local-model:1b", "size": 1234,
             "details": {"family": "test"}}]}
        with patch.object(discovery.probes, "_http_json", return_value=result) as http:
            service, models = discovery._ollama("http://127.0.0.1:11434")
        http.assert_called_once_with("127.0.0.1", 11434, "/api/tags", timeout=2)
        self.assertEqual(service["status"], "RUNNING")
        self.assertEqual(models[0]["status"], "INSTALLED")
        self.assertEqual(models[0]["loadability"], "UNKNOWN")

    def test_missing_gpu_is_not_reported_ready(self):
        with patch.object(discovery.shutil, "which", return_value=None):
            value = discovery._gpu()
        self.assertEqual(value["status"], "UNKNOWN")
        self.assertEqual(value["devices"], [])


if __name__ == "__main__":
    unittest.main()
