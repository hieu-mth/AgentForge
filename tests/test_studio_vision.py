"""Vision protocol fixtures and bounded, honest sampled-frame review."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge.ai import model_hub, orchestrator_policy
from agentforge.features.film_studio import draft_quality, studio_vision


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.result = {"verdict": "FAIL", "summary": "Wrong prop",
                       "issues": ["Wrong prop"], "repair_hint": "Keep red ball"}

    def test_vision_cloud_transports_attach_actual_image(self):
        for provider, route, reply in (
            ("openai", "/chat/completions", {"choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps(self.result)}}]}),
            ("anthropic", "/messages", {"stop_reason": "end_turn",
                "content": [{"type": "text", "text": json.dumps(self.result)}]}),
        ):
            with self.subTest(provider=provider), patch.object(studio_vision.studio_cloud, "_request", return_value=reply) as call:
                profile = {"provider": provider, "model": "fixture"}
                self.assertEqual(studio_vision.infer(profile, {}, b"image"), self.result)
                args = call.call_args.args
                self.assertEqual(args[1:3], ("POST", route))
                self.assertIn(base64.b64encode(b"image").decode(), json.dumps(args[3]))

    def test_vision_local_transport_attaches_image(self):
        profile = {"provider": "ollama", "model": "fixture", "base_url": "http://127.0.0.1:11434"}
        with (patch.object(studio_vision.runtime, "_installed_local_model", return_value=True),
              patch.object(studio_vision.runtime, "_http_json", return_value={
                  "done": True, "message": {"content": json.dumps(self.result)}}) as call):
            self.assertEqual(studio_vision.infer(profile, {}, b"image"), self.result)
            payload = call.call_args.kwargs["payload"]
            self.assertEqual(payload["messages"][1]["images"], [base64.b64encode(b"image").decode()])

    def test_character_description_uses_separate_schema(self):
        profile = {"provider": "ollama", "model": "fixture", "base_url": "http://127.0.0.1:11434"}
        result = {"appearance": "Mèo lông đen", "uncertainties": "Chưa rõ màu mắt"}
        with (patch.object(studio_vision.runtime, "_installed_local_model", return_value=True),
              patch.object(studio_vision.runtime, "_http_json", return_value={
                  "done": True, "message": {"content": json.dumps(result)}}) as call):
            self.assertEqual(studio_vision.describe_identity(profile, b"image"), result)
            self.assertEqual(call.call_args.kwargs["payload"]["format"], studio_vision.IDENTITY_SCHEMA)
        with patch.object(studio_vision, "_infer_json", return_value=self.result):
            with self.assertRaises(ValueError):
                studio_vision.describe_identity(profile, b"image")

    def test_invalid_verdict_and_unsubstantiated_fail_rejected(self):
        for bad in (dict(self.result, verdict="unknown"), dict(self.result, issues=[]), {}):
            with self.assertRaises(ValueError):
                studio_vision.validate_result(bad)

    def test_review_route_is_optional_and_requires_owner_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hub.sqlite3"
            with self.assertRaises(ValueError):
                model_hub.vision_binding(db_path=db)
            profile = {"id": "vision_fixture", "provider": "ollama", "model": "fixture",
                       "enabled": True, "base_url": "http://127.0.0.1:11434"}
            model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, db_path=db, profile=profile)
            policy = orchestrator_policy.defaults()
            model_hub.change("SET_MODEL_ROUTE", expected_revision=1, db_path=db,
                             task_id="vision.qa", model_ref=profile["id"])
            with self.assertRaises(PermissionError):
                model_hub.vision_binding(db_path=db)
            policy.update(permissions=dict.fromkeys(policy["permissions"], True), tools=["ffmpeg"])
            model_hub.change("SAVE_ORCHESTRATOR", expected_revision=2, db_path=db, policy=policy)
            self.assertEqual(model_hub.vision_binding(db_path=db)[1]["id"], profile["id"])

    def test_sampling_uses_exact_frame_boundaries_and_bounded_sheet(self):
        self.assertEqual(draft_quality.sample_indices([{"frames": 10}, {"frames": 8}], 1),
                         [(9, "PREVIOUS END"), (10, "SHOT START"), (14, "SHOT MID"), (17, "SHOT END")])
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("media extra not installed")
        image = io.BytesIO()
        Image.new("RGB", (320, 180), "orange").save(image, "PNG")
        sheet = draft_quality._sheet([(image.getvalue(), "SHOT START")]*5)
        self.assertLessEqual(len(sheet), studio_vision.MAX_SHEET_BYTES)
        with Image.open(io.BytesIO(sheet)) as result:
            self.assertEqual(result.format, "JPEG")
