"""Cloud transport and technical video verification share provider-neutral ports."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentforge.ai import registry
from agentforge.features.film_studio import draft_motion_cloud, studio_agnes
from agentforge.features.film_studio.studio_contracts import MotionOutput, ProviderRequestError
from agentforge.features.media import mp4


class CloudBoundaryTests(unittest.TestCase):
    def test_new_transport_resolves_without_lifecycle_change(self):
        adapter = SimpleNamespace(supports_video=lambda profile: profile.get("provider") == "fixture",
                                  billable_durations=lambda profile: (5, 10, 15),
                                  native_audio=lambda profile: False,
                                  input_modes=lambda profile: ("image-to-video",),
                                  output_profile=lambda profile: MotionOutput(30, 450, (1920, 1080)))
        entry = registry.Registration("cloud_video_transport", lambda: adapter, predicate="supports_video")
        with patch.object(registry, "REGISTRATIONS", (*registry.REGISTRATIONS, entry)):
            profile = {"provider": "fixture", "model": "alternate"}
            self.assertTrue(draft_motion_cloud.supports(profile))
            self.assertIs(draft_motion_cloud._transport(profile), adapter)
            self.assertEqual(draft_motion_cloud.billable_durations(profile), (5, 10, 15))
            self.assertFalse(draft_motion_cloud.native_audio(profile))
            self.assertEqual(draft_motion_cloud.input_modes(profile), ("image-to-video",))
            self.assertEqual(draft_motion_cloud.output_profile(profile), MotionOutput(30, 450, (1920, 1080)))
            self.assertEqual(draft_motion_cloud._profile_seconds(301, profile), 15)
            job = {"motion_plan": {"output": {"fps": 30, "max_frames": 450, "resolution": [1920, 1080]}},
                   "production_plan": {"billable_durations_seconds": [5, 10, 15]},
                   "board": {"scenes": [{"frames": 150}, {"frames": 301}, {"frames": 450, "motion_job": "done"}]}}
            self.assertEqual(draft_motion_cloud.remaining_seconds(job), 20)
            with self.assertRaises(ValueError):
                draft_motion_cloud._profile_seconds(451, profile)

    def test_text_only_model_refuses_frame_continuation_before_dispatch(self):
        from agentforge.features.film_studio import draft_continuity, media_probe

        job = {"brief": {"mode": "motion"}, "board": {"scenes": [
            {"shot_id": "first"}, {"shot_id": "second", "continuity_plan": {
                "transition": "CONTINUE", "previous_shot_id": "first", "start_state": "cat sits", "end_state": "cat stands"}}]}}
        with self.assertRaisesRegex(ValueError, "CONTINUE"):
            draft_continuity.validate(job, input_modes=("text-to-video",))
        draft_continuity.validate(job, input_modes=("image-to-video",))
        adapter = SimpleNamespace(input_modes=lambda profile: ("image-to-video",))
        with (patch.object(media_probe.studio_runtime, "motion_adapter", return_value=adapter),
              patch.object(draft_motion_cloud, "_db") as db):
            with self.assertRaisesRegex(ValueError, "text-to-video"):
                media_probe._start_video("a" * 32, {}, "Cat")
            db.assert_not_called()

    def test_media_probe_accepts_only_verified_image_for_i2v(self):
        from agentforge.features.film_studio import media_probe
        adapter = SimpleNamespace(input_modes=lambda profile: ("image-to-video",))
        ident = "a" * 32
        with (patch.object(media_probe.studio_runtime, "motion_adapter", return_value=adapter),
              patch.object(media_probe.visual_jobs, "_row", return_value={"asset_sha": "b"*64}),
              patch.object(media_probe.visual_jobs, "read_motion_source", return_value=b"verified") as source):
            self.assertEqual(media_probe._video_input({}, ident), ("image-to-video", b"verified"))
            source.assert_called_once_with(ident, "b"*64)
        with (patch.object(media_probe.studio_runtime, "motion_adapter", return_value=adapter),
              patch.object(media_probe.visual_jobs, "_row") as row):
            with self.assertRaisesRegex(ValueError, "text-to-video"):
                media_probe._video_input({}, None)
            row.assert_not_called()

    def test_local_probe_reserves_once_and_polls_existing_ledger(self):
        from contextlib import closing
        from agentforge.features.film_studio import media_probe, motion_comfy, motion_ltx
        from agentforge.features.film_studio import draft_motion

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            record = motion_ltx.text_workflow()
            record["weights_sha256"] = {"checkpoint": "a"*64, "encoder": "b"*64}
            profile = {"provider": "comfyui", "model": motion_ltx.CHECKPOINT,
                       "motion_encoder": str(root / motion_ltx.ENCODER), "comfy_video": record}
            ident = "c"*32
            prompt = "A cat walks slowly across the quiet room."
            def reserve(**kw):
                with closing(motion_comfy._db(motion_comfy.DB, write=True)) as conn, conn:
                    conn.execute("INSERT INTO motion_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        ("d"*32, kw["film_slug"], kw["shot_id"], kw["plan_sha"], kw["workflow_sha"],
                         "e"*64, 42, None, "SUBMITTING", "created", "updated"))
            with (patch.object(motion_comfy, "DB", root / "motion.db"),
                  patch.object(motion_comfy, "FILMS", root / "films"),
                  patch.object(draft_motion, "bind", return_value=profile),
                  patch.object(motion_comfy, "submit_shot", side_effect=reserve) as submit):
                first = media_probe._local_video(ident, profile, prompt)
                self.assertEqual(first["status"], "NEEDS_RECONCILIATION")
                self.assertEqual(media_probe._local_video(ident, profile, prompt), first)
                self.assertEqual(media_probe._local_video(ident, profile), first)
                submit.assert_called_once()
                with self.assertRaisesRegex(ValueError, "another request"):
                    media_probe._local_video(ident, profile, prompt + " Different.")
                submit.assert_called_once()

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
