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
IDLE_TIMEOUT = 60
_IDLE_INTERVAL = 2
_IDLE_SINCE = None
_IDLE_WAKE = threading.Event()
_IDLE_THREAD = None
LOG_DIR = COMPANY_DATA_DIR / "runtime_logs"
RUNTIME_DIR = COMPANY_DATA_DIR / "comfy_runtime"


class StartupError(ValueError):
    """ComfyUI could not become ready before a prompt was submitted."""


class StartupPressure(StartupError):
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
        require_idle_queue(port)
    except draft_resources.ResourceBlocked:
        return True
    return False


def validate_idle_queue(data):
    if not isinstance(data, dict) or any(not isinstance(data.get(key), list)
                                         for key in ("queue_running", "queue_pending")):
        raise draft_resources.ResourceBlocked("COMFYUI_QUEUE_UNAVAILABLE")
    if data["queue_running"] or data["queue_pending"]:
        raise draft_resources.ResourceBlocked("COMFYUI_QUEUE_BUSY")


def require_idle_queue(port, *, allow_offline=False):
    try:
        data = json.loads(comfyui.request_image_bytes("/queue", port=port, timeout=3))
    except ConnectionRefusedError:
        if allow_offline:
            return
        raise draft_resources.ResourceBlocked("COMFYUI_QUEUE_UNAVAILABLE") from None
    except (OSError, RuntimeError, ValueError, http.client.HTTPException):
        raise draft_resources.ResourceBlocked("COMFYUI_QUEUE_UNAVAILABLE") from None
    validate_idle_queue(data)


def require_other_queue_idle(port):
    """Observe the fixed Motion endpoint and the registered managed endpoint."""
    settings = _settings()
    ports = {comfyui.DEFAULT_PORT}
    if settings:
        ports.add(settings["port"])
    for other in sorted(ports - {port}):
        require_idle_queue(other, allow_offline=True)


def _jobs_pending():
    from agentforge.features.film_studio import draft_pipeline
    from agentforge.features.media import visual_jobs
    return draft_pipeline.jobs_pending() or visual_jobs.jobs_pending()


def reset_idle():
    """Reset the countdown while holding LOCK during Studio admission."""
    global _IDLE_SINCE
    _IDLE_SINCE = None


def _stop_owned():
    global _CHILD, _PORT, _STATE, _ERROR
    _STATE, _ERROR = "STOPPING", None
    try:
        _CHILD.terminate()
        _CHILD.wait(timeout=8)
    except (subprocess.TimeoutExpired, OSError) as exc:
        _STATE, _ERROR = "ERROR", f"Could not stop managed ComfyUI PID {_CHILD.pid}: {exc}"
        raise ValueError(_ERROR) from None
    _CHILD, _PORT, _STATE, _ERROR = None, None, "STOPPED", None
    reset_idle()
    _IDLE_WAKE.clear()


def _idle_check():
    global _IDLE_SINCE
    try:
        with LOCK:
            if not _owned() or _STATE != "RUNNING":
                reset_idle()
                _IDLE_WAKE.clear()
                return
            if model_hub.local_inference_busy() or _jobs_pending() or _queue_busy(_PORT):
                reset_idle()
                return
            now = time.monotonic()
            _IDLE_SINCE = max(_IDLE_SINCE if _IDLE_SINCE is not None else now,
                              model_hub.last_local_inference)
            if now - _IDLE_SINCE < IDLE_TIMEOUT:
                return
        # Acquire in the same order as image generation and manual controls.
        with model_hub.local_inference_slot(observe=False), LOCK:
            if (_owned() and _STATE == "RUNNING" and _IDLE_SINCE is not None
                    and model_hub.last_local_inference <= _IDLE_SINCE
                    and not _jobs_pending() and not _queue_busy(_PORT)):
                pid = _CHILD.pid
                _stop_owned()
                _LOG.info("Stopped managed ComfyUI PID %s after %s idle seconds", pid, IDLE_TIMEOUT)
            else:
                reset_idle()
    except PermissionError:
        # An admitted inference (or an unverifiable ledger) invalidates the countdown.
        with LOCK:
            reset_idle()
    except (sqlite3.Error, OSError, ValueError, RuntimeError):
        with LOCK:
            reset_idle()
        _LOG.warning("Could not verify or stop idle ComfyUI", exc_info=True)


def _watch_idle():
    global _IDLE_THREAD

    def run():
        while True:
            _IDLE_WAKE.wait()
            _idle_check()
            time.sleep(_IDLE_INTERVAL)

    reset_idle()
    if _IDLE_THREAD is None:
        _IDLE_THREAD = threading.Thread(target=run, name="comfyui-idle", daemon=True)
        _IDLE_THREAD.start()
    _IDLE_WAKE.set()


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
    transitioning = state in {"STARTING", "STOPPING"}
    data = None if transitioning else _probe(port)
    if transitioning:
        pass
    elif data:
        state = "RUNNING"
    elif managed or _occupied(port) or _CHILD is not None and _PORT == port:
        state = "ERROR"
    else:
        state = "ERROR" if state == "ERROR" else "STOPPED"
    try:
        production_busy = bool((managed or data) and _jobs_pending())
    except (sqlite3.Error, OSError, ValueError, RuntimeError):
        production_busy = True
    return {"state": state, "configured": config["install_root"] is not None,
            "managed": managed, "pid": child.pid if managed else None,
            "endpoint": endpoint, "profile_id": config["profile_id"], "install_root": config["install_root"],
            "busy": production_busy or bool(data and _queue_busy(port)),
            "devices": [{k: device.get(k) for k in ("name", "type", "vram_total", "vram_free")}
                        for device in data["devices"][:8] if isinstance(device, dict)] if data else [],
            "error": (_ERROR or "ComfyUI process exited or endpoint is unavailable") if state == "ERROR" else None}


def managed_exited(port):
    child = _CHILD
    return child is not None and _PORT == port and child.poll() is not None


def ensure_running(port):
    """Called from existing GPU dispatch paths after their inference admission."""
    global _CHILD, _PORT, _STATE, _ERROR
    with LOCK:
        config = _settings()
        if not config:
            raise StartupError("COMFYUI_LAUNCHER_REQUIRED")
        if config["port"] != port:
            raise StartupError("COMFYUI_ENDPOINT_MISMATCH")
        try:
            configured_port, _ = _target(config["profile_id"])
        except ValueError:
            raise StartupError("COMFYUI_ENDPOINT_MISMATCH") from None
        if configured_port != port:
            raise StartupError("COMFYUI_ENDPOINT_MISMATCH")
        if _probe(port):
            return True
        if _owned() or _occupied(port):
            raise ValueError("ComfyUI endpoint is occupied or unresponsive; startup was skipped")
        if os.name != "nt":
            raise ValueError("Managed ComfyUI Portable requires Windows")
        from agentforge import ops_control
        ops_control.require_active()
        resources = draft_resources.snapshot()
        if resources.get("processes", {}).get("comfyui"):
            raise ValueError("Another ComfyUI process is running; check the endpoint in Model Hub")
        pressure = draft_resources.pressure(resources, "image")
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
                stream.write(f"\n[AgentForge] Starting verified Portable launcher on port {port}; cwd={root}\n"
                             .encode("utf-8"))
                stream.flush()
                _CHILD = subprocess.Popen(
                    [str(executable), "-s", str(script), "--windows-standalone-build",
                     "--listen", "127.0.0.1", "--port", str(port), "--cache-none",
                     "--disable-auto-launch", *directories],
                    cwd=root, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                    shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
            _PORT = port
        except OSError as exc:
            _STATE, _ERROR = "ERROR", (
                f"Could not launch registered ComfyUI ({exc.strerror or str(exc)}). "
                "See data/company/runtime_logs/comfyui.log.")
            _LOG.exception("ComfyUI launch failed")
            raise ValueError(_ERROR) from None
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if not _owned():
                break
            if _probe(port) and _owned():
                _STATE = "RUNNING"
                _watch_idle()
                return True
            time.sleep(1)
        code = _CHILD.poll()
        if code is None:
            reason = f"ComfyUI PID {_CHILD.pid} timed out after {START_TIMEOUT}s waiting for /system_stats."
            # An owned child that never bound the port cannot be running a provider job.
            if not _occupied(port):
                _stop_owned()
        else:
            reason = f"ComfyUI PID {_CHILD.pid} exited before readiness (exit code {code})."
        _STATE, _ERROR = "ERROR", reason + " See data/company/runtime_logs/comfyui.log."
        _LOG.error("%s", _ERROR)
        raise ValueError(_ERROR)


def control(action):
    global _CHILD, _PORT, _STATE, _ERROR
    with LOCK:
        config = _settings()
        if not config:
            raise ValueError("Register the ComfyUI Portable launcher first")
        port = config["port"]
        if action in {"stop", "restart"}:
            if _jobs_pending():
                raise PermissionError("A draft production is active")
            if _owned():
                probe = _probe(port)
                if _PORT != port or (probe and _queue_busy(port)):
                    raise PermissionError("ComfyUI has a job or its queue cannot be verified")
                if not probe and _occupied(port):
                    raise PermissionError("Cannot verify ComfyUI queue before stopping")
                _stop_owned()
            elif _occupied(port):
                raise PermissionError("AgentForge cannot stop a ComfyUI it did not launch")
            else:
                _CHILD, _PORT, _STATE, _ERROR = None, None, "STOPPED", None
        if action in {"start", "restart"}:
            ensure_running(port)
        result = status()
        if action in {"start", "restart"} and result["state"] != "RUNNING":
            raise ValueError(result["error"] or "ComfyUI stopped responding after startup")
        return result
