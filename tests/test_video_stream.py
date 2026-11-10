"""Streaming MP4 byte-range parsing and bounded server response tests."""
import io
import tempfile
import unittest
from pathlib import Path

from agentforge.api.video_stream import InvalidVideoRange, parse_range
from agentforge.api.server import Handler


class VideoRangeTests(unittest.TestCase):
    def test_standard_and_suffix_ranges(self):
        self.assertEqual(parse_range(None, 100), (0, 99, False))
        self.assertEqual(parse_range("bytes=0-", 100), (0, 99, True))
        self.assertEqual(parse_range("bytes=10-20", 100), (10, 20, True))
        self.assertEqual(parse_range("bytes=90-999", 100), (90, 99, True))
        self.assertEqual(parse_range("bytes=-20", 100), (80, 99, True))
        self.assertEqual(parse_range("bytes=-999", 100), (0, 99, True))

    def test_invalid_ranges_fail_closed(self):
        for bad in ("", "bytes=-", "bytes=100-", "bytes=20-10",
                    "bytes=0-1,3-5", "bytes=-0", "bytes=abc-def",
                    "units=1-2", "bytes=0-1\r\nInjected: x"):
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidVideoRange):
                    parse_range(bad, 100)
        with self.assertRaises(InvalidVideoRange):
            parse_range(None, 0)

    def test_bounded_stream_respects_requested_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "video.mp4"
            file.write_bytes(bytes(range(128)))
            class FakeHandler:
                _stream_video = Handler._stream_video
                def __init__(self):
                    self.headers = {"Range": "bytes=10-19"}
                    self.wfile = io.BytesIO()
                    self.response = None
                    self.headers_sent = {}
                def send_response(self, status):
                    self.response = status
                def send_header(self, name, value):
                    self.headers_sent[name] = value
                def end_headers(self):
                    pass
            handler = FakeHandler()
            handler._stream_video(file)
            self.assertEqual(handler.response, 206)
            self.assertEqual(handler.headers_sent["Content-Length"], "10")
            self.assertEqual(handler.headers_sent["Content-Range"], "bytes 10-19/128")
            self.assertEqual(handler.headers_sent["Accept-Ranges"], "bytes")
            self.assertEqual(handler.wfile.getvalue(), bytes(range(10, 20)))
            handler.headers.clear()
            handler.wfile = io.BytesIO()
            handler._stream_video(file)
            self.assertEqual(handler.response, 200)
            self.assertEqual(handler.wfile.getvalue(), bytes(range(128)))


if __name__ == "__main__":
    unittest.main()
