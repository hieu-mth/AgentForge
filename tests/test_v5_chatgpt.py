import io
import json
import pytest

from agentforge.ai import chatgpt_auth
from agentforge.features.film_studio import studio_chatgpt
from agentforge.features.film_studio.studio_cloud import CloudRequestError


def event(value):
    return b"data: " + json.dumps(value).encode() + b"\n\n"


def test_completed_stream_and_failure():
    delta = event({"type": "response.output_text.delta", "delta": '{"ready":true}'})
    done = event({"type": "response.completed", "response": {"status": "completed"}})
    assert studio_chatgpt.collect(io.BytesIO(delta + done)) == '{"ready":true}'
    with pytest.raises(CloudRequestError, match="INCOMPLETE_RESPONSE"):
        studio_chatgpt.collect(io.BytesIO(delta))
    failure = event({"type": "response.failed", "response": {"error": {
        "code": "subscription_sharing_usage_limit_exceeded"}}})
    with pytest.raises(CloudRequestError, match="RATE_OR_QUOTA_LIMIT"):
        studio_chatgpt.collect(io.BytesIO(delta + failure))


def test_oauth_state_and_client_binding():
    valid = {"state": ["state"], "client_id": ["oaiapp_test"], "code": ["code"]}
    assert chatgpt_auth._callback(valid, "state", None) == ("oaiapp_test", "code")
    for query, state, client in [(valid, "wrong", None), (valid, "state", "oaiapp_other"),
                                 ({**valid, "code": ["a", "b"]}, "state", None)]:
        with pytest.raises(chatgpt_auth.AuthError):
            chatgpt_auth._callback(query, state, client)


def test_explicit_plan_scope_required():
    data = {"scope": "openid", "access_token": "abc", "refresh_token": "def",
            "token_type": "Bearer", "expires_in": 3600}
    with pytest.raises(chatgpt_auth.AuthError):
        chatgpt_auth._credentials(data)
    data["scope"] += " " + chatgpt_auth.PLAN_SCOPE
    assert chatgpt_auth._credentials(data)["access_token"] == "abc"


def test_model_and_stream_payload(monkeypatch):
    from agentforge.ai import model_hub, orchestrator_policy
    p = {"id": "director", "provider": "chatgpt", "model": "chosen-model",
         "enabled": True, "account_ref": "owner"}
    assert model_hub.validate_profile(p) == p
    assert orchestrator_policy.compatible("text", p)
    assert orchestrator_policy.compatible("vision", p)
    assert not orchestrator_policy.local_adapter("text", p)
    with pytest.raises(ValueError):
        model_hub.validate_profile({**p, "base_url": "https://evil.example"})
    monkeypatch.setattr(studio_chatgpt, "request", lambda *_: '{"ready":true}')
    assert studio_chatgpt.probe(p)["inference_verified"]
