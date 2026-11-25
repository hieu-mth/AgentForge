"""Explicit ElevenLabs-compatible sound and instrumental music generation."""
import http.client
import json
import math

from agentforge.features.film_studio import studio_cloud

MAX_AUDIO_BYTES = 8 * 1024 * 1024
ROUTES = {"sfx": "film.sound", "ambience": "film.sound", "music": "film.music"}


def supports(profile):
    return bool(profile and profile.get("provider") == "elevenlabs")


def generate(profile, kind, text, seconds):
    if (not supports(profile) or kind not in ROUTES or not isinstance(text, str)
            or not 1 <= len(text.strip()) <= 180 or type(seconds) not in (int, float)
            or not math.isfinite(seconds) or not 0 < seconds <= 60):
        raise ValueError("Invalid generated audio cue")
    if kind == "music":
        route = "/music"
        payload = {"model_id": profile["model"], "prompt": text,
                   "music_length_ms": max(3000, round(seconds*1000)), "force_instrumental": True}
    else:
        if seconds > 30:
            raise ValueError("Sound generation exceeds provider duration limit")
        route = "/sound-generation"
        payload = {"model_id": profile["model"], "text": text,
                   "duration_seconds": max(.5, seconds), "loop": False}
    parsed, base, headers = studio_cloud._connection(profile)
    headers["xi-api-key"] = headers.pop("Authorization").removeprefix("Bearer ")
    headers["Accept"] = "audio/mpeg"
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=120)
    try:
        conn.request("POST", base + route + "?output_format=mp3_44100_128",
                     body=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers)
        response = conn.getresponse()
        if not 200 <= response.status < 300:
            raise studio_cloud.CloudRequestError("HTTP_" + str(response.status))
        raw = response.read(MAX_AUDIO_BYTES+1)
        if (not 128 <= len(raw) <= MAX_AUDIO_BYTES
                or not (raw.startswith(b"ID3") or raw[0] == 255 and raw[1] & 224 == 224)):
            raise studio_cloud.CloudRequestError("INVALID_GENERATED_AUDIO")
        return raw
    except (OSError, http.client.HTTPException):
        raise studio_cloud.CloudRequestError("AUDIO_GENERATION_UNAVAILABLE") from None
    finally:
        conn.close()
