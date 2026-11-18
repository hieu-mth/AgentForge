"""Runtime certification requires explicit opt-ins, never claims GPU proof."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agentforge.ops import runtime_certification as cert


class RuntimeCertificationTests(unittest.TestCase):
    def test_only_loopback_urls_are_accepted(self):
        self.assertEqual(cert._local_endpoint("http://127.0.0.1:11434"),
                         ("127.0.0.1", 11434))
        for target in ("https://127.0.0.1:11434", "http://example.org:11434",
                       "http://127.0.0.1:11434/path"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                cert._local_endpoint(target)

    def test_default_preflight_does_not_start_inference_or_gpu(self):
        with patch.object(cert, "_ollama_preflight", return_value={"status": "UNAVAILABLE"}), \
             patch.object(cert, "_comfy_preflight", return_value={"status": "UNAVAILABLE"}), \
             patch.object(cert, "_ffmpeg_preflight", return_value={"status": "UNAVAILABLE"}), \
             patch.object(cert, "_dashboard_preflight", return_value={"status": "UNAVAILABLE"}):
            report = cert.inspect()
        self.assertFalse(report["production_go"])
        self.assertFalse(report["real_gpu_video_verified"])
        self.assertFalse(report["explicit_authorization"]["local_ollama_inference"])
        self.assertFalse(report["explicit_authorization"]["disposable_ffmpeg_fixture"])
        self.assertEqual(report["gpu_jobs_submitted"], 0)

    def test_bounded_structural_mp4_rejects_garbage(self):
        from agentforge.features.media.mp4 import _mp4_structural
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "garbage.mp4"
            source.write_bytes(b"0" * 1024)
            with self.assertRaises(ValueError):
                _mp4_structural(source)


if __name__ == "__main__":
    unittest.main()
