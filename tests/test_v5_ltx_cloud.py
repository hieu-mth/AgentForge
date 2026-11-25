import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge.features.film_studio import studio_ltx_cloud as ltx


class LtxPilotTests(unittest.TestCase):
    def test_reservation_before_submit_and_no_retry(self):
        body = ltx.payload("ltx-2-3-fast", "A cat walking", 6)
        ident = "a" * 32
        with tempfile.TemporaryDirectory() as folder, patch.object(ltx, "DB_PATH", Path(folder) / "pilot.sqlite3"), patch.object(ltx, "_key", return_value="fixture"):
            with patch.object(ltx, "_request", side_effect=ValueError("timeout")) as request:
                with self.assertRaises(ValueError):
                    ltx.submit(ident, body, max_seconds=6, confirmed=True)
                with self.assertRaises(ValueError):
                    ltx.submit(ident, body, max_seconds=6, confirmed=True)
                with self.assertRaises(ValueError):
                    ltx.submit("b" * 32, body, max_seconds=6, confirmed=True)
                self.assertEqual(request.call_count, 1)
            with self.assertRaises(ValueError):
                ltx.poll(ident, Path(folder))

    def test_async_submit_and_poll(self):
        body = ltx.payload("ltx-2-3-pro", "A cat walking", 8, audio=False)
        ident, remote = "a" * 32, "b" * 32
        with tempfile.TemporaryDirectory() as folder, patch.object(ltx, "DB_PATH", Path(folder) / "pilot.sqlite3"), patch.object(ltx, "_key", return_value="fixture"):
            with patch.object(ltx, "_request", side_effect=[{"id": remote}, {"id": remote, "status": "processing"}]) as request:
                with self.assertRaises(ValueError):
                    ltx.submit(ident, body, max_seconds=8)
                self.assertEqual(ltx.submit(ident, body, max_seconds=8, confirmed=True)["provider_id"], remote)
                self.assertEqual(ltx.poll(ident, Path(folder))["state"], "PROCESSING")
                self.assertEqual(request.call_args_list[0].args[:2], ("POST", "/v2/text-to-video"))
                self.assertEqual(request.call_args_list[1].args[:2], ("GET", "/v2/text-to-video/" + remote))

    def test_reject_untrusted_download_and_unsupported_duration(self):
        with self.assertRaises(ValueError):
            ltx._download("https://127.0.0.1/private", Path("unused"))
        with self.assertRaises(ValueError):
            ltx.payload("ltx-2-3-fast", "cat", 7)
