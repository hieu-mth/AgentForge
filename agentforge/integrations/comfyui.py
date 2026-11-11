"""Fixed-loopback ComfyUI HTTP JSON transport for the Owner motion pilot.

This is transport only: never decides approvals, GPUs, artifact acceptance or
retry policy. It never follows redirects or uses HTTP proxy environment vars.
"""
import http.client
import json
import re
from urllib.parse import parse_qs, urlsplit

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


IMAGE_NAME = re.compile(r"af_[a-f0-9]{32}_[a-zA-Z0-9_.-]{1,80}\.png\Z")
IMAGE_HISTORY = re.compile(r"/history/[0-9a-f-]{36}\Z")
MAX_IMAGE_RESPONSE_BYTES = 6 * 1024 * 1024


def validate_image_route(path, *, has_body=False):
    """Explicit read-only ComfyUI image routes and one POST dispatch route."""
    if not isinstance(path, str) or len(path) > 300:
        raise ComfyUITransportError("Invalid local image route")
    if has_body:
        if path != "/prompt":
            raise ComfyUITransportError("Invalid image POST route")
        return
    if path in ("/models/checkpoints",) or IMAGE_HISTORY.fullmatch(path):
        return
    parsed = urlsplit(path)
    if parsed.path != "/view" or parsed.scheme or parsed.netloc or parsed.fragment:
        raise ComfyUITransportError("Invalid local image route")
    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True,
                         max_num_fields=3)
    except ValueError as exc:
        raise ComfyUITransportError("Invalid local image query") from exc
    if (set(query) != {"filename", "subfolder", "type"}
            or any(len(values) != 1 for values in query.values())
            or query["subfolder"] != [""]
            or query["type"] != ["output"]
            or not IMAGE_NAME.fullmatch(query["filename"][0])):
        raise ComfyUITransportError("Invalid local image query")


def request_image_bytes(path, *, body=None, timeout=5, port=DEFAULT_PORT,
                        max_response_bytes=262144):
    """Fixed-loopback, no-proxy/no-redirect binary transport for Image Studio.

    Caller owns explicit GPU consent and one-shot dispatch state. Never
    interpret provider HTTP redirect as a fetchable destination.
    """
    validate_image_route(path, has_body=body is not None)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ComfyUITransportError("Invalid local ComfyUI port")
    if (type(timeout) not in (int, float) or not 0 < timeout <= 30
            or type(max_response_bytes) is not int
            or not 1 <= max_response_bytes <= MAX_IMAGE_RESPONSE_BYTES):
        raise ComfyUITransportError("Invalid local ComfyUI resource budget")
    payload = None if body is None else json.dumps(
        body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if payload is not None and len(payload) > 160_000:
        raise ComfyUITransportError("ComfyUI image graph exceeds safe size limit")
    conn = http.client.HTTPConnection(HOST, port, timeout=timeout)
    try:
        conn.request("POST" if payload is not None else "GET", path,
                     body=payload,
                     headers={"Accept": "application/octet-stream" if path.startswith("/view?")
                              else "application/json",
                              "Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise RuntimeError("Local ComfyUI returned non-success status")
        raw = response.read(max_response_bytes + 1)
    finally:
        conn.close()
    if len(raw) > max_response_bytes:
        raise ComfyUITransportError("ComfyUI image response exceeds safe size limit")
    return raw
