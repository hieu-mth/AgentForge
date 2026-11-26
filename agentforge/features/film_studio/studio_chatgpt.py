"""ChatGPT plan inference via documented public Responses API (no fallback or retries)."""
import http.client
import json
import sqlite3
import time

from agentforge.ai import chatgpt_auth
from agentforge.features.film_studio.studio_cloud import CloudRequestError

MAX_BYTES = 2 * 1024 * 1024


def collect(stream):
    text = []
    size = 0
    event_lines = []
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        raw = stream.readline(262145)
        size += len(raw)
        if size > MAX_BYTES or len(raw) > 262144:
            raise CloudRequestError("RESPONSE_TOO_LARGE")
        if not raw:
            break
        if raw.startswith(b"data:"):
            event_lines.append(raw[5:].strip())
        if raw.strip() or not event_lines:
            continue
        try:
            event = json.loads(b"\n".join(event_lines))
            event_lines.clear()
            kind = event.get("type")
            if kind == "response.output_text.delta":
                if not isinstance(event["delta"], str):
                    raise ValueError()
                text.append(event["delta"])
            elif kind == "response.completed":
                if event.get("response", {}).get("status") != "completed" or not text:
                    raise CloudRequestError("INCOMPLETE_RESPONSE")
                return "".join(text)
            elif kind in {"response.failed", "response.incomplete", "error"}:
                code = (event.get("response", {}).get("error") or {}).get("code") or event.get("code")
                raise CloudRequestError("RATE_OR_QUOTA_LIMIT" if code in {
                    "subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable"
                } else "INCOMPLETE_RESPONSE")
        except CloudRequestError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError):
            raise CloudRequestError("INVALID_RESPONSE") from None
    raise CloudRequestError("INCOMPLETE_RESPONSE")


def request(profile, instructions, content):
    try:
        token = chatgpt_auth.access_token(profile["account_ref"])
    except (ValueError, OSError, sqlite3.Error):
        raise CloudRequestError("AUTH_REQUIRED") from None
    body = json.dumps({"model": profile["model"], "instructions": instructions,
                       "input": [{"role": "user", "content": content}],
                       "store": False, "stream": True}, ensure_ascii=False, allow_nan=False).encode()
    if len(body) > 128 * 1024:
        raise CloudRequestError("REQUEST_TOO_LARGE")
    conn = http.client.HTTPSConnection("api.openai.com", timeout=120)
    try:
        conn.request("POST", "/v1/responses", body=body,
                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                              "Accept": "text/event-stream"})
        response = conn.getresponse()
        if response.status != 200:
            raise CloudRequestError({401: "AUTH_REQUIRED", 403: "ACCESS_DENIED", 429: "RATE_OR_QUOTA_LIMIT",
                                     402: "PAYMENT_REQUIRED"}.get(response.status, "HTTP_" + str(response.status)))
        return collect(response)
    except (OSError, http.client.HTTPException):
        raise CloudRequestError("UNAVAILABLE") from None
    finally:
        conn.close()


def infer_structured(profile, instructions, data, schema, *, cpu_only=False, extended_plan=False, max_output_tokens=None):
    content = request(profile, instructions + "\nReturn only JSON matching: " + json.dumps(schema),
                      json.dumps(data, ensure_ascii=False))
    try:
        value = json.loads(content, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError):
        raise CloudRequestError("INVALID_STRUCTURED_RESPONSE") from None
    if (not isinstance(value, dict) or not set(schema.get("required", ())) <= value.keys()
            or (schema.get("additionalProperties") is False and not value.keys() <= schema.get("properties", {}).keys())):
        raise CloudRequestError("INVALID_STRUCTURED_RESPONSE")
    return value


def readiness(profile):
    try:
        return "READY" if profile["model"] in {m["slug"] for m in chatgpt_auth.models(profile["account_ref"])} else "MODEL_OR_ENDPOINT_NOT_FOUND"
    except (ValueError, OSError, sqlite3.Error):
        return "AUTH_REQUIRED"


def probe(profile):
    value = infer_structured(profile, 'Return exactly {"ready":true}.', {},
                             {"type": "object", "required": ["ready"], "additionalProperties": False,
                              "properties": {"ready": {"type": "boolean"}}})
    if value != {"ready": True} or value["ready"] is not True:
        raise CloudRequestError("INVALID_STRUCTURED_RESPONSE")
    return {"status": "PASS_RUNTIME", "inference_verified": True}
