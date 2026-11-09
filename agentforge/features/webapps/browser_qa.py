"""Owner-gated, offline browser smoke for signed AI React source in Docker.

No generated code on the host: trusted Node/Playwright runs *inside* an
Owner-pinned Linux image. No network, writable source mount, host browser,
model call, npm install or build artifact execution on Windows.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from agentforge import webapp_builder as builder, webapp_developer
from agentforge.features.webapps import sandbox, syntax, toolchain

REPORTS = sandbox.ROOT / "workspace" / "webapp-browser-qa"
IMAGE_ENV = "AGENTFORGE_BROWSER_QA_IMAGE"
MAX_STDOUT = 2_100_000
MAX_IMAGE_BYTES = 700_000
MAX_SECONDS = 195
PNG = bytes.fromhex("89504e470d0a1a0a")
CHECK_KEYS = {"desktop_main", "body_content", "interactive_button",
              "mobile_no_overflow", "no_page_errors", "no_external_requests"}
CODES = {"NODE_TEST_FAILED", "VITE_BUILD_FAILED", "PREVIEW_UNAVAILABLE",
         "SCREENSHOT_TOO_LARGE", "BROWSER_ASSERTION_FAILED", "BROWSER_RUNTIME_FAILED",
         "BROWSER_SMOKE_ONLY"}
SCRIPT = (
    "test -d /opt/agentforge/node_modules && "
    + sandbox.TOOLCHAIN_CHECK
    + "cp -R /input/. /work/ && "
    "ln -s /opt/agentforge/node_modules /work/node_modules && "
    "node /opt/agentforge/browser_runner.mjs"
)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _report_hash(record):
    return _sha(json.dumps(record, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8"))


def _image():
    value = os.environ.get(IMAGE_ENV, "")
    if not sandbox.IMAGE_ID.fullmatch(value):
        raise RuntimeError("SANDBOX_UNAVAILABLE: pin browser QA Linux image SHA")
    return value


def _decode_png(text):
    if not isinstance(text, str) or len(text) > MAX_IMAGE_BYTES * 2:
        raise ValueError("BROWSER_QA_INVALID_SCREENSHOT")
    try:
        data = base64.b64decode(text, validate=True)
    except (ValueError, base64.binascii.Error):
        raise ValueError("BROWSER_QA_INVALID_SCREENSHOT") from None
    if not 50 <= len(data) <= MAX_IMAGE_BYTES or not data.startswith(PNG):
        raise ValueError("BROWSER_QA_INVALID_SCREENSHOT")
    return data


def _parse_output(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_STDOUT:
        raise ValueError("BROWSER_QA_INVALID_OUTPUT")
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ValueError("BROWSER_QA_INVALID_OUTPUT") from None
    required = {"format", "status", "code"}
    if (not isinstance(data, dict) or not isinstance(data.get("code"), str)
            or data.get("format") !=
            "agentforge.webapp.browser-smoke.v1" or not required.issubset(data)
            or data["code"] not in CODES or data["status"] not in
            {"PASS_SMOKE_ONLY", "FAIL"} or set(data) - required -
            {"checks", "desktop_png", "mobile_png"}):
        raise ValueError("BROWSER_QA_INVALID_OUTPUT")
    is_pass = data["status"] == "PASS_SMOKE_ONLY"
    if is_pass != (data["code"] == "BROWSER_SMOKE_ONLY"):
        raise ValueError("BROWSER_QA_INVALID_OUTPUT")
    checks = data.get("checks")
    if checks is not None and (not isinstance(checks, dict)
                               or set(checks) != CHECK_KEYS
                               or any(type(v) is not bool for v in checks.values())):
        raise ValueError("BROWSER_QA_INVALID_CHECKS")
    if is_pass and (checks is None or not all(checks.values())):
        raise ValueError("BROWSER_QA_INVALID_CHECKS")
    pngs = {}
    for name in ("desktop", "mobile"):
        key = name + "_png"
        if key in data:
            pngs[name + ".png"] = _decode_png(data[key])
    if is_pass and set(pngs) != {"desktop.png", "mobile.png"}:
        raise ValueError("BROWSER_QA_INVALID_SCREENSHOT")
    return {"status": data["status"], "code": data["code"],
            "checks": checks or {}, "pngs": pngs}


def _save(document, output):
    root = REPORTS
    builder._path_guard(root)
    root.mkdir(parents=True, exist_ok=True)
    ident = uuid4().hex
    folder = root / ident
    builder._path_guard(folder)
    folder.mkdir(exist_ok=False)
    screenshot_sha = {}
    for filename, content in output["pngs"].items():
        path = folder / filename
        builder._path_guard(path)
        with path.open("xb") as f:
            f.write(content)
        screenshot_sha[filename] = _sha(content)
    body = {
        "format": "agentforge.webapp.browser-qa.v1",
        "qa_report_id": ident, "proposal_id": document["proposal_id"],
        "source_sha256": document["sha256"], "status": output["status"],
        "code": output["code"], "checks": output["checks"],
        "screenshots": screenshot_sha,
        "build_verified": output["code"] in
            {"BROWSER_SMOKE_ONLY", "BROWSER_ASSERTION_FAILED",
             "SCREENSHOT_TOO_LARGE"},
        "browser_smoke_verified": output["status"] == "PASS_SMOKE_ONLY",
        "functional_flows_verified": False, "security_verified": False,
        "deployment_authorized": False, "network": "none",
        "runtime": "docker-local-linux-chromium",
    }
    record = {**body, "qa_report_sha": _report_hash(body)}
    with (folder / "report.json").open("x", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return {"qa_report_id": ident, "qa_report_sha": record["qa_report_sha"],
            "proposal_id": document["proposal_id"],
            "sha256": document["sha256"], "status": output["status"],
            "code": output["code"], "build_verified": record["build_verified"],
            "browser_smoke_verified": record["browser_smoke_verified"],
            "functional_flows_verified": False, "security_verified": False,
            "screenshots": screenshot_sha, "checks": output["checks"],
            "runtime": "docker-local-linux-chromium", "network": "none",
            "deployment_authorized": False}


def verify(proposal_id, sha256, *, confirm_external_run=False):
    if confirm_external_run is not True:
        raise PermissionError("BROWSER_QA_APPROVAL_REQUIRED")
    provider = webapp_developer.provider(proposal_id)
    document, _ = provider._read_proposal(proposal_id)
    if document["sha256"] != sha256:
        raise PermissionError("SANDBOX_SOURCE_STALE")
    toolchain.require_current(document["files"])
    parsed = syntax.check_files(document["files"], sha256)
    if parsed["status"] != "PASS":
        raise syntax.SourceSyntaxError(parsed)
    image = _image()
    docker, host = sandbox._docker_executable(), sandbox._local_docker_host()
    sandbox._image_ready(docker, host, image)

    root = sandbox.QA_STAGING
    builder._path_guard(root)
    root.mkdir(parents=True, exist_ok=True)
    builder._path_guard(root)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="browser-signed-", dir=root) as tmp:
        stage = Path(tmp)
        builder._path_guard(stage)
        for item in document["files"]:
            dest = stage / item["path"]
            builder._path_guard(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("x", encoding="utf-8") as f:
                f.write(item["content"])
        name = "af-browser-" + uuid4().hex[:16]
        args = [docker, "-H", host, "run", "--rm", "--pull", "never",
                "--name", name, "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges=true",
                "--user", "10001:10001", "--cpus", "2",
                "--memory", "1536m", "--memory-swap", "1536m",
                "--pids-limit", "96", "--ipc", "none",
                "--tmpfs", "/work:rw,exec,nosuid,size=900m,uid=10001,gid=10001",
                "--tmpfs", "/tmp:rw,exec,nosuid,size=256m,uid=10001,gid=10001",
                "--mount", sandbox._mount_source(stage),
                "--workdir", "/work",
                "--env", "HOME=/tmp", "--env", "CI=1",
                "--env", "npm_config_offline=true",
                "--entrypoint", "/bin/sh", image, "-ec", SCRIPT]
        needs_cleanup = True
        try:
            result = subprocess.run(
                args, stdin=subprocess.DEVNULL, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                env=sandbox._env(), timeout=MAX_SECONDS, check=False)
            needs_cleanup = False
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("SANDBOX_TIMEOUT: browser QA exceeded deadline") from exc
        except OSError as exc:
            raise RuntimeError("SANDBOX_UNAVAILABLE: Docker browser QA failed") from exc
        finally:
            if needs_cleanup:
                try:
                    subprocess.run([docker, "-H", host, "container", "rm", "-f", name],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=15,
                                   env=sandbox._env(), check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        if result.returncode == 70:
            raise RuntimeError("SANDBOX_UNAVAILABLE: pinned QA image has wrong toolchain")
        if result.returncode != 0:
            raise RuntimeError("BROWSER_QA_RUNTIME_FAILED: browser process failed")
        output = _parse_output(result.stdout)
    return _save(document, output)


def read_report(report_id, expected_sha):
    if (not isinstance(report_id, str) or not re.fullmatch(r"[a-f0-9]{32}", report_id)
            or not isinstance(expected_sha, str)
            or not re.fullmatch(r"[a-f0-9]{64}", expected_sha)):
        raise ValueError("BROWSER_QA_INVALID_ID")
    folder = REPORTS / report_id
    builder._path_guard(folder)
    path = folder / "report.json"
    builder._path_guard(path)
    if not path.is_file() or path.stat().st_size > 16_000:
        raise ValueError("BROWSER_QA_REPORT_MISSING")
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or set(record) != {
        "format", "qa_report_id", "qa_report_sha", "proposal_id", "source_sha256",
        "status", "code", "checks", "screenshots", "build_verified",
        "browser_smoke_verified", "functional_flows_verified", "security_verified",
        "deployment_authorized", "network", "runtime"}:
        raise ValueError("BROWSER_QA_INVALID_REPORT")
    if (record["format"] != "agentforge.webapp.browser-qa.v1"
            or record["status"] not in {"FAIL", "PASS_SMOKE_ONLY"}
            or record["code"] not in CODES
            or any(record[k] is not False for k in
                   ("functional_flows_verified", "security_verified", "deployment_authorized"))
            or record["network"] != "none"
            or record["runtime"] != "docker-local-linux-chromium"
            or record["browser_smoke_verified"] is not
               (record["status"] == "PASS_SMOKE_ONLY")):
        raise ValueError("BROWSER_QA_INVALID_REPORT")
    if (record["qa_report_id"] != report_id or record["qa_report_sha"] != expected_sha
            or _report_hash({k: v for k, v in record.items() if k != "qa_report_sha"})
            != expected_sha):
        raise PermissionError("BROWSER_QA_REPORT_STALE")
    doc, _ = webapp_developer.provider(record["proposal_id"])._read_proposal(
        record["proposal_id"])
    if doc["sha256"] != record["source_sha256"]:
        raise PermissionError("BROWSER_QA_SOURCE_STALE")
    if record["screenshots"]:
        if set(record["screenshots"]) - {"desktop.png", "mobile.png"}:
            raise ValueError("BROWSER_QA_INVALID_REPORT")
        for filename, expected in record["screenshots"].items():
            fp = folder / filename
            builder._path_guard(fp)
            if not fp.is_file() or fp.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError("BROWSER_QA_SCREENSHOT_MISSING")
            if _sha(fp.read_bytes()) != expected:
                raise PermissionError("BROWSER_QA_SCREENSHOT_STALE")
    return record


def image(report_id, report_sha, filename):
    if filename not in {"desktop.png", "mobile.png"}:
        raise ValueError("BROWSER_QA_INVALID_IMAGE")
    record = read_report(report_id, report_sha)
    if filename not in record["screenshots"]:
        raise ValueError("BROWSER_QA_SCREENSHOT_MISSING")
    return (REPORTS / report_id / filename).read_bytes()
