import json
import os
import urllib.request

from agentforge.worker_registry import load_worker


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
    if worker_id is None:
        return {
            "model": os.getenv(
                "AGENTFORGE_MODEL", "qwen3:8b"
            ),
            "base_url": os.getenv(
                "AGENTFORGE_OLLAMA_URL",
                "http://127.0.0.1:11434"
            ),
            "system_prompt": default_system,
        }

    profile = load_worker(worker_id)
    selected = profile["model"]

    if selected["provider"] != "ollama":
        raise NotImplementedError(
            "This model provider is configured "
            "but its execution adapter is not implemented."
        )

    return {
        "model": selected["model"],
        "base_url": selected["base_url"],
        "system_prompt": (
            default_system
            + "\n\nWORKER INSTRUCTIONS:\n"
            + profile["instructions"]
        ),
    }


def _chat(prompt, *, worker_id=None, schema=None):
    default_system = (
        DEFAULT_JSON_SYSTEM
        if schema is not None
        else DEFAULT_TEXT_SYSTEM
    )

    runtime = resolve_runtime(
        worker_id,
        default_system
    )

    payload = {
        "model": runtime["model"],
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "system",
                "content": runtime["system_prompt"]
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    if schema is not None:
        payload["format"] = schema
        payload["options"] = {
            "temperature": 0.2
        }

    url = (
        runtime["base_url"].rstrip("/")
        + "/api/chat"
    )

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(
        request, timeout=180
    ) as response:
        raw = json.load(response)

    answer = raw["message"]["content"]

    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError(
            "Ollama returned an empty answer"
        )

    return answer.strip()


def generate(prompt: str, *, worker_id=None) -> str:
    return _chat(
        prompt,
        worker_id=worker_id
    )


def generate_json(
    prompt: str,
    schema: dict,
    *,
    worker_id=None,
) -> dict:
    answer = _chat(
        prompt,
        worker_id=worker_id,
        schema=schema
    )

    result = json.loads(answer)

    if not isinstance(result, dict):
        raise RuntimeError(
            "Model did not return a JSON object"
        )

    return result
