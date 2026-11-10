"""Fail closed if Owner secrets, model weights or binary outputs are tracked.

This is a lightweight *filename and high-confidence token* CI backstop.
It is NOT a substitute for dedicated secret scanning, SCA or Git history
inspection. It runs no downloads, models or user-artifact reads outside Git
tracked files. Only paths (not content/tokens) are printed on failure.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANNED_DIRECTORIES = {".venv", "data", "workspace", "node_modules", "models",
                      "__pycache__", ".pytest_cache"}
BANNED_EXTENSIONS = {
    ".safetensors", ".ckpt", ".onnx", ".pth", ".pt",
    ".p12", ".pfx", ".pem", ".key",
    ".sqlite3", ".db", ".mp4", ".mov", ".wav", ".mp3", ".zip",
}
CREDENTIAL_NAMES = re.compile(
    r"(?:client_secret[^/]*\.json|.*oauth.*client.*\.json|"
    r"credentials\.json|token\.json|service-account[^/]*\.json)\Z",
    re.IGNORECASE,
)
TEXT_EXTENSIONS = {
    ".py", ".toml", ".json", ".js", ".jsx", ".mjs", ".ts", ".tsx",
    ".md", ".yml", ".yaml", ".ps1", ".txt", ".html", ".css", ".log",
}
SIGNATURES = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp_|gho_|github_pat_|sk-ant-|sk-proj-)[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{30,}"),
]


def forbidden_path(path):
    """Filename-only guard. All rules are relative to the Git checkout."""
    if not isinstance(path, str) or not path:
        return True
    name = path.replace("\\", "/")
    parts = name.split("/")
    if any(part.lower() in BANNED_DIRECTORIES for part in parts[:-1]):
        return True
    basename = parts[-1].lower()
    if basename == ".env.example":
        return False
    if basename == ".env" or basename.startswith(".env."):
        return True
    if CREDENTIAL_NAMES.fullmatch(basename):
        return True
    return Path(basename).suffix.lower() in BANNED_EXTENSIONS


def has_token(content):
    if not isinstance(content, str):
        return False
    return any(pattern.search(content) is not None for pattern in SIGNATURES)


def inspect(root=ROOT):
    root = Path(root)
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=True, timeout=20,
    )
    paths = [raw.decode("utf-8", "surrogateescape")
             for raw in result.stdout.split(b"\x00") if raw]
    problems = []
    for name in paths:
        if forbidden_path(name):
            problems.append((name, "tracked_owner_artifact_or_credentials"))
            continue
        path = root / name
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if not path.is_file() or path.is_symlink():
            problems.append((name, "tracked_text_missing_or_linked"))
            continue
        if path.stat().st_size > 1_500_000:
            # Avoid silently exempting unexpectedly giant text from inspection.
            problems.append((name, "tracked_text_too_large_for_guard"))
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            problems.append((name, "tracked_text_unreadable"))
            continue
        if has_token(content):
            problems.append((name, "high_confidence_secret_signature"))
    return {"tracked_files": len(paths), "problems": problems,
            "status": "PASS" if not problems else "BLOCKED"}


def main():
    result = inspect()
    for name, reason in result["problems"]:
        print(f"BLOCKED: {name}: {reason}")
    print(f"Tracked source hygiene: {result['status']}, "
          f"{result['tracked_files']} files checked")
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
