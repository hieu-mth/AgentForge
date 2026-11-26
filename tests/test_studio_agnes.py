import os
import unittest
from unittest.mock import patch

from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_motion_cloud, studio_agnes, studio_runtime
from agentforge.features.media import studio_agnes_image


class AgnesContractTests(unittest.TestCase):
    def profile(self, model):
        return {"id": "agnes_test", "provider": "agnes", "model": model, "enabled": True,
                "base_url_env": "AGNES_BASE_URL", "api_key_env": "AGNES_API_KEY"}

    def test_capabilities_and_routes(self):
        image = self.profile(studio_agnes.IMAGE_MODEL)
        video = self.profile("agnes-video-2.5-flash")
        self.assertIs(studio_runtime.image_adapter(image), studio_agnes_image)
        self.assertIs(studio_runtime.motion_adapter(video), draft_motion_cloud)
        self.assertTrue(model_hub.capability_contract("image.generate", image)["runtime_compatible"])
        self.assertFalse(model_hub.capability_contract("film.motion", image)["runtime_compatible"])
        self.assertTrue(model_hub.capability_contract("film.motion", video)["runtime_compatible"])
        self.assertEqual(draft_motion_cloud.billable_durations(video), tuple(range(4, 11)))

    def test_payload_and_poll(self):
        body = studio_agnes.payload("agnes-video-2.5-flash", "Cat walks", 4)
        self.assertEqual(body["seconds"], "4")
        self.assertEqual(body["mode"], "text")
        self.assertEqual(studio_agnes.image_payload("Cat", "16:9")["extra_body"]["response_format"], "b64_json")
        with patch.object(studio_agnes, "_request", return_value={"video_id": "job_123"}) as request:
            self.assertEqual(studio_agnes.submit(body, "fixture"), "job_123")
            request.assert_called_once_with("POST", "/v1/videos", "fixture", body)
        row = {"provider_id": "job_123", "model": body["model"]}
        with patch.object(studio_agnes, "_request", return_value={"status": "completed", "url": "https://example.com/result.mp4"}) as request:
            self.assertEqual(studio_agnes.poll(row, "fixture")["status"], "completed")
            self.assertIn("video_id=job_123", request.call_args.args[1])

    def test_endpoint_and_private_download_rejected(self):
        profile = self.profile(studio_agnes.IMAGE_MODEL)
        with patch.dict(os.environ, {"AGNES_BASE_URL": "https://example.com/v1", "AGNES_API_KEY": "fixture"}):
            with self.assertRaises(ValueError):
                studio_agnes.key(profile)
        with patch.object(studio_agnes.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ValueError):
                studio_agnes._public_addresses("example.com")
