"""Small Ollama / Anthropic-compatible runtime router for AgentForge."""

import json
import os
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from agentforge.model_registry import ROOT, ModelConfigError, load_models
from agentforge.worker_registry import load_worker

DOTENV_PATH = ROOT / ".env"
DEFAULT_MODEL_REF = "local_primary"

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

    model_ref = os.getenv("AGENTFORGE_MODEL_REF") or default_ref
    models = load_models()
    if model_ref not in models:
        raise ModelConfigError(f"Unknown model reference: {model_ref}")

    selected = models[model_ref]
    if not selected["enabled"]:
        raise ModelConfigError(f"Model is disabled: {model_ref}")

    provider = selected["provider"]
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
    }


def _ollama_chat(runtime, prompt, schema):
    payload = {
        "model": runtime["model"],
        "stream": False,
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
    with urllib.request.urlopen(request, timeout=180) as response:
        raw = json.load(response)

    answer = raw["message"]["content"]
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Ollama returned an empty answer")
    return answer.strip()


def _anthropic_chat(runtime, prompt, schema):
    system_prompt = runtime["system_prompt"]
    if schema is not None:
        system_prompt += (
            "\n\nReturn ONLY one JSON object matching this JSON schema. "
            "No markdown fences or explanatory text.\nSCHEMA:\n"
            + json.dumps(schema, ensure_ascii=False)
        )

    payload = {
        "model": runtime["model"],
        "max_tokens": 4096 if schema is not None else 2048,
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
    with urllib.request.urlopen(request, timeout=180) as response:
        raw = json.load(response)

    blocks = raw.get("content") if isinstance(raw, dict) else None
    if not isinstance(blocks, list):
        raise RuntimeError("Gateway response has no content blocks")
    parts = [
        item["text"]
        for item in blocks
        if isinstance(item, dict)
        and item.get("type") == "text"
        and isinstance(item.get("text"), str)
    ]
    answer = "\n".join(parts).strip()
    if not answer:
        raise RuntimeError("Gateway returned no text content")
    return answer


def _chat(prompt, *, worker_id=None, schema=None):
    default_system = DEFAULT_JSON_SYSTEM if schema is not None else DEFAULT_TEXT_SYSTEM
    runtime = resolve_runtime(worker_id, default_system)
    if runtime["provider"] == "ollama":
        return _ollama_chat(runtime, prompt, schema)
    if runtime["provider"] == "anthropic":
        return _anthropic_chat(runtime, prompt, schema)
    raise NotImplementedError("Model adapter is not implemented")


def generate(prompt: str, *, worker_id=None) -> str:
    return _chat(prompt, worker_id=worker_id)


def generate_json(prompt: str, schema: dict, *, worker_id=None) -> dict:
    answer = _chat(prompt, worker_id=worker_id, schema=schema)
    result = json.loads(answer)
    if not isinstance(result, dict):
        raise RuntimeError("Model did not return a JSON object")
    return result
