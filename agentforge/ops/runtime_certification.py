"""Owner-side runtime evidence, deliberately distinct from CI contract tests.

Default: bounded localhost GETs and read-only executable/image inspection.
Explicit flags: one Ollama inference, disposable FFmpeg fixture or pinned
offline Docker container. No cloud calls, model pulls, Owner artifact reads,
secret dumps, retries, publishing or production certification.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from agentforge.paths import REPOSITORY_ROOT, WORKSPACE_DIR

REPORT_FORMAT = "agentforge.owner-runtime-evidence.v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
MAX_TAGS_BYTES = 262_144
MAX_INFERENCE_BYTES = 65_536


def _result(status, **fields):
    return {"status": status, **fields}


def _safe_probe(callback):
    """Never surface paths, provider bodies, exception text or credentials."""
    try:
        return callback()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError,
            TimeoutError, http.client.HTTPException, UnicodeError):
        return _result("UNAVAILABLE")


def _local_endpoint(value):
    if not isinstance(value, str) or len(value) > 120:
        raise ValueError("Invalid local model endpoint")
    parts = urlsplit(value)
    try:
        valid = (parts.scheme == "http" and parts.hostname in LOOPBACK
                 and parts.port is not None and 1 <= parts.port <= 65535
                 and parts.path in ("", "/") and not parts.query
                 and not parts.fragment and parts.username is None
                 and parts.password is None)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Local model endpoint must be loopback")
    return parts.hostname, parts.port


def _http_json(host, port, route, *, payload=None, timeout=3, max_bytes=MAX_TAGS_BYTES):
    """No proxy/redirect: exact loopback host plus hardcoded Ollama route."""
    if host not in LOOPBACK or route not in ("/api/tags", "/api/chat"):
        raise ValueError("Unapproved local route")
    if (type(port) is not int or not 1 <= port <= 65535
            or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_TAGS_BYTES
            or type(timeout) not in (int, float) or not 0 < timeout <= 150):
        raise ValueError("Invalid HTTP budget")
    body = None if payload is None else json.dumps(
        payload, ensure_ascii=True, allow_nan=False).encode("utf-8")
    if body is not None and len(body) > 4096:
        raise ValueError("Local inference probe payload too large")
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("POST" if body is not None else "GET", route,
                           body=body, headers={"Accept": "application/json",
                                               "Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError("Local provider did not return HTTP 200")
        data = response.read(max_bytes + 1)
    finally:
        connection.close()
    if len(data) > max_bytes:
        raise ValueError("Local provider response exceeds byte budget")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Local provider returned non-object JSON")
    return value


def _ollama_profile(model_ref):
    from agentforge.ai import model_hub
    if not isinstance(model_ref, str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,39}", model_ref):
        raise ValueError("Invalid local model reference")
    models = model_hub.effective_models()
    profile = models.get(model_ref)
    if not isinstance(profile, dict) or profile.get("provider") != "ollama" or profile.get("enabled") is not True:
        raise ValueError("Selected model is not an enabled local Ollama profile")
    host, port = _local_endpoint(profile["base_url"])
    name = profile["model"]
    if not isinstance(name, str) or not 1 <= len(name) <= 160:
        raise ValueError("Invalid model identifier")
    return host, port, name


def _ollama_preflight(model_ref):
    host, port, name = _ollama_profile(model_ref)
    tags = _http_json(host, port, "/api/tags", max_bytes=MAX_TAGS_BYTES)
    entries = tags.get("models")
    if not isinstance(entries, list):
        raise ValueError("Invalid local model list")
    installed = any(isinstance(item, dict) and item.get("name") == name
                    for item in entries)
    return _result("READY_FOR_INFERENCE" if installed else "MODEL_NOT_INSTALLED",
                   model_ref=model_ref, model_installed=installed,
                   inference_invoked=False, model_downloaded=False)


def _ollama_inference(model_ref):
    host, port, name = _ollama_profile(model_ref)
    start = time.monotonic()
    response = _http_json(host, port, "/api/chat",
                          payload={"model": name, "stream": False, "think": False,
                                   "options": {"num_predict": 32, "temperature": 0},
                                   "messages": [
                                       {"role": "system", "content": "Respond briefly."},
                                       {"role": "user", "content": "Say READY."},
                                   ]},
                          timeout=120, max_bytes=MAX_INFERENCE_BYTES)
    message = response.get("message")
    answer = message.get("content") if isinstance(message, dict) else None
    if (not isinstance(answer, str) or not answer.strip()
            or response.get("done") is not True):
        raise ValueError("Incomplete local model answer")
    receipt = hashlib.sha256(answer.encode("utf-8")).hexdigest()
    return _result("PASS_RUNTIME", inference_invoked=True,
                   model_ref=model_ref, output_sha256=receipt,
                   output_not_saved=True,
                   duration_seconds=round(time.monotonic() - start, 2),
                   response_bounded=True, automatic_retry=False)


def _comfy_preflight():
    from agentforge.features.film_studio import motion_comfy
    from agentforge.features.websites import image_studio
    motion = motion_comfy.health()
    images = image_studio.health()
    # Only structured non-identifying metadata; no GPU host device names.
    return _result(
        "READY_FOR_OWNER_GPU_PILOT" if
        motion.get("status") == "GPU_DETECTED_UNBENCHMARKED"
        else "UNAVAILABLE",
        motion_status=motion.get("status", "UNAVAILABLE"),
        image_status=images.get("status", "UNAVAILABLE"),
        vram_gib=motion.get("vram_gib"),
        free_vram_snapshot_gib=motion.get("vram_free_snapshot_gib"),
        generated_frames=0, gpu_inference_invoked=False,
        video_verified=False)


def _ffmpeg_executable():
    from agentforge.features.media import render
    return render._ffmpeg()


def _ffmpeg_preflight():
    executable = _ffmpeg_executable()
    run = subprocess.run(
        [executable, "-hide_banner", "-version"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=8, check=False)
    return _result("READY_FOR_ENCODE_TEST" if run.returncode == 0 else "UNAVAILABLE",
                   encode_invoked=False)


def _ffmpeg_runtime():
    """Actual encode + audio/video decode in an automatically deleted fixture."""
    from agentforge.features.media.quality import _mp4_structural
    executable = _ffmpeg_executable()
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="agentforge-ffmpeg-evidence-") as temp:
        mp4 = Path(temp) / "isolated.mp4"
        encode = [
            executable, "-hide_banner", "-v", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=12:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=1",
            "-t", "1", "-c:v", "mpeg4", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(mp4),
        ]
        encoded = subprocess.run(
            encode, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=45, check=False)
        if encoded.returncode != 0 or not mp4.is_file():
            raise RuntimeError("FFmpeg fixture encode failed")
        _mp4_structural(mp4)
        decoded = subprocess.run(
            [executable, "-hide_banner", "-v", "error", "-xerror", "-nostdin",
             "-i", str(mp4), "-map", "0:v:0", "-map", "0:a:0",
             "-f", "null", "-"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=30, check=False)
        if decoded.returncode != 0:
            raise RuntimeError("FFmpeg fixture decode failed")
        digest = hashlib.sha256(mp4.read_bytes()).hexdigest()
        size = mp4.stat().st_size
    return _result("PASS_RUNTIME", encode_invoked=True, decode_invoked=True,
                   audio_track_verified=True, video_track_verified=True,
                   fixture_sha256=digest, fixture_bytes=size,
                   temporary_fixture_deleted=True,
                   duration_seconds=round(time.monotonic() - start, 2))


def _docker_context():
    from agentforge.features.webapps import sandbox
    docker, host = sandbox._docker_executable(), sandbox._local_docker_host()
    image = os.environ.get("AGENTFORGE_BROWSER_QA_IMAGE", "")
    if not sandbox.IMAGE_ID.fullmatch(image):
        return docker, host, None
    return docker, host, image


def _docker_preflight():
    from agentforge.features.webapps import sandbox
    docker, host, image = _docker_context()
    if image is None:
        return _result("QA_IMAGE_NOT_PINNED", container_started=False)
    sandbox._image_ready(docker, host, image)
    return _result("READY_FOR_OFFLINE_SANDBOX_TEST", pinned_image=True,
                   container_started=False, browser_qa_verified=False)


def _docker_runtime():
    """Start only the cached, SHA-pinned QA image; no source or network mount."""
    from agentforge.features.webapps import sandbox
    docker, host, image = _docker_context()
    if image is None:
        raise ValueError("A local browser QA image must be pinned by SHA")
    sandbox._image_ready(docker, host, image)
    args = [
        docker, "-H", host, "run", "--rm", "--pull", "never",
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges=true",
        "--user", "10001:10001", "--cpus", "1", "--memory", "512m",
        "--memory-swap", "512m", "--pids-limit", "32", "--ipc", "none",
        "--entrypoint", "node", image, "--version",
    ]
    result = subprocess.run(
        args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=45, check=False, env=sandbox._env())
    if result.returncode != 0:
        raise RuntimeError("Pinned offline QA container failed to start")
    return _result("PASS_RUNTIME", container_started=True,
                   pinned_image=True, network="none", source_executed=False,
                   browser_qa_verified=False, image_pull_performed=False)


def _dashboard_preflight():
    connection = http.client.HTTPConnection("127.0.0.1", 8780, timeout=3)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        valid = response.status in (200, 301, 302, 303, 307, 308)
    finally:
        connection.close()
    return _result("HTTP_REACHABLE_LOGIN_NOT_VERIFIED" if valid else "UNAVAILABLE",
                   owner_login_verified=False)


def inspect(*, model_ref="local_primary", run_ollama=False,
            run_ffmpeg=False, run_docker=False):
    """Actual host probes, no mocks; explicitly tagged which stages ran."""
    checks = {
        "python": _result("PASS_PRECHECK" if sys.version_info >= (3, 13)
                          else "BLOCKED", python_313_or_newer=sys.version_info >= (3, 13)),
        "node": _result("TOOL_PRESENT" if shutil.which("node") else "UNAVAILABLE"),
        "npm": _result("TOOL_PRESENT" if shutil.which("npm.cmd" if os.name == "nt" else "npm")
                       else "UNAVAILABLE"),
        "ollama": _safe_probe(lambda: _ollama_preflight(model_ref)),
        "comfyui_gpu": _safe_probe(_comfy_preflight),
        "ffmpeg": _safe_probe(_ffmpeg_preflight),
        "docker": _safe_probe(_docker_preflight),
        "dashboard": _safe_probe(_dashboard_preflight),
    }
    # No automatic escalation: optional probes each need a separate CLI flag.
    if run_ollama:
        checks["ollama_inference"] = _safe_probe(lambda: _ollama_inference(model_ref))
    if run_ffmpeg:
        checks["ffmpeg_encode_decode"] = _safe_probe(_ffmpeg_runtime)
    if run_docker:
        checks["docker_offline_container"] = _safe_probe(_docker_runtime)
    checks.update({
        "ai_generated_app_browser_qa": _result("OWNER_RUNTIME_PENDING"),
        "film_motion_import_decode_owner_review": _result("OWNER_RUNTIME_PENDING"),
        "real_business_backup_staged_restore": _result("OWNER_RUNTIME_PENDING"),
        "dashboard_owner_login_and_workflow": _result("OWNER_RUNTIME_PENDING"),
    })
    failed_opt_in = any(
        checks[key]["status"] != "PASS_RUNTIME" for key, run in (
            ("ollama_inference", run_ollama), ("ffmpeg_encode_decode", run_ffmpeg),
            ("docker_offline_container", run_docker)) if run)
    report = {
        "format": REPORT_FORMAT,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_id": uuid4().hex,
        "status": "OPTIONAL_PROBE_FAILED" if failed_opt_in else "OWNER_RUNTIME_PENDING",
        "checks": checks,
        "explicit_authorization": {
            "local_ollama_inference": bool(run_ollama),
            "disposable_ffmpeg_fixture": bool(run_ffmpeg),
            "offline_pinned_docker_container": bool(run_docker),
        },
        "cloud_requests": 0, "model_downloads": 0,
        "gpu_jobs_submitted": 0, "youtube_uploads": 0,
        "existing_owner_data_modified_by_design": False,
        "generated_app_browser_verified": False,
        "real_gpu_video_verified": False,
        "production_go": False,
    }
    digest = hashlib.sha256(json.dumps(
        report, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("utf-8")).hexdigest()
    report["report_sha256"] = digest
    return report


def save_report(report):
    """Explicitly create a new redacted receipt in ignored Owner workspace."""
    folder = WORKSPACE_DIR / "runtime-certification"
    for part in (WORKSPACE_DIR, folder):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise PermissionError("Runtime receipt directory is a link")
    folder.mkdir(parents=True, exist_ok=True)
    name = "runtime-" + report["evidence_id"] + ".json"
    dest = folder / name
    with dest.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    return dest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Owner-side real runtime probes, NOT production GO")
    parser.add_argument("--model-ref", default="local_primary")
    parser.add_argument("--run-ollama", action="store_true")
    parser.add_argument("--confirm-inference", action="store_true")
    parser.add_argument("--run-ffmpeg", action="store_true")
    parser.add_argument("--confirm-local-exec", action="store_true")
    parser.add_argument("--run-docker", action="store_true")
    parser.add_argument("--confirm-docker-run", action="store_true")
    parser.add_argument("--save-report", action="store_true")
    args = parser.parse_args(argv)
    if (args.run_ollama and not args.confirm_inference
            or args.run_ffmpeg and not args.confirm_local_exec
            or args.run_docker and not args.confirm_docker_run):
        parser.error("Every active probe requires its matching explicit confirmation flag")
    report = inspect(model_ref=args.model_ref, run_ollama=args.run_ollama,
                     run_ffmpeg=args.run_ffmpeg, run_docker=args.run_docker)
    if args.save_report:
        dest = save_report(report)
        report["saved_receipt_filename"] = dest.name
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if report["status"] == "OPTIONAL_PROBE_FAILED":
        parser.exit(2)


if __name__ == "__main__":
    main()
