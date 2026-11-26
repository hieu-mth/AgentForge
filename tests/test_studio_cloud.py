"""Cloud transport, permissions and actual storyboard integration (mocked HTTPS only)."""
import json
import os
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from agentforge.ai import model_hub, orchestrator_policy
from agentforge.features.film_studio import draft_pipeline as draft, studio_cloud


class CloudTextTests(unittest.TestCase):
    def profile(self, provider="openai"):
        return {"id": "cloud_writer", "provider": provider, "enabled": True,
                "model": "fixture/model", "base_url_env": "TEST_API_BASE",
                "api_key_env": "TEST_API_KEY"}

    def test_protocol_payloads_and_sanitized_failure(self):
        schema = {"type": "object"}
        for provider, route, response in (
            ("openai", "/chat/completions", {"choices": [{"finish_reason": "stop",
                "message": {"content": '{"ready":true}'}}]}),
            ("anthropic", "/messages", {"stop_reason": "end_turn",
                "content": [{"type": "text", "text": '{"ready":true}'}]}),
        ):
            with self.subTest(provider=provider), patch.object(studio_cloud, "_request", return_value=response) as request:
                self.assertEqual(studio_cloud.infer_structured(self.profile(provider), "Test", {}, schema), {"ready": True})
                self.assertEqual(request.call_args.args[1:3], ("POST", route))
                self.assertEqual(request.call_args.args[3]["model"], "fixture/model")
        with patch.dict(os.environ, {"TEST_API_BASE": "https://example.test/v1", "TEST_API_KEY": "fixture-key"}):
            with patch("http.client.HTTPSConnection") as connection:
                response = connection.return_value.getresponse.return_value
                response.status = 429
                with self.assertRaisesRegex(ValueError, "RATE_OR_QUOTA_LIMIT"):
                    studio_cloud.probe(self.profile())
                response.read.assert_not_called()
                connection.return_value.close.assert_called_once()

    def test_cloud_only_storyboard_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(model_hub, "DB_PATH", Path(tmp)/"hub.db"), \
                patch.object(draft, "DB", Path(tmp)/"draft.db"), patch.object(draft, "_dispatch"):
            profile = self.profile()
            model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, profile=profile)
            policy = orchestrator_policy.defaults()
            policy["permissions"].update(plan=True, assign_models=True, call_cloud=True)
            policy["cloud_call_limit"] = 2
            model_hub.change("SET_MODEL_ROUTE", expected_revision=1, task_id="general.text", model_ref=profile["id"])
            model_hub.change("SET_MODEL_ROUTE", expected_revision=2, task_id="film.storyboard", model_ref=profile["id"])
            model_hub.change("SAVE_ORCHESTRATOR", expected_revision=3, policy=policy)
            brief = {"id": "a"*32, "idea": "A cat", "seconds": 6, "scene_count": 2, "ratio": "16:9"}
            job = draft.submit(brief)
            board = {"title": "Cat", "continuity": "Same cat", "scenes": [
                {"description": "Cat sits", "image_prompt": "Cat in room", "audio": "Quiet", "character_ids": []},
                {"description": "Cat stands", "image_prompt": "Cat stands in room", "audio": "Quiet", "character_ids": []}]}
            with (patch.object(model_hub, "local_inference_slot", side_effect=AssertionError("local inference")),
                  patch.object(draft.draft_resources, "snapshot", side_effect=AssertionError("local resource check")),
                  patch.object(draft.characters, "list_characters", return_value={"characters": []}),
                  patch.dict(os.environ, {"TEST_API_BASE": "https://example.test/v1", "TEST_API_KEY": "fixture-key"}),
                  patch("http.client.HTTPSConnection") as connection):
                response = connection.return_value.getresponse.return_value
                response.status = 200
                response.read.side_effect = [
                    json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}).encode()
                    for result in ({"outline": "Cat sits and stands."}, board)]
                draft._work(job, nullcontext())
                self.assertEqual(connection.return_value.request.call_count, 2)
                self.assertEqual(connection.return_value.request.call_args.args[:2],
                                 ("POST", "/v1/chat/completions"))
            saved = draft._read(job["id"])
            self.assertEqual(saved["status"], "STORYBOARD_REVIEW", saved.get("error"))
            self.assertEqual(saved["cloud_calls"], 2)
            with patch.object(studio_cloud, "infer_structured", side_effect=AssertionError("budget bypass")):
                with self.assertRaisesRegex(ValueError, "ngân sách"):
                    draft._ask(profile, "Test", {}, {}, None, job=saved)
            self.assertFalse(policy["permissions"]["call_local"])
            policy["permissions"]["call_cloud"] = False
            model_hub.change("SAVE_ORCHESTRATOR", expected_revision=4, policy=policy)
            with patch.object(studio_cloud, "infer_structured", side_effect=AssertionError("revoked permission")):
                with self.assertRaises(PermissionError):
                    draft._ask(profile, "Test", {}, {}, None, job=saved)

    def test_dashboard_auto_motion_with_cloud_and_pause_between_requests(self):
        for pause in (False, True):
            with (self.subTest(pause=pause), tempfile.TemporaryDirectory() as tmp,
                  patch.object(model_hub, "DB_PATH", Path(tmp)/"hub.db"),
                  patch.object(draft, "DB", Path(tmp)/"draft.db"),
                  patch.object(draft, "_dispatch"),
                  patch.object(model_hub, "local_inference_slot", side_effect=AssertionError("local inference")),
                  patch.object(draft.draft_resources, "snapshot", side_effect=AssertionError("local resource check")),
                  patch.object(draft.characters, "list_characters", return_value={"characters": []}),
                  patch.dict(os.environ, {"TEST_API_BASE": "https://example.test/v1", "TEST_API_KEY": "fixture-key"}),
                  patch("http.client.HTTPSConnection") as connection):
                profile = self.profile("anthropic")
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, profile=profile)
                policy = orchestrator_policy.defaults()
                policy["permissions"].update(plan=True, assign_models=True, call_cloud=True)
                model_hub.change("SET_MODEL_ROUTE", expected_revision=1, task_id="general.text", model_ref=profile["id"])
                model_hub.change("SET_MODEL_ROUTE", expected_revision=2, task_id="film.storyboard", model_ref=profile["id"])
                model_hub.change("SAVE_ORCHESTRATOR", expected_revision=3, policy=policy)
                job = draft.submit({"id": "b"*32, "idea": "Mèo nhìn cửa rồi bước đi.",
                                    "seconds": None, "scene_count": None, "ratio": "16:9",
                                    "mode": "motion", "duration_mode": "auto"})
                plan = {"estimated_duration_seconds": 4, "production_feasibility": "feasible",
                        "duration_reasoning": "Hai hành động ngắn.", "shots": [
                            {"action": "Mèo nhìn cửa.", "reason": "Mở đầu", "suggested_seconds": 2},
                            {"action": "Mèo bước đi.", "reason": "Tiếp nối", "suggested_seconds": 2}]}
                shots = [{"title": "Mèo", "continuity": "Cùng căn phòng", "description": desc,
                          "image_prompt": prompt, "audio": "Quiet"}
                         for desc, prompt in (("Mèo nhìn cửa", "Cat looks at door"),
                                              ("Mèo bước đi", "Cat walks away"))]
                results = iter([plan, *shots])
                response = connection.return_value.getresponse.return_value
                response.status = 200
                paused = False

                def read(_size):
                    nonlocal paused
                    result = next(results)
                    paused = pause
                    return json.dumps({"stop_reason": "end_turn",
                                       "content": [{"type": "text", "text": json.dumps(result)}]}).encode()

                def require_active():
                    if paused:
                        raise PermissionError("OPERATIONS_PAUSED: Owner must resume before new dispatch")

                response.read.side_effect = read
                with (patch.object(draft.ops_control, "require_active", side_effect=require_active),
                      patch.object(draft.studio_runtime, "image_adapter", side_effect=AssertionError("image adapter")),
                      patch.object(draft.studio_runtime, "motion_adapter", side_effect=AssertionError("motion adapter"))):
                    draft._work(job, nullcontext())
                saved = draft._read(job["id"])
                if pause:
                    self.assertEqual(saved["status"], "FAILED")
                    self.assertIn("OPERATIONS_PAUSED", saved["error"])
                    self.assertEqual(saved["cloud_calls"], 1)
                    self.assertEqual(connection.return_value.request.call_count, 1)
                else:
                    self.assertEqual(saved["status"], "STORYBOARD_REVIEW", saved.get("error"))
                    self.assertEqual(saved["brief"]["seconds"], 4)
                    self.assertEqual(len(saved["board"]["scenes"]), 2)
                    self.assertEqual(saved["cloud_calls"], 3)
                    self.assertEqual(connection.return_value.request.call_count, 3)
                    self.assertEqual(connection.return_value.request.call_args.args[:2], ("POST", "/v1/messages"))
                    self.assertTrue(saved["deferred_media_binding"])
                    self.assertNotIn("motion_plan", saved)

    def test_cloud_metadata_uses_https_without_post_or_redirect(self):
        with (patch.dict(os.environ, {"TEST_API_BASE": "https://example.test/v1", "TEST_API_KEY": "fixture-key"}),
              patch("http.client.HTTPSConnection") as connection):
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"id":"fixture/model"}'
            self.assertEqual(studio_cloud.readiness(self.profile()), "READY")
            self.assertEqual(connection.return_value.request.call_args.args[:2],
                             ("GET", "/v1/models/fixture%2Fmodel"))
            self.assertEqual(connection.return_value.request.call_args.kwargs["headers"]["Authorization"],
                             "Bearer fixture-key")
            response.status = 302
            self.assertEqual(studio_cloud.readiness(self.profile()), "HTTP_302")
            self.assertEqual(connection.return_value.request.call_count, 2)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_direct_key_roundtrip(self):
        from agentforge.ai import cloud_credentials
        value = cloud_credentials.protect_api_key("fixture-key")
        self.assertNotEqual(value, "fixture-key")
        self.assertEqual(cloud_credentials.unprotect_api_key(value), "fixture-key")
