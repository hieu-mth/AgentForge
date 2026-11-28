"""BigModel CogVideoX-Flash transport; no automatic submission retries."""
import base64
import http.client
import io
import json
import os
import re

from agentforge.ai import cloud_credentials
from agentforge.features.film_studio.cloud_media_assets import download_normalized
from agentforge.features.film_studio.studio_contracts import MotionOutput, ProviderRequestError

HOST = "open.bigmodel.cn"
PATH = "/api/paas/v4"
BASE = "https://" + HOST + PATH
MODEL = "cogvideox-flash"
PROVIDER = "bigmodel"
DURATIONS = (5,)
MAX_PROMPT_CHARS = 512
MAX_IMAGE = 5 * 1024 * 1024
MAX_RESPONSE = 1024 * 1024


def supports_video(profile):
    return profile.get("provider") == PROVIDER and profile.get("model") == MODEL


def input_modes(profile):
    return ("text-to-video", "image-to-video")


def output_profile(profile):
    # Conservative normalized Studio contract, not the provider's native FPS.
    return MotionOutput(24, DURATIONS[0] * 24, (1280, 720))


def billable_durations(profile):
    return DURATIONS


def native_audio(profile):
    return False


def validate_endpoint(endpoint):
    if endpoint.rstrip("/") != BASE:
        raise ValueError("BigModel endpoint must be the official HTTPS endpoint.")


def credential(profile):
    endpoint = profile.get("base_url") or os.environ.get(profile.get("base_url_env", ""), "")
    validate_endpoint(endpoint)
    value = (cloud_credentials.unprotect_api_key(profile["api_key_protected"])
             if "api_key_protected" in profile else os.environ.get(profile.get("api_key_env", ""), ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", value) or len(value) > 4096:
        raise ValueError("BigModel requires the complete API key, not the API Key ID.")
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", value):
        raise ValueError("Invalid BigModel provider job ID.")
    return value


def _request(method, path, token, body=None):
    conn = http.client.HTTPSConnection(HOST, timeout=120)
    try:
        conn.request(method, PATH + path, None if body is None else json.dumps(body).encode("utf-8"),
                     {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        response = conn.getresponse()
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ProviderRequestError("BigModel response exceeds limit; outcome unknown.")
        if response.status not in ({200, 201, 202} if method == "POST" else {200}):
            # Only a definitive error envelope with no acceptance evidence can
            # authorize a new explicit request. No automatic retry.
            try:
                error = json.loads(raw)
            except (ValueError, UnicodeError):
                error = None
            rejected = (response.status in {400, 401, 402, 403, 404, 413, 415, 422, 429}
                        and isinstance(error, dict) and set(error) == {"error"}
                        and isinstance(error["error"], dict))
            raise ProviderRequestError(f"BigModel HTTP {response.status}", rejected=rejected)
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ProviderRequestError("Invalid BigModel response; outcome unknown.")
        return result
    except (OSError, http.client.HTTPException, UnicodeError, json.JSONDecodeError):
        raise ProviderRequestError("BigModel transport failed; outcome unknown.") from None
    finally:
        conn.close()


def payload(model, prompt, duration, *, image=None, audio=False):
    if model != MODEL or type(duration) is not int or duration not in DURATIONS or audio:
        raise ValueError("Unsupported CogVideoX-Flash request.")
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= MAX_PROMPT_CHARS:
        raise ValueError("CogVideoX-Flash prompt must contain 1–512 characters.")
    body = {"model": model, "prompt": prompt}
    if image is not None:
        from PIL import Image
        if not isinstance(image, bytes) or not 1 <= len(image) <= MAX_IMAGE:
            raise ValueError("BigModel reference image must be at most 5 MiB.")
        with Image.open(io.BytesIO(image)) as frame:
            if frame.format not in {"PNG", "JPEG"} or frame.width * frame.height > 12_000_000:
                raise ValueError("Unsupported BigModel reference image.")
            frame.verify()
        body["image_url"] = base64.b64encode(image).decode("ascii")
    return body


def submit_video(body, key, endpoint):
    if endpoint not in {"text-to-video", "image-to-video"} or ("image_url" in body) != (endpoint == "image-to-video"):
        raise ValueError("BigModel request does not match the approved input mode.")
    result = _request("POST", "/videos/generations", key, body)
    if result.get("model") not in (None, MODEL) or result.get("task_status") not in {"PROCESSING", "SUCCESS", "FAIL"}:
        raise ProviderRequestError("Unrecognized BigModel submission; outcome unknown.")
    try:
        return _id(result.get("id"))
    except ValueError:
        raise ProviderRequestError("BigModel accepted response without a valid ID; outcome unknown.") from None


def poll_video(row, token):
    remote = _id(row["provider_id"])
    result = _request("GET", "/async-result/" + remote, token)
    if result.get("id") != remote or result.get("model") not in (None, row["model"]):
        raise ValueError("BigModel job identity mismatch.")
    state = result.get("task_status")
    if state == "PROCESSING":
        return {"status": "processing"}
    if state == "FAIL":
        return {"status": "failed"}
    if state != "SUCCESS":
        raise ValueError("Unrecognized BigModel job status.")
    items = result.get("video_result")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise ValueError("Invalid BigModel video result.")
    url = items[0].get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("Missing BigModel video URL.")
    return {"status": "completed", "url": url}


def download_video(result, target, seconds):
    download_normalized(result["url"], target, seconds)
