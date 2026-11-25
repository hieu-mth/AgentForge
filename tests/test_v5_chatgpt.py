import io
import json
import unittest
from unittest.mock import patch

from agentforge.ai import chatgpt_auth, model_hub, orchestrator_policy
from agentforge.features.film_studio import studio_chatgpt
from agentforge.features.film_studio.studio_cloud import CloudRequestError


def event(value):
    return b"data: " + json.dumps(value).encode() + b"\n\n"


class ChatGPTTests(unittest.TestCase):
    def test_completed_stream_and_failure(self):
        delta = event({"type": "response.output_text.delta", "delta": '{"ready":true}'})
        done = event({"type": "response.completed", "response": {"status": "completed"}})
        self.assertEqual(studio_chatgpt.collect(io.BytesIO(delta + done)), '{"ready":true}')
        with self.assertRaisesRegex(CloudRequestError, "INCOMPLETE_RESPONSE"):
            studio_chatgpt.collect(io.BytesIO(delta))
        failure = event({"type": "response.failed", "response": {"error": {
            "code": "subscription_sharing_usage_limit_exceeded"}}})
        with self.assertRaisesRegex(CloudRequestError, "RATE_OR_QUOTA_LIMIT"):
            studio_chatgpt.collect(io.BytesIO(delta + failure))

    def test_oauth_state_and_client_binding(self):
        valid = {"state": ["state"], "client_id": ["oaiapp_test"], "code": ["code"]}
        self.assertEqual(chatgpt_auth._callback(valid, "state", None), ("oaiapp_test", "code"))
        for query, state, client in [(valid, "wrong", None), (valid, "state", "oaiapp_other"),
                                     ({**valid, "code": ["a", "b"]}, "state", None)]:
            with self.assertRaises(chatgpt_auth.AuthError):
                chatgpt_auth._callback(query, state, client)

    def test_explicit_plan_scope_required(self):
        data = {"scope": "openid", "access_token": "abc", "refresh_token": "def",
                "token_type": "Bearer", "expires_in": 3600}
        with self.assertRaises(chatgpt_auth.AuthError):
            chatgpt_auth._credentials(data)
        data["scope"] += " " + chatgpt_auth.PLAN_SCOPE
        with self.assertRaises(chatgpt_auth.AuthError):
            chatgpt_auth._credentials(data)
        data["scope"] += " resource.invoke"
        self.assertEqual(chatgpt_auth._credentials(data)["access_token"], "abc")

    def test_model_and_stream_payload(self):
        p = {"id": "director", "provider": "chatgpt", "model": "chosen-model",
             "enabled": True, "account_ref": "owner"}
        self.assertEqual(model_hub.validate_profile(p), p)
        self.assertTrue(orchestrator_policy.compatible("text", p))
        self.assertTrue(orchestrator_policy.compatible("vision", p))
        self.assertFalse(orchestrator_policy.local_adapter("text", p))
        with self.assertRaises(ValueError):
            model_hub.validate_profile({**p, "base_url": "https://evil.example"})
        with patch.object(studio_chatgpt, "request", return_value='{"ready":true}'):
            self.assertTrue(studio_chatgpt.probe(p)["inference_verified"])
