"""Local-only transport and stable Film Studio error/patch boundary."""
import io
import unittest
from unittest.mock import patch

from agentforge.integrations import comfyui
from agentforge.features.film_studio import motion_comfy as motion


class ComfyUIIntegrationTests(unittest.TestCase):
    def test_fixed_loopback_host_method_payload_and_bounded_response(self):
        with patch.object(comfyui.http.client, "HTTPConnection") as conn_type:
            conn = conn_type.return_value
            conn.getresponse.return_value.status = 200
            conn.getresponse.return_value.read.return_value = b'{"devices":[]}'
            self.assertEqual(comfyui.request_json("/system_stats"), {"devices": []})
            conn_type.assert_called_once_with("127.0.0.1", 8188, timeout=6)
            conn.request.assert_called_once_with(
                "GET", "/system_stats", body=None,
                headers={"Content-Type": "application/json", "Accept": "application/json"})
            conn.close.assert_called_once()

    def test_untrusted_paths_and_invalid_limits_cannot_open_connection(self):
        with patch.object(comfyui.http.client, "HTTPConnection") as connect:
            for path in ("http://remote/prompt", "//evil.test", "/prompt/../history",
                         "/history/../../x", "/system_stats?url=evil", "/queue"):
                with self.subTest(path=path), self.assertRaises(comfyui.ComfyUITransportError):
                    comfyui.request_json(path)
            with self.assertRaises(comfyui.ComfyUITransportError):
                comfyui.request_json("/prompt", port=0)
            with self.assertRaises(comfyui.ComfyUITransportError):
                comfyui.request_json("/prompt", max_response_bytes=1_000_000)
            connect.assert_not_called()

    def test_bounded_reply_invalid_json_and_redirect_are_rejected(self):
        with patch.object(comfyui.http.client, "HTTPConnection") as connect:
            response = connect.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"overflow":true}'
            with self.assertRaises(comfyui.ComfyUITransportError):
                comfyui.request_json("/system_stats", max_response_bytes=2)
            response.read.return_value = b'not json'
            with self.assertRaises(comfyui.ComfyUITransportError):
                comfyui.request_json("/system_stats")
            response.status = 302
            with self.assertRaises(RuntimeError):
                comfyui.request_json("/system_stats")

    def test_image_download_rejects_oversized_body(self):
        filename = "af_" + "a" * 32 + "_00001_.png"
        path = f"/view?filename={filename}&subfolder=&type=output"
        with patch.object(comfyui.http.client, "HTTPConnection") as connect:
            response = connect.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b"12345"
            with self.assertRaisesRegex(comfyui.ComfyUITransportError, "size limit"):
                comfyui.request_image_bytes(path, max_response_bytes=4)
            response.read.assert_called_once_with(5)
            connect.return_value.close.assert_called_once()

    def test_image_download_streams_and_stops_at_the_budget(self):
        path = "/view?filename=af_" + "a" * 32 + "_00001_.png&subfolder=&type=output"
        with patch.object(comfyui.http.client, "HTTPConnection") as connect:
            response = connect.return_value.getresponse.return_value
            response.status = 200
            response.read.side_effect = [b"12", b"34", b""]
            target = io.BytesIO()
            self.assertEqual(comfyui.request_image_bytes(path, max_response_bytes=4, sink=target), b"")
            self.assertEqual(target.getvalue(), b"1234")
            response.read.side_effect = [b"12", b"345"]
            target = io.BytesIO()
            with self.assertRaises(comfyui.ComfyUITransportError):
                comfyui.request_image_bytes(path, max_response_bytes=4, sink=target)
            self.assertEqual(target.getvalue(), b"12")

    def test_motion_errors_and_http_mock_point_remain_compatible(self):
        with patch.object(comfyui, "request_json", side_effect=comfyui.ComfyUITransportError("bad")) as api:
            with self.assertRaises(motion.MotionError):
                motion._json_request("/system_stats")
            api.assert_called_once_with("/system_stats", body=None, timeout=6,
                                        port=motion.PORT,
                                        max_response_bytes=motion.MAX_RESPONSE_BYTES)
        with patch.object(motion, "_json_request", return_value={"devices": []}) as mock:
            self.assertEqual("GPU_NOT_DETECTED", motion.health()["status"])
            mock.assert_called_once_with("/system_stats")


if __name__ == "__main__":
    unittest.main()
