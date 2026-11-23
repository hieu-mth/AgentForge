"""Local structured text inference for Studio."""
import http.client
import json

from agentforge.features.film_studio import draft_resources
from agentforge.ops import runtime_certification as runtime


def infer_structured(profile, instructions, data, schema, *, cpu_only=False, extended_plan=False):
    host, port = runtime._local_endpoint(profile["base_url"])
    if not runtime._installed_local_model(host, port, profile["model"]):
        raise ValueError("Configured Ollama model is unavailable: " + profile["id"])
    payload = {"model": profile["model"], "stream": False, "think": False,
               "keep_alive": 0, "format": schema,
               "options": {"temperature": 0.2, "num_predict": 1600, "num_ctx": 4096},
               "messages": [{"role": "system", "content": instructions},
                            {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]}
    if cpu_only:
        payload["options"].update(num_gpu=0, num_predict=2600)
    if extended_plan:
        payload["options"].update(num_ctx=8192, num_predict=5200)
    timeout = 300 if cpu_only else 150
    try:
        message = runtime._http_json(host, port, "/api/chat", timeout=timeout, max_request_bytes=16384, payload=payload)
    except TimeoutError:
        raise ValueError(f"Ollama không phản hồi trong {timeout} giây khi phân tích nội dung. "
                         "Kiểm tra Ollama hoặc chọn model điều phối nhẹ hơn trước khi tiếp tục.") from None
    except runtime.LocalProviderHTTPError as exc:
        # Ollama's transport does not distinguish OOM from other server-side failures.
        if exc.status == 500:
            raise draft_resources.ResourceWait("OLLAMA_RESOURCE_OR_SERVER_ERROR") from None
        raise ValueError(f"Ollama rejected the request (HTTP {exc.status}): {profile['id']}") from None
    except (OSError, http.client.HTTPException):
        raise ValueError("Mất kết nối với Ollama khi phân tích nội dung. Kiểm tra dịch vụ Ollama rồi tiếp tục.") from None
    if message.get("done") is not True or message.get("done_reason") == "length":
        raise ValueError("Ollama did not complete the structured response")
    return json.loads(message["message"]["content"])
