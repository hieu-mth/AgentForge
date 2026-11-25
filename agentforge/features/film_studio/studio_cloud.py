"""Explicit HTTPS text requests for OpenAI Chat Completions and Anthropic Messages.

No discovery, fallback, redirect, tool execution or automatic retry. Never expose
provider bodies or credentials in exceptions or job receipts.
"""
import http.client
import json
import os
import re
from urllib.parse import quote, urlsplit

from agentforge.ai import cloud_credentials

PROVIDERS = frozenset({"openai", "anthropic"})
MAX_RESPONSE_BYTES = 512 * 1024


class CloudRequestError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__("Cloud AI: " + code)


def _connection(profile):
    # Import lazily to avoid a Model Hub / adapter dependency cycle.
    from agentforge.ai.model_hub import _cloud_url
    endpoint = profile.get("base_url") or os.environ.get(profile.get("base_url_env", ""), "")
    key = (cloud_credentials.unprotect_api_key(profile["api_key_protected"])
           if "api_key_protected" in profile else os.environ.get(profile.get("api_key_env", ""), ""))
    if not isinstance(key, str) or not re.fullmatch(r"[!-~]{1,4096}", key):
        raise CloudRequestError("AUTH_REQUIRED")
    try:
        parsed = urlsplit(_cloud_url(endpoint))
    except ValueError:
        raise CloudRequestError("INVALID_ENDPOINT") from None
    # An endpoint is the API base, e.g. https://provider.example/v1.
    base = parsed.path.rstrip("/") or "/v1"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if profile["provider"] == "anthropic":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    else:
        headers["Authorization"] = "Bearer " + key
    return parsed, base, headers


def _request(profile, method, route, payload=None):
    parsed, base, headers = _connection(profile)
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=120)
    try:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if body is not None and len(body) > 128 * 1024:
            raise CloudRequestError("REQUEST_TOO_LARGE")
        conn.request(method, base + route, body=body, headers=headers)
        response = conn.getresponse()
        if not 200 <= response.status < 300:
            code = {401: "AUTH_REQUIRED", 403: "ACCESS_DENIED", 404: "MODEL_OR_ENDPOINT_NOT_FOUND",
                    429: "RATE_OR_QUOTA_LIMIT", 402: "PAYMENT_REQUIRED"}.get(response.status, "HTTP_" + str(response.status))
            raise CloudRequestError(code)
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise CloudRequestError("RESPONSE_TOO_LARGE")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise CloudRequestError("INVALID_RESPONSE")
        return result
    except TimeoutError:
        raise CloudRequestError("TIMEOUT") from None
    except (OSError, http.client.HTTPException):
        raise CloudRequestError("UNAVAILABLE") from None
    except (UnicodeError, json.JSONDecodeError):
        raise CloudRequestError("INVALID_RESPONSE") from None
    finally:
        conn.close()


def readiness(profile):
    try:
        result = _request(profile, "GET", "/models/" + quote(profile["model"], safe=""))
        return "READY" if result.get("id") == profile["model"] else "INVALID_RESPONSE"
    except CloudRequestError as exc:
        return exc.code
    except ValueError:
        return "AUTH_REQUIRED"


def infer_structured(profile, instructions, data, schema, *, cpu_only=False, extended_plan=False, max_output_tokens=None):
    # Local placement flags deliberately have no effect on cloud inference.
    system = instructions + "\nReturn ONLY a JSON object matching this schema, no markdown:\n" + json.dumps(schema, ensure_ascii=False)
    user = json.dumps(data, ensure_ascii=False)
    limit = max_output_tokens if max_output_tokens is not None else (5200 if extended_plan else 2600)
    if profile["provider"] == "anthropic":
        result = _request(profile, "POST", "/messages", {
            "model": profile["model"], "max_tokens": limit, "system": system,
            "messages": [{"role": "user", "content": user}]})
        try:
            if result["stop_reason"] != "end_turn":
                raise CloudRequestError("INCOMPLETE_RESPONSE")
            content = "".join(block["text"] for block in result["content"] if block.get("type") == "text")
        except (KeyError, TypeError, AttributeError):
            raise CloudRequestError("INVALID_RESPONSE") from None
    else:
        result = _request(profile, "POST", "/chat/completions", {
            "model": profile["model"], "max_completion_tokens": limit,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        try:
            choice = result["choices"][0]
            if choice["finish_reason"] != "stop":
                raise CloudRequestError("INCOMPLETE_RESPONSE")
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise CloudRequestError("INVALID_RESPONSE") from None
    try:
        value = json.loads(content, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError):
        raise CloudRequestError("INVALID_STRUCTURED_RESPONSE") from None
    if not isinstance(value, dict) or not set(schema.get("required", ())) <= value.keys():
        raise CloudRequestError("INVALID_STRUCTURED_RESPONSE")
    if schema.get("additionalProperties") is False and not value.keys() <= schema.get("properties", {}).keys():
        raise CloudRequestError("INVALID_STRUCTURED_RESPONSE")
    return value


def probe(profile):
    value = infer_structured(profile, "Return the JSON object {\"ready\":true}.",
                             {}, {"type": "object", "required": ["ready"],
                                  "properties": {"ready": {"type": "boolean"}}}, max_output_tokens=64)
    if value.keys() != {"ready"} or value["ready"] is not True:
        raise CloudRequestError("INVALID_STRUCTURED_RESPONSE")
    return {"status": "PASS_RUNTIME", "inference_verified": True}
