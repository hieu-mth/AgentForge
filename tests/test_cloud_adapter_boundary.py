"""Cloud transport and technical video verification share provider-neutral ports."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentforge.ai import registry
from agentforge.features.film_studio import draft_motion_cloud, studio_agnes
from agentforge.features.film_studio.studio_contracts import ProviderRequestError
from agentforge.features.media import mp4


class CloudBoundaryTests(unittest.TestCase):
    def test_new_transport_resolves_without_lifecycle_change(self):
        adapter = SimpleNamespace(supports_video=lambda profile: profile.get("provider") == "fixture",
                                  DURATIONS=(5, 10), NATIVE_AUDIO=False)
        entry = registry.Registration("cloud_video_transport", lambda: adapter, predicate="supports_video")
        with patch.object(registry, "REGISTRATIONS", (*registry.REGISTRATIONS, entry)):
            profile = {"provider": "fixture", "model": "alternate"}
            self.assertTrue(draft_motion_cloud.supports(profile))
            self.assertIs(draft_motion_cloud._transport(profile), adapter)
            self.assertEqual(draft_motion_cloud.billable_durations(profile), (5, 10))
            self.assertFalse(draft_motion_cloud.native_audio(profile))

    def test_unknown_provider_error_cannot_authorize_retry(self):
        with self.assertRaises(ValueError):
            ProviderRequestError("unknown", retryable=True)
        error = studio_agnes.AgnesHTTPError(503, "video_queue_full")
        self.assertIsInstance(error, ProviderRequestError)
        self.assertTrue(error.rejected)
        self.assertTrue(error.retryable)
        with patch.object(draft_motion_cloud, "_db") as db:
            with self.assertRaises(ValueError):
                draft_motion_cloud.reject_submission("a" * 32, ProviderRequestError("unknown"))
            db.assert_not_called()

    def test_media_verifier_uses_explicit_output_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.mp4"
            path.write_bytes(b"0" * 2048)
            metadata = SimpleNamespace(stdout='{"streams":[{"width":320,"height":192,"avg_frame_rate":"30/1"}]}')
            decoded = SimpleNamespace(stdout="frame=150\n")
            with (patch.object(mp4.render, "find_media_tool", return_value="ffprobe"),
                  patch.object(mp4.render, "_ffmpeg", return_value="ffmpeg"),
                  patch.object(mp4.render, "_run_process", side_effect=[metadata, decoded, metadata])):
                digest = mp4.verify_video(path, 5, fps=30, resolution=(320, 192))
                self.assertEqual(len(digest), 64)
                with self.assertRaisesRegex(ValueError, "approved profile"):
                    mp4.verify_video(path, 5, fps=24, resolution=(1280, 720))


if __name__ == "__main__":
    unittest.main()
