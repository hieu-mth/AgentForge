"""Wave 1 security regressions: cloud redirects and Windows ZIP restore paths.

Uses only synthetic Bearer credentials, loopback HTTP and temporary archives.
Never makes paid model calls or writes business/production state.
"""
import hashlib
import io
import json
import os
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from agentforge import model, ops_backup


class CloudRedirectSecurityTests(unittest.TestCase):
    def test_redirect_handler_rejects_cross_host_and_https_downgrade(self):
        request = Request(
            "https://gateway.example/v1/messages", data=b"{}",
            headers={"Authorization": "Bearer SYNTHETIC_TEST_ONLY"}, method="POST")
        handler = model._RejectCloudRedirect()
        for code in (301, 302, 303, 307, 308):
            for destination in (
                    "https://other.example/collect",
                    "http://other.example/collect",
                    "https://gateway.example/other"):
                with self.subTest(code=code, destination=destination):
                    self.assertIsNone(handler.redirect_request(
                        request, None, code, "Redirect", {}, destination))

    def test_cloud_call_uses_restricted_opener_and_preserves_payload(self):
        runtime = {
            "base_url": "https://gateway.example/v1", "api_key": "TEST_ONLY",
            "model": "example-model", "system_prompt": "system",
        }
        body = {"content": [{"type": "text", "text": "OK"}]}
        with patch.object(model.urllib.request, "build_opener") as factory, \
             patch.object(model.urllib.request, "urlopen") as default_open:
            factory.return_value.open.return_value = io.BytesIO(json.dumps(body).encode())
            result = model._anthropic_chat(runtime, "prompt", None)
        self.assertEqual(result, "OK")
        default_open.assert_not_called()
        factory.assert_called_once()
        self.assertTrue(any(isinstance(h, model._RejectCloudRedirect)
                            for h in factory.call_args.args))
        request = factory.return_value.open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer TEST_ONLY")
        self.assertEqual(request.full_url, "https://gateway.example/v1/messages")
        self.assertEqual(factory.return_value.open.call_count, 1)

    def test_real_loopback_302_does_not_forward_authorization(self):
        class Sink(BaseHTTPRequestHandler):
            def do_GET(self):
                self.server.seen.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()

            do_POST = do_GET

            def log_message(self, *args):
                pass

        class Redirect(BaseHTTPRequestHandler):
            def do_POST(self):
                self.server.seen.append(self.headers.get("Authorization"))
                self.send_response(302)
                self.send_header("Location", self.server.destination)
                self.end_headers()

            def log_message(self, *args):
                pass

        with HTTPServer(("127.0.0.1", 0), Sink) as sink, \
             HTTPServer(("127.0.0.1", 0), Redirect) as redirect:
            sink.seen, redirect.seen = [], []
            redirect.destination = "http://127.0.0.1:%s/collect" % sink.server_port
            threads = [
                threading.Thread(target=sink.serve_forever, daemon=True),
                threading.Thread(target=redirect.serve_forever, daemon=True),
            ]
            for thread in threads:
                thread.start()
            try:
                request = Request(
                    "http://127.0.0.1:%s/messages" % redirect.server_port,
                    data=b"{}", headers={"Authorization": "Bearer SYNTHETIC"},
                    method="POST")
                with patch.dict(os.environ, {
                    "NO_PROXY": "127.0.0.1,localhost",
                    "no_proxy": "127.0.0.1,localhost"}):
                    with self.assertRaises(HTTPError) as error:
                        model._cloud_open(request, timeout=3)
                self.assertEqual(error.exception.code, 302)
                self.assertEqual(redirect.seen, ["Bearer SYNTHETIC"])
                self.assertEqual(sink.seen, [])
            finally:
                sink.shutdown()
                redirect.shutdown()
                for thread in threads:
                    thread.join(timeout=3)


class RestorePathSecurityTests(unittest.TestCase):
    def _archive(self, directory, name):
        raw = b"synthetic fixture"
        manifest = {
            "schema": 1,
            "contents": [{
                "path": name, "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "sqlite": False,
            }],
        }
        archive = directory / "agentforge-20261110T000000Z-abcdef12.zip"
        with zipfile.ZipFile(archive, "w") as out:
            out.writestr("manifest.json", json.dumps(manifest))
            out.writestr(name, raw)
        return archive

    def test_windows_drive_ads_device_unc_and_traversal_rejected_before_mkdir(self):
        malicious = [
            "workspace/products/D:/escape.txt",
            "workspace/products/C:relative.txt",
            "workspace/products/hero.jpg:secret",
            "workspace/products/CON.txt",
            "workspace/products/LPT1.txt",
            "workspace/products/folder./file.txt",
            "workspace/products/folder /file.txt",
            "workspace/products/../../escape.txt",
            "workspace/products//escape.txt",
            r"workspace/products/\\server\share\escape.txt",
            "/workspace/products/escape.txt",
            "workspace/products/bad\x00name.txt",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for idx, bad in enumerate(malicious):
                with self.subTest(path=bad):
                    archive = self._archive(root, bad)
                    destination = root / ("restore-%d" % idx)
                    with self.assertRaisesRegex(ops_backup.BackupError, "Unsafe"):
                        ops_backup.verify(archive)
                    with self.assertRaisesRegex(ops_backup.BackupError, "Unsafe"):
                        ops_backup.stage_restore(
                            archive, destination, confirm_restore=True)
                    self.assertFalse(destination.exists())

    def test_normal_nested_zip_entry_still_stages_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._archive(root, "workspace/products/site/index.html")
            self.assertEqual(ops_backup.verify(archive)["status"], "PASS")
            destination = root / "review"
            result = ops_backup.stage_restore(
                archive, destination, confirm_restore=True)
            self.assertEqual(result["status"], "RESTORED_TO_STAGING_ONLY")
            self.assertEqual(
                (destination / "workspace/products/site/index.html").read_bytes(),
                b"synthetic fixture")
            with self.assertRaisesRegex(ops_backup.BackupError, "must not exist"):
                ops_backup.stage_restore(
                    archive, destination, confirm_restore=True)


if __name__ == "__main__":
    unittest.main()
