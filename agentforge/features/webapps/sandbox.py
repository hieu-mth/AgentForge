"""V4.2: explicit Owner-gated offline Docker verification of signed React app.

No model calls, package installation, image pulls or native npm runs. The only
executed app code is inside a restricted Linux container on the local Docker
daemon, with source bind-mounted read-only. This is defense-in-depth isolation,
not a proof against container-runtime vulnerabilities.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from agentforge import webapp_builder as builder
from agentforge import webapp_developer
from agentforge.paths import REPOSITORY_ROOT

ROOT = REPOSITORY_ROOT
QA_STAGING = ROOT / "workspace" / ".webapp-qa-staging"
IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}\Z")
MAX_TIMEOUT_SECONDS = 150
CHECKS = ["node-unit-tests", "vite-production-build"]
# Fixed trusted code checks the cached image, not generated package scripts.
# Vite's supported esbuild range includes 0.28; an old cached image must fail.
TOOLCHAIN_CHECK = (
    "node -e 'const {createRequire}=require(\"node:module\");"
    "const r=createRequire(\"/opt/agentforge/package.json\");"
    "const v=r(\"vite/package.json\");"
    "const e=createRequire(r.resolve(\"vite/package.json\"))(\"esbuild/package.json\");"
    "if(v.version!==\"7.3.7\"||e.version!==\"0.28.1\")process.exit(70)' && "
)
# The only shell text executed is fixed trusted code *inside* the isolated
# container. Nothing from an AI model or Owner prompt becomes shell syntax.
CONTAINER_SCRIPT = (
    "test -d /opt/agentforge/node_modules && "
    + TOOLCHAIN_CHECK +
    "cp -R /input/. /work/ && "
    "ln -s /opt/agentforge/node_modules /work/node_modules && "
    "npm run test && npm run build"
)


def _local_docker_host():
    return ("npipe:////./pipe/docker_engine" if os.name == "nt"
            else "unix:///var/run/docker.sock")


def _docker_executable():
    executable = shutil.which("docker")
    if not executable:
        raise RuntimeError("SANDBOX_UNAVAILABLE: Docker CLI is not installed")
    return executable


def _pinned_image():
    value = os.environ.get("AGENTFORGE_SANDBOX_IMAGE", "")
    if not IMAGE_ID.fullmatch(value):
        raise RuntimeError("SANDBOX_UNAVAILABLE: Owner must pin a local image ID")
    return value


def _env():
    # Never pass cloud/model keys, tokens, app secrets or arbitrary DOCKER_HOST.
    allowed = ("PATH", "SystemRoot", "USERPROFILE", "HOME", "TMP", "TEMP")
    return {key: os.environ[key] for key in allowed if key in os.environ}


def _image_ready(docker, host, image):
    try:
        r = subprocess.run(
            [docker, "-H", host, "image", "inspect", "--format", "{{.Os}}", image],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=15,
            text=True, encoding="utf-8", errors="replace", env=_env(),
            check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("SANDBOX_UNAVAILABLE: Docker daemon unavailable") from exc
    if r.returncode != 0 or r.stdout.strip() != "linux":
        raise RuntimeError("SANDBOX_UNAVAILABLE: Pinned Linux image not cached locally")


def _mount_source(path):
    source = str(path.resolve())
    if (not path.is_dir() or any(char in source for char in (",", "\n", "\r", "="))):
        raise PermissionError("SANDBOX_INVALID_SOURCE: unsupported staging path")
    return "type=bind,source=" + source + ",target=/input,readonly"


def verify(proposal_id, sha256, *, confirm_external_run=False):
    """Bounded local container build after separate explicit Owner approval."""
    if confirm_external_run is not True:
        raise PermissionError("SANDBOX_APPROVAL_REQUIRED")
    provider = webapp_developer.provider(proposal_id)
    document, _ = provider._read_proposal(proposal_id)
    if sha256 != document["sha256"]:
        raise PermissionError("SANDBOX_SOURCE_STALE")
    from agentforge.features.webapps import toolchain, syntax
    toolchain.require_current(document["files"])
    report = syntax.check_files(document["files"], sha256)
    if report["status"] != "PASS":
        raise syntax.SourceSyntaxError(report)
    # Never try native npm or any process if pinned Docker is unavailable.
    image = _pinned_image()
    docker, host = _docker_executable(), _local_docker_host()
    _image_ready(docker, host, image)

    root = QA_STAGING
    builder._path_guard(root)
    root.mkdir(parents=True, exist_ok=True)
    builder._path_guard(root)

    name = "af-qa-" + uuid4().hex[:16]
    with tempfile.TemporaryDirectory(prefix="signed-", dir=root) as directory:
        stage = Path(directory)
        builder._path_guard(stage)
        for item in document["files"]:
            dest = stage / item["path"]  # Exact file allowlist validated by _read_proposal.
            builder._path_guard(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("x", encoding="utf-8") as stream:
                stream.write(item["content"])
        args = [
            docker, "-H", host, "run", "--rm", "--pull", "never",
            "--name", name, "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges=true",
            "--user", "10001:10001",
            "--cpus", "1", "--memory", "1024m", "--memory-swap", "1024m",
            "--pids-limit", "64", "--ipc", "none",
            "--tmpfs", "/work:rw,exec,nosuid,size=768m,uid=10001,gid=10001",
            "--tmpfs", "/tmp:rw,exec,nosuid,size=64m,uid=10001,gid=10001",
            "--mount", _mount_source(stage),
            "--workdir", "/work",
            "--env", "HOME=/tmp", "--env", "CI=1",
            "--env", "npm_config_audit=false",
            "--env", "npm_config_offline=true",
            "--entrypoint", "/bin/sh", image, "-ec", CONTAINER_SCRIPT,
        ]
        needs_cleanup = True
        try:
            result = subprocess.run(
                args, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=_env(), timeout=MAX_TIMEOUT_SECONDS, check=False)
            needs_cleanup = False  # --rm removes a normally exited container.
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("SANDBOX_TIMEOUT: Container exceeded build deadline") from exc
        except OSError as exc:
            raise RuntimeError("SANDBOX_UNAVAILABLE: Cannot start Docker") from exc
        finally:
            if needs_cleanup:
                # Killing the CLI does not necessarily kill the container.
                # Force-remove only the unique container created for this run.
                try:
                    subprocess.run(
                        [docker, "-H", host, "container", "rm", "-f", name],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=15, env=_env(),
                        check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        if result.returncode == 70:
            raise RuntimeError("SANDBOX_UNAVAILABLE: Rebuild the pinned QA image with the patched lockfile")
        if result.returncode != 0:
            raise RuntimeError("SANDBOX_BUILD_FAILED: Reviewed app did not pass npm test/build")
    return {
        "status": "PASS",
        "stage": "BUILD_VALID", "build_verified": True, "browser_verified": False,
        "project_slug": document["project_slug"],
        "proposal_id": proposal_id,
        "sha256": sha256,
        "checks": CHECKS,
        "runtime": "docker-local-linux",
        "network": "none",
        "source_mount": "read_only",
        "model_called": False,
        "deployment_authorized": False,
        "ai_code_experimental": provider is not builder,
    }


def main():
    p = argparse.ArgumentParser(description="Owner-gated offline container QA")
    p.add_argument("proposal_id")
    p.add_argument("--sha256", required=True)
    p.add_argument("--confirm-external-run", action="store_true")
    args = p.parse_args()
    print(json.dumps(
        verify(args.proposal_id, args.sha256,
               confirm_external_run=args.confirm_external_run),
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
