import hashlib
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path, PureWindowsPath

from agentforge.paths import REPOSITORY_ROOT, ensure_local_root

ROOT = REPOSITORY_ROOT
WORKSPACE = (ROOT / "workspace").resolve()
MAX_BYTES = 16_384


def safe_path(path: str) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Path must be a non-empty string")

    given = Path(path)

    windows_path = PureWindowsPath(path)
    if (given.is_absolute() or windows_path.anchor or ".." in windows_path.parts
            or ":" in path or any(p.endswith((".", " ")) or
                                   re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])",
                                                p.split(".")[0])
                                   for p in windows_path.parts)):
        raise PermissionError("Unsafe workspace path")

    # Windows resolve expands 8.3 names (for example RUNNER~1). Normalize
    # both operands only after checking the original ancestry for links.
    target = ensure_local_root(WORKSPACE / given).resolve()
    root = WORKSPACE.resolve()

    if target == root or not target.is_relative_to(root):
        raise PermissionError("Access outside workspace denied")

    return target


def _has_anchored_open():
    return os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW")


@contextmanager
def _workspace_parent(target, *, create=False):
    """Keep the checked directory chain anchored while opening a leaf."""
    root = WORKSPACE.resolve()
    parts = target.relative_to(root).parts
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        parent = os.open(root, flags)
        stack.callback(os.close, parent)
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part, dir_fd=parent)
                except FileExistsError:
                    pass
            parent = os.open(part, flags, dir_fd=parent)
            stack.callback(os.close, parent)
        yield parent, parts[-1]


def _read_at(parent, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(fd, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise FileNotFoundError("Regular workspace file required")
        return source.read(limit)


def read_file(path: str) -> str:
    target = safe_path(path)
    if _has_anchored_open():
        with _workspace_parent(target) as (parent, name):
            data = _read_at(parent, name, MAX_BYTES + 1)
    else:
        if not target.is_file():
            raise FileNotFoundError("Regular workspace file required")
        with target.open("rb") as source:
            data = source.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("File exceeds size limit")
    return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_file(path: str, content: str) -> dict:
    if not isinstance(content, str):
        raise ValueError("Content must be text")

    if len(content.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Content exceeds size limit")

    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        with target.open("x", encoding="utf-8") as file:
            file.write(content)

        return {"status": "created", "path": path}

    except FileExistsError:
        existing = read_file(path)

        if existing != content:
            raise RuntimeError(
                "File exists with different content"
            )

        return {
            "status": "already_exists_same_content",
            "path": path
        }


REPORT_PATH = re.compile(r"(?:[a-zA-Z0-9_-]{1,48}/){1,4}[a-zA-Z0-9_-]{1,48}\.md\Z")


def validate_report(path, content):
    if not isinstance(path, str) or len(path) > 150 or not REPORT_PATH.fullmatch(path):
        raise ValueError("Choose a relative Markdown file in a workspace subfolder")
    if not isinstance(content, str) or not content.strip() or len(content.encode("utf-8")) > 6000:
        raise ValueError("Markdown content must be nonempty and at most 6000 bytes")
    safe_path(path)


def _write_report_at(path, target, raw):
    with _workspace_parent(target, create=True) as (parent, name):
        temporary = ".agentforge-" + secrets.token_hex(16) + ".tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
            except FileExistsError:
                pass
            # Reopen through the current namespace before emitting a receipt.
            with _workspace_parent(safe_path(path)) as (verified_parent, leaf):
                return _read_at(verified_parent, leaf, len(raw) + 1)
        finally:
            os.unlink(temporary, dir_fd=parent)


def _write_report_portable(path, target, raw):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".agentforge-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        try:
            os.link(temporary, safe_path(path))
        except FileExistsError:
            pass
        target = safe_path(path)
        if not target.is_file():
            raise ValueError("Regular Markdown file required")
        with target.open("rb") as source:
            return source.read(len(raw) + 1)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_verified_report(path, content):
    """Publish a complete file without overwriting, then verify exact bytes."""
    validate_report(path, content)
    target = safe_path(path)
    raw = content.encode("utf-8")
    if _has_anchored_open() and {os.mkdir, os.link, os.unlink} <= os.supports_dir_fd:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        verified = _write_report_at(path, target, raw)
    else:
        verified = _write_report_portable(path, target, raw)
    if verified != raw:
        raise FileExistsError("Existing file has different content")
    return {"status": "VERIFIED", "report_path": "workspace/" + path,
            "sha256": hashlib.sha256(verified).hexdigest(), "size_bytes": len(verified)}


def validate_terminal_recipe(recipe, directory):
    if recipe != "python-version":
        raise PermissionError("Unknown terminal recipe")
    if not isinstance(directory, str) or not re.fullmatch(
            r"(?:[a-zA-Z0-9_-]{1,48}/){0,3}[a-zA-Z0-9_-]{1,48}", directory):
        raise ValueError("Choose a relative workspace directory")
    if not safe_path(directory).is_dir():
        raise FileNotFoundError("Workspace directory must exist")


def run_terminal_recipe(recipe, directory):
    validate_terminal_recipe(recipe, directory)
    # Absolute interpreter, fixed arguments, clean environment, no shell or child scripts.
    env = {key: os.environ[key] for key in ("SystemRoot",) if key in os.environ}
    try:
        proc = subprocess.run([sys.executable, "-I", "-S", "--version"],
                              cwd=safe_path(directory), env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, check=False, timeout=5)
    except subprocess.TimeoutExpired as exc:
        return {"status": "TIMEOUT", "recipe": recipe, "exit_code": -1,
                "stdout": (exc.stdout or b"")[:2048].decode("utf-8", errors="replace"),
                "stderr": (exc.stderr or b"")[:2048].decode("utf-8", errors="replace")}
    return {"status": "EXECUTED" if proc.returncode == 0 else "FAIL",
            "recipe": recipe, "exit_code": proc.returncode,
            "stdout": proc.stdout[:2048].decode("utf-8", errors="replace"),
            "stderr": proc.stderr[:2048].decode("utf-8", errors="replace")}



TOOLS = {
    "read_file": read_file,
    "write_file": write_file,
}


def execute_tool(name: str, arguments: dict):
    if name not in TOOLS:
        raise PermissionError(f"Tool not authorized: {name}")

    if not isinstance(arguments, dict):
        raise ValueError("Arguments must be a dictionary")

    return TOOLS[name](**arguments)
