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

    def test_dashboard_account_actions_are_owner_gated_and_never_return_tokens(self):
        from types import SimpleNamespace
        from agentforge.api.routes import model_hub as api
        server = SimpleNamespace(allow_external_actions=True)
        req = {"ack": "CONNECT_CHATGPT", "account_ref": "owner"}
        with (patch("agentforge.ops_control.require_active"),
              patch.object(chatgpt_auth, "sign_in", return_value={"email": "private", "token": "secret"}) as login,
              patch.object(chatgpt_auth, "models", return_value=[{"slug": "model", "display_name": "Model", "token": "secret"}]) as models,
              patch.object(chatgpt_auth, "sign_out", return_value={"remote_revocation": "CONFIRMED"}) as logout):
            with self.assertRaises(PermissionError):
                api.handle(server, "/api/model-hub/chatgpt", req, None)
            with self.assertRaises(PermissionError):
                api.handle(SimpleNamespace(allow_external_actions=False), "/api/model-hub/chatgpt", req, {})
            login.assert_not_called()
            result = api.handle(server, "/api/model-hub/chatgpt", req, {})
            self.assertEqual(result, {"account_ref": "owner", "connected": True})
            result = api.handle(server, "/api/model-hub/chatgpt", {**req, "ack": "LIST_CHATGPT_MODELS"}, {})
            self.assertEqual(result["models"], [{"slug": "model", "display_name": "Model"}])
            result = api.handle(server, "/api/model-hub/chatgpt", {**req, "ack": "DISCONNECT_CHATGPT"}, {})
            self.assertFalse(result["connected"])
            login.assert_called_once_with("owner")
            models.assert_called_once_with("owner")
            logout.assert_called_once_with("owner")
