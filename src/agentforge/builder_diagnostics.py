"""Safe, bounded diagnostics for local website builder and model availability.

Never expose exception text, tokens, prompt, model response or endpoint URL.
The Ollama probe only reads /api/tags from a configured LOOPBACK server.
No generation, no retries and no implicit model dispatch.
"""
import argparse
import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

# Typed errors are the only model/network information exposed via S1.
BUILDER_ERRORS = (
    ("MODEL_CONNECT_FAILED", "Không kết nối được Ollama; kiểm tra dịch vụ local."),
    ("MODEL_TIMEOUT", "Ollama quá thời gian phản hồi; kiểm tra tải máy/model."),
    ("MODEL_HTTP_ERROR", "Model endpoint trả về lỗi HTTP; kiểm tra cấu hình."),
    ("MODEL_INVALID_RESPONSE", "Model endpoint trả dữ liệu sai cấu trúc."),
    ("HTML_INCOMPLETE", "Model không trả HTML hoàn chỉnh; giảm độ dài brief."),
    ("HTML_TOO_LARGE", "HTML vượt giới hạn an toàn của Product Builder."),
    ("HTML_QUALITY_FAILED", "HTML bị Quality Gate từ chối; cần sửa bố cục/mã."),
    ("HTML_UNSAFE", "Builder từ chối nội dung hoặc liên kết không được phép."),
    ("PROJECT_EXISTS", "Đã có project với slug này; dùng slug mới."),
    ("MODEL_CONFIG_FAILED", "Cấu hình model chưa hợp lệ."),
    ("BUILDER_VALIDATION_FAILED", "Đầu ra Builder không khớp hợp đồng."),
)
DESCRIPTIONS = dict(BUILDER_ERRORS)


def classify(exc):
    """Return fixed error code + safe hint; never interpolate str(exc)."""
    if isinstance(exc, (urllib.error.URLError, ConnectionError, ConnectionRefusedError,
                        BrokenPipeError)):
        return "MODEL_CONNECT_FAILED"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "MODEL_TIMEOUT"
    if isinstance(exc, urllib.error.HTTPError):
        return "MODEL_HTTP_ERROR"
    if isinstance(exc, (json.JSONDecodeError, UnicodeError, KeyError, TypeError)):
        return "MODEL_INVALID_RESPONSE"
    if isinstance(exc, FileExistsError):
        return "PROJECT_EXISTS"
    from agentforge.model_registry import ModelConfigError
    if isinstance(exc, ModelConfigError):
        return "MODEL_CONFIG_FAILED"
    if isinstance(exc, ValueError):
        # Only compare allowlisted fixed string fragments; do not echo error.
        msg = str(exc)
        if any(x in msg for x in ("incomplete code fence", "HTML appears truncated",
                                   "complete HTML document", "Builder must return HTML")):
            return "HTML_INCOMPLETE"
        if any(x in msg for x in ("too large", "exceeds", "above size", "byte limit")):
            return "HTML_TOO_LARGE"
        if "Static quality gate FAIL" in msg:
            return "HTML_QUALITY_FAILED"
        if any(x in msg for x in ("Unexpected or duplicate", "Unexpected model",
                                   "suspicious", "Unsafe", "remote resource")):
            return "HTML_UNSAFE"
        return "BUILDER_VALIDATION_FAILED"
    return "BUILDER_EXECUTION_FAILED"


def safe_failure(exc):
    code = classify(exc)
    return code + ": " + DESCRIPTIONS.get(
        code, "Không thể hoàn thành lần chạy; không tự chạy lại model.")


def ollama_probe(*, worker_id="product_builder"):
    """Observe configured local provider without calling /api/chat."""
    from agentforge.model import resolve_runtime
    try:
        runtime = resolve_runtime(worker_id, "Local model readiness check")
    except (ValueError, KeyError, OSError) as exc:
        return {"status": "CONFIG_ERROR", "error_code": classify(exc),
                "generation_invoked": False}
    if runtime["provider"] != "ollama":
        return {"status": "NOT_LOCAL_OLLAMA", "provider": runtime["provider"],
                "generation_invoked": False}
    url = urlsplit(runtime["base_url"])
    # Host is strictly loopback, even if a config mistake points elsewhere.
    if (url.scheme != "http" or url.hostname not in ("localhost", "127.0.0.1", "::1")
            or url.username or url.password or url.query or url.fragment or url.path not in ("", "/")):
        return {"status": "UNSAFE_ENDPOINT", "error_code": "MODEL_CONFIG_FAILED",
                "generation_invoked": False}
    target = runtime["base_url"].rstrip("/") + "/api/tags"
    try:
        request = urllib.request.Request(target, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=3) as response:
            if response.status != 200:
                return {"status": "UNAVAILABLE", "error_code": "MODEL_HTTP_ERROR",
                        "generation_invoked": False}
            raw = response.read(262145)
        if len(raw) > 262144:
            return {"status": "INVALID_RESPONSE", "error_code": "MODEL_INVALID_RESPONSE",
                    "generation_invoked": False}
        payload = json.loads(raw)
        models = payload["models"]
        if not isinstance(models, list):
            raise ValueError("Invalid local model list")
        matched = any(isinstance(x, dict) and x.get("name") == runtime["model"]
                      for x in models)
        return {"status": "READY" if matched else "MODEL_NOT_INSTALLED",
                "provider": "ollama", "model": runtime["model"],
                "model_installed": matched, "generation_invoked": False}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError,
            KeyError, TypeError, UnicodeError) as exc:
        return {"status": "UNAVAILABLE", "error_code": classify(exc),
                "generation_invoked": False}


def main():
    parser = argparse.ArgumentParser(description="Read-only local Ollama readiness")
    parser.add_argument("command", choices=["check"])
    parser.parse_args()
    print(json.dumps(ollama_probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
