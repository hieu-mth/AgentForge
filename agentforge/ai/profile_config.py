"""Shared endpoint validation, independent of the model database."""
from urllib.parse import urlsplit

from agentforge.ai.orchestrator_policy import ModelConfigError


def local_url(value):
    """Reject SSRF endpoints, loopback aliases, userinfo and nested paths."""
    if not isinstance(value, str) or len(value) > 120:
        raise ModelConfigError("Invalid local provider URL")
    parsed = urlsplit(value)
    try:
        good = (parsed.scheme == "http" and
                parsed.hostname in {"127.0.0.1", "localhost", "::1"} and
                parsed.port is not None and 1 <= parsed.port <= 65535 and
                parsed.path in {"", "/"} and not parsed.username and
                not parsed.password and not parsed.query and not parsed.fragment)
    except ValueError:
        good = False
    if not good:
        raise ModelConfigError("Only a local loopback HTTP provider is allowed")
    return value.rstrip("/")


def cloud_url(value):
    if not isinstance(value, str) or len(value) > 512 or any(
            c.isspace() or ord(c) < 32 or c in "\\?#" for c in value):
        raise ModelConfigError("Nhập URL HTTPS hợp lệ cho endpoint Cloud")
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == "https" and parsed.hostname and
                 parsed.username is None and parsed.password is None and
                 (parsed.port is None or 1 <= parsed.port <= 65535))
    except ValueError:
        valid = False
    if not valid:
        raise ModelConfigError("Nhập URL HTTPS hợp lệ cho endpoint Cloud")
    return value.rstrip("/")
