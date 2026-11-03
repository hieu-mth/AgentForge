import json
import os
import urllib.request


def generate(prompt: str) -> str:
    base_url = os.getenv(
        "AGENTFORGE_OLLAMA_URL",
        "http://127.0.0.1:11434"
    ).rstrip("/")

    model = os.getenv("AGENTFORGE_MODEL", "qwen3:8b")

    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an AI Company research worker. "
                    "Be accurate. Do not fabricate evidence. "
                    "State when information is missing."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(
        request, timeout=180
    ) as response:
        result = json.load(response)

    answer = result["message"]["content"].strip()

    if not answer:
        raise RuntimeError("Ollama returned an empty answer")

    return answer
