"""Bounded explicit cloud speech transport. No automatic retry or model fallback."""
import http.client
import json

from agentforge.features.film_studio import studio_cloud

MAX_WAV_BYTES = 8 * 1024 * 1024


def supports(profile):
    return bool(profile and profile.get("provider") == "openai")


def registry_readiness(profile):
    return studio_cloud.readiness(profile)


def synthesize(profile, text, voice):
    if not supports(profile) or not isinstance(text, str) or not 1 <= len(text) <= 180:
        raise ValueError("Unsupported speech adapter or narration text")
    if not isinstance(voice, str) or not 1 <= len(voice) <= 100:
        raise ValueError("Cloud speech requires an explicit voice")
    parsed, base, headers = studio_cloud._connection(profile)
    headers["Accept"] = "audio/wav"
    payload = json.dumps({"model": profile["model"], "input": text, "voice": voice,
                          "response_format": "wav"}, ensure_ascii=False).encode("utf-8")
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=120)
    try:
        conn.request("POST", base + "/audio/speech", body=payload, headers=headers)
        response = conn.getresponse()
        if not 200 <= response.status < 300:
            raise studio_cloud.CloudRequestError("HTTP_" + str(response.status))
        raw = response.read(MAX_WAV_BYTES+1)
        if not 44 <= len(raw) <= MAX_WAV_BYTES or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
            raise studio_cloud.CloudRequestError("INVALID_AUDIO_RESPONSE")
        return raw
    except (OSError, http.client.HTTPException):
        raise studio_cloud.CloudRequestError("AUDIO_REQUEST_UNAVAILABLE") from None
    finally:
        conn.close()
