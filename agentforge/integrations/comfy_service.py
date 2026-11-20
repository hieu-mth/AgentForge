"""Owner-approved lifecycle for one Windows ComfyUI Portable installation."""
import hashlib
import http.client
import json
import logging
import os
import socket
import sqlite3
import subprocess
import threading
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_resources
from agentforge.integrations import comfyui
from agentforge.paths import COMPANY_DATA_DIR, ensure_local_root

LOCK = threading.RLock()
_CHILD = None
_PORT = None
_STATE = "STOPPED"
_ERROR = None
_LOG = logging.getLogger(__name__)
START_TIMEOUT = 120
LOG_DIR = COMPANY_DATA_DIR / "runtime_logs"
RUNTIME_DIR = COMPANY_DATA_DIR / "comfy_runtime"


class StartupPressure(ValueError):
    """The existing resource gate refused to load ComfyUI."""


def _db(write=False):
    path = ensure_local_root(model_hub.DB_PATH)
    if not write and not path.is_file():
        return None
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path if write else path.as_uri() + "?mode=ro", uri=not write, timeout=5)


def _settings():
    conn = _db()
    if conn is None:
        return None
    with closing(conn):
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='comfy_service'").fetchone():
            return None
        row = conn.execute("SELECT body FROM comfy_service WHERE id=1").fetchone()
        return json.loads(row[0]) if row else None


def _target(profile_id):
    for profile in model_hub.catalog()["profiles"]:
        if profile["id"] == profile_id and profile["provider"] == "comfyui" and profile["enabled"]:
            parts = urlsplit(profile["base_url"])
            if parts.hostname not in {"localhost", "127.0.0.1"}:
                break
            return parts.port, profile["base_url"]
    raise ValueError("Choose an enabled IPv4 loopback ComfyUI profile")


def _launcher(value):
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError("Invalid ComfyUI Portable folder")
    root = Path(value)
    # Reject UNC paths, as well as alternate streams and relative path segments.
    if not root.is_absolute() or not root.drive or root.drive.startswith("\\") or any(
            p in {".", ".."} or ":" in p for p in root.parts[1:]):
        raise ValueError("Choose an absolute local Windows Portable folder")
    root = ensure_local_root(root)
    executable = ensure_local_root(root / "python_embeded" / "python.exe")
    script = ensure_local_root(root / "ComfyUI" / "main.py")
    try:
        with executable.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("Invalid Portable Python executable")
            stream.seek(0)
            executable_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        with script.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024 or b"comfy.cli_args" not in data:
            raise ValueError("Invalid ComfyUI entry point")
    except OSError:
        raise ValueError("Portable Python or ComfyUI entry point could not be read") from None
    return root, executable, script, [executable_hash, hashlib.sha256(data).hexdigest()]


def configure(profile_id, install_root):
    global _CHILD, _PORT, _STATE, _ERROR
    port, _ = _target(profile_id)
    root, _, _, fingerprints = _launcher(install_root)
    with LOCK:
        if _owned():
            raise PermissionError("Stop the managed ComfyUI before changing its launcher")
        with closing(_db(True)) as conn, conn:
            conn.execute("CREATE TABLE IF NOT EXISTS comfy_service (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
            conn.execute("INSERT OR REPLACE INTO comfy_service VALUES (1,?)",
                         (json.dumps({"profile_id": profile_id, "port": port,
                                      "install_root": str(root), "fingerprints": fingerprints}),))
        _CHILD, _PORT, _STATE, _ERROR = None, None, "STOPPED", None
    return status()


def _owned():
    return _CHILD is not None and _CHILD.poll() is None


def _probe(port):
    try:
        data = comfyui.request_json("/system_stats", port=port, timeout=2)
        if isinstance(data, dict) and isinstance(data.get("devices"), list) and isinstance(data.get("system"), dict):
            return data
        raise ValueError("Invalid ComfyUI system stats")
    except (OSError, RuntimeError, ValueError, http.client.HTTPException):
        return None


def _occupied(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            return True
    except ConnectionRefusedError:
        return False
    except OSError:
        return True


def _queue_busy(port):
    try:
        data = json.loads(comfyui.request_image_bytes("/queue", port=port, timeout=3))
        return data.get("queue_running") != [] or data.get("queue_pending") != []
    except (OSError, RuntimeError, ValueError, AttributeError, http.client.HTTPException):
        return True


def status():
    config = _settings()
    if not config:
        catalog = model_hub.catalog()
        selected = next((r["model_ref"] for r in catalog["routes"] if r["id"] == "image.generate"), None)
        profiles = [p for p in catalog["profiles"] if p["enabled"] and p["provider"] == "comfyui"]
        profile = next((p for p in profiles if p["id"] == selected), profiles[0] if len(profiles) == 1 else None)
        if not profile:
            return {"state": "UNCONFIGURED", "managed": False, "configured": False}
        try:
            port, _ = _target(profile["id"])
        except ValueError:
            return {"state": "UNCONFIGURED", "managed": False, "configured": False}
        config = {"port": port, "profile_id": profile["id"], "install_root": None}
    port = config["port"]
    endpoint = f"http://127.0.0.1:{port}"
    child = _CHILD
    managed = _PORT == port and child is not None and child.poll() is None
    state = _STATE
    data = None if state == "STARTING" and managed else _probe(port)
    if data:
        state = "RUNNING"
    elif state == "STARTING" and managed:
        state = "STARTING"
    elif managed or _occupied(port) or _CHILD is not None and _PORT == port:
        state = "ERROR"
    else:
        state = "ERROR" if state == "ERROR" else "STOPPED"
    from agentforge.features.film_studio import draft_pipeline
    production_busy = bool(draft_pipeline.ACTIVE)
    return {"state": state, "configured": config["install_root"] is not None,
            "managed": managed, "pid": child.pid if managed else None,
            "endpoint": endpoint, "profile_id": config["profile_id"], "install_root": config["install_root"],
            "busy": production_busy or bool(data and _queue_busy(port)),
            "devices": [{k: device.get(k) for k in ("name", "type", "vram_total", "vram_free")}
                        for device in data["devices"][:8] if isinstance(device, dict)] if data else [],
            "error": (_ERROR or "ComfyUI process exited or endpoint is unavailable") if state == "ERROR" else None}


def ensure_running(port, *, required=False):
    """Called from existing GPU dispatch paths after their inference admission."""
    global _CHILD, _PORT, _STATE, _ERROR
    with LOCK:
        config = _settings()
        if not config or config["port"] != port:
            if required:
                raise ValueError("Configure the launcher for the active ComfyUI endpoint")
            return False
        configured_port, _ = _target(config["profile_id"])
        if configured_port != port:
            raise ValueError("ComfyUI profile endpoint changed; save the launcher again")
        if _probe(port):
            return True
        if _owned() or _occupied(port):
            raise ValueError("ComfyUI endpoint is occupied or unresponsive; startup was skipped")
        if os.name != "nt":
            raise ValueError("Managed ComfyUI Portable requires Windows")
        from agentforge import ops_control
        ops_control.require_active()
        pressure = draft_resources.pressure(draft_resources.snapshot(), "image")
        if pressure:
            raise StartupPressure(pressure)
        root, executable, script, fingerprints = _launcher(config["install_root"])
        if fingerprints != config["fingerprints"]:
            raise ValueError("Launcher files changed; review and register them again")
        folder = ensure_local_root(LOG_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        log = ensure_local_root(folder / "comfyui.log")
        if log.is_file() and log.stat().st_size > 8 * 1024 * 1024:
            log.replace(ensure_local_root(folder / "comfyui.previous.log"))
        directories = []
        for kind in ("user", "output", "temp"):
            directory = ensure_local_root(RUNTIME_DIR / kind)
            directory.mkdir(parents=True, exist_ok=True)
            directories.extend((f"--{kind}-directory", str(directory)))
        _STATE, _ERROR = "STARTING", None
        try:
            with log.open("ab") as stream:
                _CHILD = subprocess.Popen(
                    [str(executable), "-s", str(script), "--windows-standalone-build",
                     "--listen", "127.0.0.1", "--port", str(port), "--cache-none",
                     "--disable-auto-launch", *directories],
                    cwd=root, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                    shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
            _PORT = port
        except OSError:
            _STATE, _ERROR = "ERROR", "Could not start registered ComfyUI executable"
            _LOG.exception("ComfyUI launch failed")
            raise ValueError(_ERROR) from None
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if not _owned():
                break
            if _probe(port) and _owned():
                _STATE = "RUNNING"
                return True
            time.sleep(1)
        # Keep ownership so an Owner can inspect or stop the slow startup explicitly.
        _STATE, _ERROR = "ERROR", "ComfyUI exited or timed out; see data/company/runtime_logs/comfyui.log"
        raise ValueError(_ERROR)


def control(action):
    global _CHILD, _PORT, _STATE, _ERROR
    with LOCK:
        config = _settings()
        if not config:
            raise ValueError("Register the ComfyUI Portable launcher first")
        port = config["port"]
        if action in {"stop", "restart"}:
            from agentforge.features.film_studio import draft_pipeline
            if draft_pipeline.ACTIVE:
                raise PermissionError("A draft production is active")
            if _owned():
                probe = _probe(port)
                if _PORT != port or (probe and _queue_busy(port)):
                    raise PermissionError("ComfyUI has a job or its queue cannot be verified")
                if not probe and _occupied(port):
                    raise PermissionError("Cannot verify ComfyUI queue before stopping")
                _CHILD.terminate()
                try:
                    _CHILD.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    _STATE, _ERROR = "ERROR", "Managed ComfyUI did not stop within 8 seconds"
                    raise ValueError(_ERROR) from None
                _CHILD, _PORT, _STATE, _ERROR = None, None, "STOPPED", None
            elif _occupied(port):
                raise PermissionError("AgentForge cannot stop a ComfyUI it did not launch")
            else:
                _CHILD, _PORT, _STATE, _ERROR = None, None, "STOPPED", None
        if action in {"start", "restart"}:
            ensure_running(port, required=True)
        return status()
