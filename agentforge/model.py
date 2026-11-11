"""Small Ollama / Anthropic-compatible runtime router for AgentForge."""

import json
import os
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from agentforge.model_registry import ROOT, ModelConfigError, load_models
from agentforge.ai import model_hub
from agentforge.worker_registry import load_worker

DOTENV_PATH = ROOT / ".env"
DEFAULT_MODEL_REF = "local_primary"

# Higher cap only for the product builder: a complete HTML document plus any
# gateway-internal reasoning needs more space than a short research answer.
# This is an upper bound, not a request to consume all tokens. No auto-retry.
BUILDER_CLOUD_TEXT_MAX_TOKENS = 8192
# A React app embedded as structured JSON takes substantially more output
# tokens than a short research answer. Still one Owner-approved call; no retry.
DEVELOPER_CLOUD_JSON_MAX_TOKENS = 8192
MAX_CONFIGURED_DEVELOPER_CLOUD_TOKENS = 16384


def _developer_cloud_max_tokens():
    """Owner-controlled response cap, never silently escalated or retried."""
    raw = os.getenv("AGENTFORGE_DEVELOPER_MAX_TOKENS", "").strip()
    if not raw:
        return DEVELOPER_CLOUD_JSON_MAX_TOKENS
    if not raw.isascii() or not raw.isdecimal():
        raise ModelConfigError("AGENTFORGE_DEVELOPER_MAX_TOKENS must be 8192-16384")
    budget = int(raw)
    if not DEVELOPER_CLOUD_JSON_MAX_TOKENS <= budget <= MAX_CONFIGURED_DEVELOPER_CLOUD_TOKENS:
        raise ModelConfigError("AGENTFORGE_DEVELOPER_MAX_TOKENS must be 8192-16384")
    return budget


# Ollama in non-streaming mode sends no answer until the whole React app is
# generated. Keep shorter requests on the original 180s socket timeout; give
# the explicitly approved Developer call room for larger structured output.
DEFAULT_MODEL_TIMEOUT_SECONDS = 180
DEFAULT_DEVELOPER_TIMEOUT_SECONDS = 600
MAX_DEVELOPER_TIMEOUT_SECONDS = 900
MAX_OLLAMA_DEVELOPER_STREAM_BYTES = 512_000
MAX_OLLAMA_DEVELOPER_STREAM_EVENTS = 30_000
# Raw network envelopes are separate from decoded generated text budgets.
MAX_MODEL_RESPONSE_BYTES = 1_000_000
MAX_OLLAMA_STREAM_LINE_BYTES = 64_000
MAX_OLLAMA_STREAM_WIRE_BYTES = 4_000_000


def _request_timeout(worker_id):
    if worker_id != "webapp_developer":
        return DEFAULT_MODEL_TIMEOUT_SECONDS
    raw = os.getenv("AGENTFORGE_DEVELOPER_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_DEVELOPER_TIMEOUT_SECONDS
    if not raw.isascii() or not raw.isdecimal():
        raise ModelConfigError(
            "AGENTFORGE_DEVELOPER_TIMEOUT_SECONDS must be 60-900")
    seconds = int(raw)
    if not 60 <= seconds <= MAX_DEVELOPER_TIMEOUT_SECONDS:
        raise ModelConfigError(
            "AGENTFORGE_DEVELOPER_TIMEOUT_SECONDS must be 60-900")
    return seconds

DEFAULT_TEXT_SYSTEM = (
    "You are an AI Company research worker. "
    "Be accurate. Do not fabricate evidence. "
    "State when information is missing."
)

DEFAULT_JSON_SYSTEM = (
    "You are AgentForge's research planner. "
    "Return valid structured JSON. "
    "Do not invent evidence."
)


def resolve_runtime(worker_id, default_system):
    # Process environment takes precedence over the local, gitignored .env.
    load_dotenv(DOTENV_PATH, override=False)
    from agentforge.ai.role_routing import ROLE_WORKERS, require_worker_model
    if worker_id in ROLE_WORKERS.values():
        # Cloud/model switching requires separate process-level Owner consent
        # and has no automatic fallback. This check makes V5 model routing
        # enforceable, not merely a static display.
        require_worker_model(worker_id)

    if worker_id is None:
        default_ref = DEFAULT_MODEL_REF
        system_prompt = default_system
    else:
        profile = load_worker(worker_id)
        default_ref = profile["model_ref"]
        system_prompt = (
            default_system
            + "\n\nWORKER INSTRUCTIONS:\n"
            + profile["instructions"]
        )

    routed_ref, routing_revision, owner_routed = model_hub.model_for_worker(
        worker_id, default_ref)
    # Explicit process environment selection preserves existing CLI behavior
    # and takes priority over Dashboard overrides. A saved cloud route never
    # grants cloud consent: the process and each actual task still must approve.
    env_ref = os.getenv("AGENTFORGE_MODEL_REF")
    model_ref = env_ref or routed_ref
    models = model_hub.effective_models()
    if model_ref not in models:
        raise ModelConfigError(f"Unknown model reference: {model_ref}")

    selected = models[model_ref]
    if not selected["enabled"]:
        raise ModelConfigError(f"Model is disabled: {model_ref}")

    provider = selected["provider"]
    if (owner_routed and not env_ref and provider != "ollama"
            and os.getenv("AGENTFORGE_CLOUD_MODEL_CONSENT") != "YES"):
        raise PermissionError("CLOUD_MODEL_CONSENT_REQUIRED")
    if provider == "ollama":
        base_url = selected["base_url"]
        token = None
    elif provider == "anthropic":
        base_url = os.getenv(selected["base_url_env"], "").strip()
        token = os.getenv(selected["api_key_env"], "").strip()
        if not base_url:
            raise ModelConfigError(
                f"Missing environment variable: {selected['base_url_env']}"
            )
        if not token:
            raise ModelConfigError(
                f"Missing environment variable: {selected['api_key_env']}"
            )
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ModelConfigError("Cloud endpoint must be an HTTPS base URL")
    else:
        raise NotImplementedError(f"No adapter for provider: {provider}")

    return {
        "provider": provider,
        "model_ref": model_ref,
        "model": selected["model"],
        "base_url": base_url,
        "api_key": token,
        "system_prompt": system_prompt,
        "routing_revision": routing_revision,
        "route_source": "process_env" if env_ref else (
            "owner" if owner_routed else "default"),
    }



def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Model invocation exceeded total deadline")
    return remaining


def _bound_socket(response, deadline):
    """Bound the next receive where urllib exposes a real HTTP socket.

    BytesIO/testing gateways intentionally lack a socket. This supplements
    monotonic checks; socket timeouts alone are per I/O, not a total budget.
    """
    _remaining(deadline)
    fp = getattr(response, "fp", None)
    sock = getattr(getattr(fp, "raw", None), "_sock", None)
    if sock is not None:
        sock.settimeout(_remaining(deadline))


def _read_json_envelope(response, deadline):
    chunks, size = [], 0
    while True:
        _bound_socket(response, deadline)
        remaining = MAX_MODEL_RESPONSE_BYTES + 1 - size
        if remaining <= 0:
            raise RuntimeError("Model response exceeds safe size limit")
        reader = getattr(response, "read1", None) or response.read
        block = reader(min(8192, remaining))
        _remaining(deadline)
        if not block:
            break
        size += len(block)
        if size > MAX_MODEL_RESPONSE_BYTES:
            raise RuntimeError("Model response exceeds safe size limit")
        chunks.append(block)
    try:
        return json.loads(b"".join(chunks))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("Model response returned invalid JSON") from exc


def _read_stream_event(response, deadline, max_bytes):
    _bound_socket(response, deadline)
    line = response.readline(max_bytes + 1)
    _remaining(deadline)
    if len(line) > max_bytes:
        raise RuntimeError("Ollama stream exceeds safe size limit")
    return line



def _ollama_chat(runtime, prompt, schema, *, worker_id=None):
    stream_developer = worker_id == "webapp_developer" and schema is not None
    payload = {
        "model": runtime["model"],
        "stream": stream_developer,
        "think": False,
        "messages": [
            {"role": "system", "content": runtime["system_prompt"]},
            {"role": "user", "content": prompt},
        ],
    }
    if schema is not None:
        payload["format"] = schema
        payload["options"] = {"temperature": 0.2}

    request = urllib.request.Request(
        runtime["base_url"].rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = _request_timeout(worker_id)
    deadline = time.monotonic() + timeout
    with urllib.request.urlopen(request, timeout=timeout) as response:
        _remaining(deadline)
        if stream_developer:
            parts = []
            received_bytes = 0
            wire_bytes = 0
            completed = False
            for event_count in range(1, MAX_OLLAMA_DEVELOPER_STREAM_EVENTS + 2):
                # Never iterate an unbounded line: readline(limit) caps bytes
                # *before* the event is allocated or JSON-decoded.
                if event_count > MAX_OLLAMA_DEVELOPER_STREAM_EVENTS:
                    raise RuntimeError("Ollama stream exceeds safe size limit")
                line = _read_stream_event(response, deadline,
                                          MAX_OLLAMA_STREAM_LINE_BYTES)
                if not line:
                    break
                wire_bytes += len(line)
                if wire_bytes > MAX_OLLAMA_STREAM_WIRE_BYTES:
                    raise RuntimeError("Ollama stream exceeds safe size limit")
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise RuntimeError("Ollama stream returned invalid JSON") from None
                if not isinstance(event, dict) or "error" in event:
                    raise RuntimeError("Ollama stream returned invalid event")
                message = event.get("message")
                if message is not None:
                    if (not isinstance(message, dict)
                            or not isinstance(message.get("content"), str)):
                        raise RuntimeError("Ollama stream returned invalid event")
                    chunk = message["content"]
                    received_bytes += len(chunk.encode("utf-8"))
                    if received_bytes > MAX_OLLAMA_DEVELOPER_STREAM_BYTES:
                        raise RuntimeError("Ollama stream exceeds safe size limit")
                    parts.append(chunk)
                elif event.get("done") is not True:
                    raise RuntimeError("Ollama stream returned invalid event")
                if event.get("done") is True:
                    completed = True
                    break
            if not completed:
                raise RuntimeError("Ollama stream ended before done")
            answer = "".join(parts)
        else:
            raw = _read_json_envelope(response, deadline)
            answer = raw["message"]["content"]
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Ollama returned an empty answer")
    return answer.strip()



class _RejectCloudRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward cloud credentials to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _cloud_open(request, *, timeout):
    # Keep normal proxy/HTTPS handling, but do not use the process-global
    # urlopen opener: it follows 30x responses and may forward Bearer tokens.
    # Building a per-call opener is safe for concurrent local API requests.
    opener = urllib.request.build_opener(_RejectCloudRedirect())
    return opener.open(request, timeout=timeout)


def _anthropic_chat(runtime, prompt, schema, *, worker_id=None):
    system_prompt = runtime["system_prompt"]
    if schema is not None:
        system_prompt += (
            "\n\nReturn ONLY one JSON object matching this JSON schema. "
            "No markdown fences or explanatory text.\nSCHEMA:\n"
            + json.dumps(schema, ensure_ascii=False)
        )

    max_tokens = (
        _developer_cloud_max_tokens()
        if schema is not None and worker_id == "webapp_developer"
        else 4096 if schema is not None
        else BUILDER_CLOUD_TEXT_MAX_TOKENS if worker_id == "product_builder"
        else 2048
    )
    payload = {
        "model": runtime["model"],
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        runtime["base_url"].rstrip("/") + "/messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "Authorization": "Bearer " + runtime["api_key"],
        },
        method="POST",
    )
    timeout = _request_timeout(worker_id)
    deadline = time.monotonic() + timeout
    with _cloud_open(request, timeout=timeout) as response:
        raw = _read_json_envelope(response, deadline)

    if not isinstance(raw, dict):
        raise RuntimeError("Gateway response must be a JSON object")
    blocks = raw.get("content")
    stop_reason = raw.get("stop_reason")
    usage = raw.get("usage")
    output_tokens = (
        usage.get("output_tokens")
        if isinstance(usage, dict) and type(usage.get("output_tokens")) is int
        else None
    )
    block_types = (
        sorted({
            item["type"] for item in blocks
            if isinstance(item, dict) and isinstance(item.get("type"), str)
        })[:8]
        if isinstance(blocks, list) else []
    )
    # Never log response text, the user's prompt, URL or the API key.
    diagnostic = (
        f"stop_reason={stop_reason!r}, block_types={block_types!r}, "
        f"output_tokens={output_tokens!r}, max_tokens={max_tokens}"
    )
    if stop_reason == "max_tokens":
        raise RuntimeError(
            "Gateway response stopped at max_tokens (" + diagnostic
            + "). Incomplete output rejected; no automatic retry."
        )
    if not isinstance(blocks, list):
        raise RuntimeError("Gateway response has no content blocks (" + diagnostic + ")")
    parts = [
        item["text"]
        for item in blocks
        if isinstance(item, dict)
        and item.get("type") == "text"
        and isinstance(item.get("text"), str)
    ]
    answer = "\n".join(parts).strip()
    if not answer:
        raise RuntimeError(
            "Gateway returned no text content (" + diagnostic
            + "). No automatic retry; no generated files saved."
        )
    return answer


def _chat(prompt, *, worker_id=None, schema=None):
    default_system = DEFAULT_JSON_SYSTEM if schema is not None else DEFAULT_TEXT_SYSTEM
    runtime = resolve_runtime(worker_id, default_system)
    if runtime["provider"] == "ollama":
        return _ollama_chat(runtime, prompt, schema, worker_id=worker_id)
    if runtime["provider"] == "anthropic":
        return _anthropic_chat(runtime, prompt, schema, worker_id=worker_id)
    raise NotImplementedError("Model adapter is not implemented")


def generate(prompt: str, *, worker_id=None) -> str:
    return _chat(prompt, worker_id=worker_id)


def generate_json(prompt: str, schema: dict, *, worker_id=None) -> dict:
    answer = _chat(prompt, worker_id=worker_id, schema=schema)
    result = json.loads(answer)
    if not isinstance(result, dict):
        raise RuntimeError("Model did not return a JSON object")
    return result
