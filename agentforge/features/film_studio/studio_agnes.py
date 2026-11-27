"""Agnes Flash transport. No credentials in URLs, logs, or downloaded assets."""
import base64
import http.client
import io
import ipaddress
import json
import os
import re
import socket
import ssl
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from agentforge.ai import cloud_credentials
from agentforge.features.media import mp4, render
from agentforge.features.film_studio.studio_contracts import ProviderRequestError
from agentforge.paths import ensure_local_root

HOST = "apihub.agnes-ai.com"
BASE = "https://" + HOST + "/v1"
IMAGE_MODEL = "agnes-image-2.5-flash"
VIDEO_MODELS = {"agnes-video-2.5-flash"}
PROVIDER = "agnes"
NATIVE_AUDIO = False


def supports_video(profile):
    return profile.get("provider", PROVIDER) == PROVIDER and profile.get("model") in VIDEO_MODELS
# Studio currently caps its shared cloud output contract at 10 seconds.
DURATIONS = tuple(range(4, 11))
MAX_JSON = 12 * 1024 * 1024


def validate_endpoint(endpoint):
    if endpoint.rstrip("/") != BASE:
        raise ValueError("Agnes endpoint must be the official HTTPS endpoint.")


def credential(profile):
    endpoint = profile.get("base_url") or os.environ.get(profile.get("base_url_env", ""), "")
    validate_endpoint(endpoint)
    value = (cloud_credentials.unprotect_api_key(profile["api_key_protected"])
             if "api_key_protected" in profile else os.environ.get(profile.get("api_key_env", ""), ""))
    if not re.fullmatch(r"[!-~]{1,4096}", value):
        raise ValueError("Agnes API key is not configured.")
    return value


key = credential


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", value):
        raise ValueError("Invalid Agnes provider ID.")
    return value


class AgnesHTTPError(ProviderRequestError):
    """Sanitized classification: never persist provider body, prompts or credentials."""

    def __init__(self, status, code=None, retry_after=None):
        self.status = status
        self.code = code if code in {"video_queue_full", "rate_limit_exceeded", "too_many_requests"} else None
        retryable = (status == 503 and self.code == "video_queue_full") or status == 429
        rejected = retryable or status in {400, 401, 402, 403, 404, 413, 415, 422}
        label = {400: "Invalid request", 401: "Invalid API key", 402: "Payment or quota required",
                 403: "Access denied", 404: "Endpoint or model not found", 413: "Request too large",
                 415: "Unsupported media type", 422: "Invalid request parameters",
                 429: "Rate limited"}.get(status, "Video queue full" if self.code == "video_queue_full" else "Provider error")
        super().__init__(f"Agnes HTTP {status}: {label}" + (f" ({self.code})" if self.code else ""),
                         rejected=rejected, retryable=retryable, retry_after=retry_after)


def _http_error(response):
    # Read a bounded response to distinguish a definitive queue rejection
    # from arbitrary 503/5xx. Never echo untrusted message text.
    code = None
    try:
        data = response.read(64 * 1024 + 1)
        if len(data) <= 64 * 1024:
            result = json.loads(data)
            if isinstance(result, dict):
                error = result.get("error")
                candidate = result.get("code") or (error.get("code") if isinstance(error, dict) else None)
                if isinstance(candidate, str):
                    code = candidate
                if result.get("video_id") or result.get("id") or result.get("data") not in (None, {}):
                    # Unexpected acceptance evidence must not authorize a retry.
                    return ValueError(f"Agnes HTTP {response.status}: response contains possible job evidence; outcome unknown.")
    except (ValueError, TypeError, OSError, http.client.HTTPException):
        pass
    raw_retry = response.getheader("Retry-After")
    retry_after = int(raw_retry) if isinstance(raw_retry, str) and re.fullmatch(r"[0-9]{1,9}", raw_retry) else None
    return AgnesHTTPError(response.status, code, retry_after)


def _request(method, path, token, body=None):
    conn = http.client.HTTPSConnection(HOST, timeout=120)
    try:
        conn.request(method, path, None if body is None else json.dumps(body).encode("utf-8"),
                     {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status not in ({200, 201, 202} if method == "POST" else {200}):
            raise _http_error(response)
        data = response.read(MAX_JSON + 1)
        if len(data) > MAX_JSON:
            raise ValueError("Agnes response exceeds limit.")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("Invalid Agnes response.")
        return result
    except TimeoutError:
        raise ProviderRequestError("Agnes request timed out; outcome unknown.") from None
    except (OSError, http.client.HTTPException, UnicodeError):
        raise ProviderRequestError("Agnes transport failed; outcome unknown.") from None
    finally:
        conn.close()


def image_payload(prompt, ratio):
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 5000 or ratio not in {"16:9", "9:16", "1:1"}:
        raise ValueError("Invalid Agnes image request.")
    return {"model": IMAGE_MODEL, "prompt": prompt, "size": "1K", "ratio": ratio,
            "extra_body": {"response_format": "b64_json"}}


def image_bytes(body, token, max_bytes):
    from PIL import Image
    result = _request("POST", "/v1/images/generations", token, body)
    item = result["data"][0]
    encoded = item.get("b64_json")
    if encoded:
        if not isinstance(encoded, str) or len(encoded) > (max_bytes * 4 // 3 + 8):
            raise ValueError("Agnes image exceeds limit.")
        raw = base64.b64decode(encoded, validate=True)
    else:
        sink = io.BytesIO()
        _download_to(item["url"], sink, max_bytes)
        raw = sink.getvalue()
    with Image.open(io.BytesIO(raw)) as image:
        if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > 12_000_000:
            raise ValueError("Unsupported Agnes image.")
        image.load()
        output = io.BytesIO()
        image.convert("RGB").save(output, format="PNG")
        data = output.getvalue()
    if not 0 < len(data) <= max_bytes:
        raise ValueError("Normalized image exceeds limit.")
    return data


def payload(model, prompt, duration, *, image=None, audio=False):
    if model not in VIDEO_MODELS or type(duration) is not int or duration not in DURATIONS:
        raise ValueError("Unsupported Agnes video model or duration.")
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 5000:
        raise ValueError("Invalid Agnes video prompt.")
    body = {"model": model, "prompt": prompt, "seconds": str(duration),
            "size": "720P", "aspect_ratio": "16:9", "n": 1, "mode": "text"}
    if image is not None:
        from PIL import Image
        if not isinstance(image, bytes) or not 1 <= len(image) <= 6 * 1024 * 1024:
            raise ValueError("Invalid Agnes reference image.")
        with Image.open(io.BytesIO(image)) as frame:
            if frame.format not in {"PNG", "JPEG"} or frame.width * frame.height > 12_000_000:
                raise ValueError("Unsupported reference image.")
            fmt = frame.format.lower()
            frame.verify()
        body.update(mode="keyframe", first_frame="data:image/" + fmt + ";base64," + base64.b64encode(image).decode("ascii"))
    return body


def submit(body, token):
    response = _request("POST", "/v1/videos", token, body)
    try:
        return _id(response.get("video_id"))
    except ValueError:
        raise ProviderRequestError("Agnes accepted HTTP response without a valid video ID; outcome unknown.") from None


def submit_video(body, key, endpoint):
    return submit(body, key)


def poll(row, token):
    remote = _id(row["provider_id"])
    result = _request("GET", "/agnesapi?" + urlencode({"video_id": remote, "model_name": row["model"]}), token)
    if ("video_id" in result and result["video_id"] != remote) or result.get("status") not in {
            "pending", "processing", "queued", "running", "completed", "failed"}:
        raise ValueError("Unrecognized Agnes job status.")
    if "model" in result and result["model"] != row["model"]:
        raise ValueError("Agnes job model mismatch.")
    if result["status"] == "completed":
        metadata = result.get("metadata")
        url = result.get("url") or (metadata.get("url") if isinstance(metadata, dict) else None)
        if not isinstance(url, str) or not url:
            raise ValueError("Missing Agnes output URL.")
        result = {**result, "url": url}
    return result


poll_video = poll


def download_video(result, target, seconds):
    download_normalized(result["url"], target, seconds)


def _public_addresses(host):
    addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast
                            for ip in addresses):
        raise ValueError("Agnes download host must resolve exclusively to public addresses.")
    return sorted(addresses)


def _download_to(url, stream, max_bytes):
    if not isinstance(url, str):
        raise ValueError("Invalid Agnes download URL.")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in {None, 443} or not parsed.path or parsed.fragment
            or any(ord(c) < 33 for c in url)):
        raise ValueError("Unsafe Agnes download URL.")
    # Pin the validated address, but verify TLS against the original host.
    # No authorization header and no redirects to arbitrary destinations.
    address = _public_addresses(parsed.hostname)[0]
    conn = http.client.HTTPSConnection(parsed.hostname, timeout=30)
    try:
        with socket.create_connection((address, 443), timeout=30) as sock:
            conn.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
            conn.request("GET", parsed.path + ("?" + parsed.query if parsed.query else ""))
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError("Agnes download unavailable.")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Agnes output exceeds size limit.")
                stream.write(chunk)
    except (OSError, http.client.HTTPException):
        raise ValueError("Agnes download failed.") from None
    finally:
        conn.close()


def _download(url, target):
    with target.open("xb") as stream:
        _download_to(url, stream, mp4.MAX_VIDEO_BYTES)


def download_normalized(url, target, seconds):
    raw = ensure_local_root(target.with_name(uuid4().hex + ".raw.mp4"))
    try:
        _download(url, raw)
        # Normalize provider FPS / dimensions; never synthesize missing duration.
        # Native audio is not advertised until verified against the real provider.
        render._run_process([render._ffmpeg(), "-nostdin", "-n", "-v", "error", "-xerror",
            "-protocol_whitelist", "file,pipe", "-f", "mov", "-i", str(raw), "-map", "0:v:0", "-an",
            "-vf", "fps=24,scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1",
            "-frames:v", str(seconds * 24), "-c:v", "libx264", "-threads", "2",
            "-pix_fmt", "yuv420p", str(target)], cwd=target.parent, timeout=150)
    finally:
        raw.unlink(missing_ok=True)
