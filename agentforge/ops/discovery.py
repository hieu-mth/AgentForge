"""Bounded Owner inventory. Discovery is never evidence that inference works."""
import csv
import ctypes
import http.client
import json
import os
import platform
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from agentforge.ai import model_hub
from agentforge.integrations import comfyui
from agentforge.ops import runtime_certification as probes
from agentforge.paths import REPOSITORY_ROOT

PROBE_ERRORS = (OSError, ValueError, RuntimeError, TypeError, http.client.HTTPException)
MAX_MODELS = 100


def _memory():
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
                (field, ctypes.c_uint64) for field in (
                    "total", "available", "page_total", "page_available",
                    "virtual_total", "virtual_available", "extended_available")]

        state = MemoryStatus()
        state.length = ctypes.sizeof(state)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            return {"total_bytes": state.total, "available_bytes": state.available}
    elif sys.platform.startswith("linux"):
        try:
            fields = {}
            with Path("/proc/meminfo").open(encoding="ascii") as source:
                for line in source:
                    key, _, value = line.partition(":")
                    if key in {"MemTotal", "MemAvailable"}:
                        fields[key] = int(value.split()[0]) * 1024
            return {"total_bytes": fields.get("MemTotal"),
                    "available_bytes": fields.get("MemAvailable")}
        except (OSError, ValueError, IndexError):
            pass
    return {"total_bytes": None, "available_bytes": None}


def _command(executable, *args):
    try:
        proc = subprocess.run([executable, *args], cwd=REPOSITORY_ROOT,
                              stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=3, check=False)
        if proc.returncode == 0 and len(proc.stdout) <= 32_768:
            return proc.stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _software(name, executable, *args):
    if not executable:
        return {"id": name, "status": "NOT_INSTALLED", "scope": "PATH or bundled executable"}
    output = _command(executable, *args)
    first_line = output.splitlines()[0][:160] if output and output.splitlines() else None
    return {"id": name, "status": "READY" if first_line else "INSTALLED",
            "version": first_line, "scope": "version command only"}


def _gpu():
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"status": "UNKNOWN", "devices": [], "error": "NVIDIA_SMI_NOT_FOUND"}
    output = _command(executable,
                      "--query-gpu=name,driver_version,memory.total,memory.free",
                      "--format=csv,noheader,nounits")
    devices = []
    for row in csv.reader((output or "").splitlines(), skipinitialspace=True):
        if len(row) != 4:
            continue
        name, driver, total, free = row
        devices.append({"name": name[:120], "driver_version": driver[:60],
                        "vram_total_mib": int(total) if total.isascii() and total.isdecimal() else None,
                        "vram_free_mib": int(free) if free.isascii() and free.isdecimal() else None})
    return {"status": "RUNNING" if devices else "ERROR", "devices": devices[:16],
            "cuda_toolkit": _software("cuda", shutil.which("nvcc"), "--version")}


def _error(exc):
    if isinstance(exc, ConnectionRefusedError):
        return "STOPPED", "CONNECTION_REFUSED"
    if isinstance(exc, TimeoutError):
        return "DEGRADED", "TIMEOUT"
    return "ERROR", "INVALID_OR_UNAVAILABLE_RESPONSE"


def _model(provider, endpoint, category, name, *, size=None, family=None):
    return {"id": f"{provider}:{endpoint}:{category}:{name}", "name": name,
            "provider": provider, "endpoint": endpoint, "type": category, "family": family,
            "size_bytes": size if type(size) is int and size >= 0 else None,
            "status": "INSTALLED", "loadability": "UNKNOWN",
            "capabilities": [], "hardware_requirements": None}


def _ollama(endpoint):
    service = {"id": "ollama", "endpoint": endpoint}
    try:
        host, port = probes._local_endpoint(endpoint)
        response = probes._http_json(host, port, "/api/tags", timeout=2)
        entries = response.get("models")
        if not isinstance(entries, list):
            raise ValueError("Invalid catalog")
        models = []
        for item in entries[:MAX_MODELS]:
            if not isinstance(item, dict):
                continue
            name, details = item.get("name"), item.get("details")
            if isinstance(name, str) and 0 < len(name) <= 180 and name.isprintable():
                family = details.get("family") if isinstance(details, dict) else None
                models.append(_model("ollama", endpoint, "ollama_model", name,
                                     size=item.get("size"), family=family[:80] if isinstance(family, str) else None))
        return {**service, "status": "RUNNING", "check": "MODEL_CATALOG",
                "truncated": len(entries) > MAX_MODELS}, models
    except PROBE_ERRORS as exc:
        status, reason = _error(exc)
        return {**service, "status": status, "error": reason}, []


def _comfy(port):
    endpoint = f"http://127.0.0.1:{port}"
    service = {"id": "comfyui", "endpoint": endpoint}
    try:
        stats = comfyui.request_json("/system_stats", port=port, timeout=2)
        if not isinstance(stats, dict) or not isinstance(stats.get("devices"), list):
            raise ValueError("Invalid system stats")
    except PROBE_ERRORS as exc:
        status, reason = _error(exc)
        return {**service, "status": status, "error": reason}, []
    categories = comfyui.MODEL_CATEGORIES
    with ThreadPoolExecutor(max_workers=len(categories)) as pool:
        results = list(pool.map(lambda key: _comfy_catalog_at_port(key, port), categories))
    models, errors = [], {}
    truncated = False
    for category, (entries, error) in zip(categories, results):
        if error:
            errors[category] = error
        truncated = truncated or len(entries) > MAX_MODELS
        for name in entries[:MAX_MODELS]:
            if isinstance(name, str) and 0 < len(name) <= 240 and name.isprintable():
                models.append(_model("comfyui", endpoint, category, name))
    return {**service, "status": "DEGRADED" if errors else "RUNNING", "check": "SYSTEM_STATS",
            "catalog_errors": errors, "truncated": truncated}, models


def _comfy_catalog_at_port(category, port):
    try:
        entries = json.loads(comfyui.request_image_bytes("/models/" + category, port=port, timeout=2))
        if not isinstance(entries, list):
            raise ValueError("Invalid catalog")
        return entries, None
    except PROBE_ERRORS as exc:
        return [], _error(exc)[1]


def _browser_preflight():
    from agentforge.features.webapps import sandbox
    docker, host, image = probes._docker_context()
    if image is None:
        return {"status": "QA_IMAGE_NOT_PINNED"}
    sandbox._image_ready(docker, host, image, timeout=3)
    return {"status": "READY_FOR_OFFLINE_SANDBOX_TEST"}


def inspect():
    """One live snapshot with no model loads, installation, or external addresses."""
    disk = shutil.disk_usage(REPOSITORY_ROOT)
    try:
        profiles = model_hub.catalog()["profiles"]
        config_error = None
    except PROBE_ERRORS:
        profiles, config_error = [], "MODEL_CONFIG_UNAVAILABLE"
    ollama = sorted({p["base_url"] for p in profiles if p["provider"] == "ollama"})
    comfy = sorted({probes._local_endpoint(p["base_url"])[1]
                    for p in profiles if p["provider"] == "comfyui"})
    # Check conventional local service endpoints even without an Owner profile.
    ollama = list(dict.fromkeys(["http://127.0.0.1:11434", *ollama]))
    comfy = list(dict.fromkeys([comfyui.DEFAULT_PORT, *comfy]))
    try:
        ffmpeg = probes._ffmpeg_executable()
    except PROBE_ERRORS:
        ffmpeg = None
    software_commands = [
        ("node", shutil.which("node"), "--version"),
        ("git", shutil.which("git"), "--version"),
        ("docker", shutil.which("docker"), "--version"),

        ("ffmpeg", ffmpeg, "-version"),
    ]
    with ThreadPoolExecutor(max_workers=10) as pool:
        tools = [pool.submit(_software, *args) for args in software_commands]
        gpu = pool.submit(_gpu)
        docker = pool.submit(probes._safe_probe, _browser_preflight)
        runtime = [pool.submit(_ollama, endpoint) for endpoint in ollama[:4]]
        runtime.extend(pool.submit(_comfy, port) for port in comfy[:4])
        rows = [future.result() for future in runtime]
    checked_at = datetime.now(timezone.utc).isoformat()
    services = [service for service, _ in rows]
    models = list({model["id"]: model for _, entries in rows for model in entries}.values())
    browser = docker.result()
    checked = {(row["id"], row["endpoint"]): row for row in services}
    present = {(row["provider"], row["endpoint"], row["name"]) for row in models}
    configured = []
    for profile in profiles:
        provider = profile["provider"]
        endpoint = profile.get("base_url")
        if provider == "comfyui":
            endpoint = f"http://127.0.0.1:{probes._local_endpoint(endpoint)[1]}"
        service = checked.get((provider, endpoint))
        status = "DISABLED" if not profile["enabled"] else "UNKNOWN"
        if profile["enabled"] and (provider, endpoint, profile["model"]) in present:
            status = "INSTALLED"
        elif profile["enabled"] and provider == "ollama" and service and (
                service["status"] == "RUNNING" and not service["truncated"]):
            status = "NOT_INSTALLED"
        configured.append({"id": profile["id"], "provider": provider,
                           "name": profile["model"], "status": status})
    return {"checked_at": checked_at, "config_error": config_error,
            "endpoints_truncated": len(ollama) > 4 or len(comfy) > 4,
            "hardware": {"os": platform.system(), "os_release": platform.release(),
                         "cpu": platform.processor() or platform.machine(),
                         "architecture": platform.machine(), "logical_cpu_count": os.cpu_count(),
                         "memory": _memory(), "gpu": gpu.result(),
                         "disk": {"total_bytes": disk.total, "free_bytes": disk.free,
                                  "scope": "workspace volume"}},
            "software": [{"id": "python", "status": "READY", "version": platform.python_version(),
                          "scope": "active virtualenv" if sys.prefix != sys.base_prefix else "active interpreter"},
                         {"id": "ollama", "status": "INSTALLED" if shutil.which("ollama")
                          else "NOT_INSTALLED", "scope": "CLI in PATH"},
                         *[future.result() for future in tools]],
            "services": services, "models": models, "configured_models": configured,
            "browser_qa": {"status": "INSTALLED" if browser["status"] == "READY_FOR_OFFLINE_SANDBOX_TEST"
                           else "UNKNOWN", "detail": browser["status"], "smoke_tested": False},
            "validation": {"discovery": True, "model_loadability": "UNKNOWN",
                           "capability_smoke": "NOT_RUN", "benchmark": "NOT_RUN"}}
