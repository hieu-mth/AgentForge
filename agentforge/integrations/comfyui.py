"""Fixed-loopback ComfyUI HTTP JSON transport for the Owner motion pilot.

This is transport only: never decides approvals, GPUs, artifact acceptance or
retry policy. It never follows redirects or uses HTTP proxy environment vars.
"""
import http.client
import json
import re
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

HOST = "127.0.0.1"
DEFAULT_PORT = 8188
MAX_RESPONSE_BYTES = 131_072
MODEL_CATEGORIES = ("checkpoints", "diffusion_models", "loras", "vae",
                    "text_encoders", "clip")
MODEL_ROUTES = frozenset("/models/" + category for category in MODEL_CATEGORIES)
ROUTE = re.compile(r"/(?:system_stats|prompt|history/[0-9a-f-]{36})\Z")


class ComfyUITransportError(ValueError):
    """Invalid local route or bounded JSON response."""


class ComfyHTTPError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__("Local ComfyUI returned non-success status")


def failure_status(exc):
    if isinstance(exc, ComfyHTTPError):
        return ("AUTH_REQUIRED" if exc.status in {401, 403} else
                "COMFYUI_TIMEOUT" if exc.status in {408, 504} else "COMFYUI_HTTP_ERROR")
    if isinstance(exc, TimeoutError):
        return "COMFYUI_TIMEOUT"
    if isinstance(exc, (OSError, http.client.HTTPException)):
        return "COMFYUI_UNAVAILABLE"
    return "COMFYUI_INVALID_RESPONSE"


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
            raise ComfyHTTPError(response.status)
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
        if path not in {"/prompt", "/free"}:
            raise ComfyUITransportError("Invalid image POST route")
        return
    if (path in MODEL_ROUTES or path in {"/system_stats", "/queue"}
            or IMAGE_HISTORY.fullmatch(path)
            or re.fullmatch(r"/object_info/(?:UnetLoaderGGUF|DualCLIPLoaderGGUF|VAELoader|"
                            r"CheckpointLoaderSimple|CLIPLoader|CLIPTextEncode|LoadImage|"
                            r"SaveImage|EmptyLatentImage|EmptySD3LatentImage|KSampler|"
                            r"LTXVImgToVideo|LTXVConditioning|KSamplerSelect|ManualSigmas|"
                            r"SamplerCustom|VAEDecode|CreateVideo|SaveVideo)", path)):
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
                        max_response_bytes=262144, sink=None):
    """Fixed-loopback, no-proxy/no-redirect binary transport for Image Studio.

    Caller owns explicit GPU consent and one-shot dispatch state. Never
    interpret provider HTTP redirect as a fetchable destination.
    """
    validate_image_route(path, has_body=body is not None)
    if sink is not None and not path.startswith("/view?"):
        raise ComfyUITransportError("Only an image response can be streamed")
    if path == "/free" and (not isinstance(body, dict) or body.keys() != {"unload_models", "free_memory"}
                            or any(value is not True for value in body.values())):
        raise ComfyUITransportError("Invalid local memory release request")
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
            raise ComfyHTTPError(response.status)
        if sink is not None:
            total = 0
            while chunk := response.read(min(64 * 1024, max_response_bytes - total + 1)):
                total += len(chunk)
                if total > max_response_bytes:
                    raise ComfyUITransportError("ComfyUI image response exceeds safe size limit")
                sink.write(chunk)
            return b""
        raw = response.read(max_response_bytes + 1)
    finally:
        conn.close()
    if len(raw) > max_response_bytes:
        raise ComfyUITransportError("ComfyUI image response exceeds safe size limit")
    return raw


MAX_MOTION_INPUT_BYTES = 8 * 1024 * 1024


def upload_motion_source(port, job_id, data):
    """One bounded loopback upload with a generated basename and no overwrite."""
    if (type(port) is not int or not 1 <= port <= 65535
            or not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id)
            or not isinstance(data, bytes) or not 0 < len(data) <= MAX_MOTION_INPUT_BYTES):
        raise ValueError("Invalid motion input upload")
    name = "af_motion_source_" + job_id + ".png"
    boundary = uuid4().hex
    prefix = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
              "Content-Type: image/png\r\n\r\n").encode("ascii")
    body = prefix + data + f"\r\n--{boundary}--\r\n".encode("ascii")
    with_connection = http.client.HTTPConnection(HOST, port, timeout=10)
    try:
        with_connection.request("POST", "/upload/image", body=body, headers={
            "Content-Type": "multipart/form-data; boundary=" + boundary,
        })
        response = with_connection.getresponse()
        if response.status != 200:
            raise ValueError("ComfyUI did not accept the motion input")
        raw = response.read(4097)
        if len(raw) > 4096:
            raise ValueError("Invalid ComfyUI upload response")
        try:
            saved = json.loads(raw)
        except (ValueError, RecursionError):
            raise ValueError("Invalid ComfyUI upload response") from None
        if not isinstance(saved, dict) or ("asset" in saved and not isinstance(saved["asset"], dict)):
            raise ValueError("Invalid ComfyUI upload response")
        # ComfyUI may include asset metadata. Only the upload identity binds the graph.
        if saved.get("name") != name or saved.get("subfolder") != "" or saved.get("type") != "input":
            raise ValueError("ComfyUI returned an unexpected input filename")
    finally:
        with_connection.close()
    return name
