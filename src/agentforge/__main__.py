import json
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "qwen3:8b"


def main():
    print("=== AgentForge v0.1.0 ===")

    with urllib.request.urlopen(
        f"{OLLAMA_URL}/api/tags", timeout=10
    ) as response:
        data = json.load(response)

    installed = [
        item["name"]
        for item in data.get("models", [])
    ]

    print("Ollama: CONNECTED")
    print("Available models:", installed)

    if MODEL not in installed:
        raise RuntimeError(f"Model not found: {MODEL}")

    payload = {
        "model": MODEL,
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Reply with only this text: "
                    "AgentForge is online."
                )
            }
        ]
    }

    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
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
        raise RuntimeError("Empty AI response")

    print("Model response:", answer)
    print("AgentForge: READY")


if __name__ == "__main__":
    main()
