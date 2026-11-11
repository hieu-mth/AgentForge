"""Bounded, read-only local Ollama preflight for the Product Builder.

GET /api/tags ONLY. This is not a generation request, billing check or
guarantee that a long HTML model response will fit the builder contract.
No request URL, token, exception text or model output is returned.
"""
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

MAX_TAGS_BYTES = 262144


def check(*, resolve=None, opener=None):
    from agentforge.model import resolve_runtime
    try:
        runtime = (resolve or resolve_runtime)(
            "product_builder", "Read-only local model readiness preflight")
    except (ValueError, OSError, KeyError):
        return {"status": "CONFIG_ERROR", "generation_invoked": False}
    provider = runtime.get("provider")
    if provider != "ollama":
        return {"status": "NON_LOCAL_PROVIDER", "provider": provider,
                "ready": False, "generation_invoked": False}
    base = runtime.get("base_url", "")
    if not isinstance(base, str):
        return {"status": "INVALID_ENDPOINT", "ready": False, "generation_invoked": False}
    parsed = urlsplit(base)
    try:
        valid = (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")
                 and parsed.port is not None and parsed.path in ("", "/")
                 and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        return {"status": "INVALID_ENDPOINT", "ready": False, "generation_invoked": False}
    expected = runtime.get("model")
    if not isinstance(expected, str) or not expected:
        return {"status": "CONFIG_ERROR", "ready": False, "generation_invoked": False}
    request = urllib.request.Request(base.rstrip("/") + "/api/tags",
                                     headers={"Accept": "application/json"},
                                     method="GET")
    # Metadata probe is local-only: environment proxies and redirects must
    # not carry the request to any remote destination.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    safe_open = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()).open if opener is None else opener
    try:
        with safe_open(request, timeout=3) as resp:
            if resp.status != 200:
                return {"status": "HTTP_ERROR", "ready": False, "generation_invoked": False}
            raw = resp.read(MAX_TAGS_BYTES + 1)
        if len(raw) > MAX_TAGS_BYTES:
            return {"status": "INVALID_RESPONSE", "ready": False, "generation_invoked": False}
        payload = json.loads(raw)
        entries = payload.get("models")
        if not isinstance(entries, list):
            raise ValueError("Invalid model list")
        exists = any(isinstance(item, dict) and item.get("name") == expected
                     for item in entries)
        return {"status": "READY" if exists else "MODEL_NOT_INSTALLED",
                "model": expected, "ready": exists, "generation_invoked": False}
    except (TimeoutError, urllib.error.URLError, OSError):
        return {"status": "UNAVAILABLE", "ready": False, "generation_invoked": False}
    except (ValueError, TypeError, UnicodeError):
        return {"status": "INVALID_RESPONSE", "ready": False, "generation_invoked": False}
