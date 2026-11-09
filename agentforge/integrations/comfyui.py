"""Fixed-loopback ComfyUI HTTP JSON transport for the Owner motion pilot.

This is transport only: never decides approvals, GPUs, artifact acceptance or
retry policy. It never follows redirects or uses HTTP proxy environment vars.
"""
import http.client
import json
import re

HOST = "127.0.0.1"
DEFAULT_PORT = 8188
MAX_RESPONSE_BYTES = 131_072
ROUTE = re.compile(r"/(?:system_stats|prompt|history/[0-9a-f-]{36})\Z")


class ComfyUITransportError(ValueError):
    """Invalid local route or bounded JSON response."""


def request_json(path: str, *, body=None, timeout=6, port=DEFAULT_PORT,
                 max_response_bytes=MAX_RESPONSE_BYTES):
    """One request to a fixed loopback host; caller owns one-shot semantics."""
    if not isinstance(path, str) or not ROUTE.fullmatch(path):
        raise ComfyUITransportError("Unknown local ComfyUI route")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ComfyUITransportError("Invalid local ComfyUI port")
    if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES:
        raise ComfyUITransportError("Invalid ComfyUI response limit")
    if type(timeout) not in (int, float) or not 0 < timeout <= 30:
        raise ComfyUITransportError("Invalid ComfyUI timeout")
    payload = None if body is None else json.dumps(
        body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    conn = http.client.HTTPConnection(HOST, port, timeout=timeout)
    try:
        conn.request("POST" if payload is not None else "GET", path, body=payload,
                     headers={"Content-Type": "application/json",
                              "Accept": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise RuntimeError("Local ComfyUI returned non-success status")
        data = response.read(max_response_bytes + 1)
    finally:
        conn.close()
    if len(data) > max_response_bytes:
        raise ComfyUITransportError("ComfyUI response exceeds safe limit")
    try:
        return json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise ComfyUITransportError("ComfyUI returned invalid JSON") from exc
