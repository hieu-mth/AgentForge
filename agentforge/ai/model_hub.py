"""Versioned Owner Model Hub; no model invocation at configuration time.

Owner-added model profiles and route assignments have one source of truth:
versioned SQLite. The capability catalog stays in reviewed Python source.
No profiles or assignments are created by default; GET is read-only.
All model routes are configuration-only until an explicitly reviewed runtime
consumes their bindings. A saved cloud profile never authorizes a cloud call.
"""
from __future__ import annotations

import copy
import hashlib
import base64
import binascii
from contextlib import closing, contextmanager
from threading import Lock
from time import monotonic
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from agentforge.ai import cloud_credentials, orchestrator_policy
from agentforge.ai.orchestrator_policy import ModelConfigError
from agentforge.features.media import flux_workflow
from agentforge.paths import COMPANY_DATA_DIR, ensure_local_root

DB_PATH = COMPANY_DATA_DIR / "model_hub.sqlite3"
ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*\Z")
# Routes are approved capabilities, NOT configured model selections.
# Retain stable IDs for existing Owner SQLite routes and Dashboard clients.
ROUTE_CAPABILITIES = frozenset(key for key, _, kind, _ in orchestrator_policy.CAPABILITIES
                               if kind != "tool" or key == "ops.monitor")

ID_RE = re.compile(r"[a-z][a-z0-9_]{2,39}\Z")
TASK_RE = re.compile(r"[a-z][a-z0-9_.]{2,59}\Z")
MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}\Z")
KINDS = {"text", "image", "video", "vision", "audio", "sound", "music", "rules"}
MAX_PROFILE_COUNT = 32
MAX_STATE_BYTES = 65536
_LOCAL_INFERENCE = Lock()
_LOCAL_ADMISSION = Lock()
last_local_inference = 0.0


def local_inference_busy():
    return _LOCAL_INFERENCE.locked()


@contextmanager
def local_process_slot(path, reason):
    """OS-backed reservation releases when the handle closes, including after a crash."""
    path = ensure_local_root(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if not stream.tell():
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            import msvcrt
        except ImportError:
            import fcntl
            lock = lambda: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            lock = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            lock()
        except OSError:
            raise PermissionError(reason) from None
        yield


@contextmanager
def local_inference_slot(*, observe=True):
    """Serialize inference across AgentForge processes using the same workspace."""
    global last_local_inference
    with _LOCAL_ADMISSION:
        if not _LOCAL_INFERENCE.acquire(blocking=False):
            raise PermissionError("LOCAL_INFERENCE_BUSY")
        if not observe:
            # New GPU requests wait for the final idle transition, then can auto-start.
            try:
                with local_process_slot(DB_PATH.parent / "local_inference.worker", "LOCAL_INFERENCE_BUSY"):
                    yield
            finally:
                _LOCAL_INFERENCE.release()
            return
    try:
        with local_process_slot(DB_PATH.parent / "local_inference.worker", "LOCAL_INFERENCE_BUSY"):
            yield
    finally:
        last_local_inference = monotonic()
        _LOCAL_INFERENCE.release()

# These are the profile adapters accepted by Model Hub. Registration is
# configuration only, including for providers with an existing runtime.
ADAPTERS = {
    "ollama": {
        "label": "Ollama", "connection": "local", "model_label": "Tên model",
        "model_example": "qwen3:8b",
        "description": "Model văn bản chạy qua Ollama trên máy này.",
        "defaults": {"base_url": "http://127.0.0.1:11434"}, "local_probe": True,
    },
    "comfyui": {
        "label": "ComfyUI", "connection": "local", "model_label": "Mã checkpoint",
        "model_example": "ltxv-2b-0.9.8-distilled-fp8.safetensors",
        "description": "Hồ sơ ảnh hoặc video. Đăng ký chỉ lưu cấu hình cho ComfyUI.",
        "defaults": {"base_url": "http://127.0.0.1:8188"}, "local_probe": False,
        "flux_workflow_max_bytes": flux_workflow.MAX_WORKFLOW_BYTES,
        "motion_encoder_supported": True,
    },
    "anthropic": {
        "label": "Anthropic-compatible", "connection": "cloud", "model_label": "Model ID",
        "model_example": "model-id-da-cap",
        "description": "API HTTPS tương thích Anthropic Messages; nhập API base URL và model ID.",
        "defaults": {"base_url": ""},
        "environment_defaults": {"base_url_env": "ANTHROPIC_BASE_URL",
                            "api_key_env": "ANTHROPIC_AUTH_TOKEN"}, "local_probe": False,
        "cloud_probe": True,
    },
    "openai": {
        "label": "OpenAI-compatible", "connection": "cloud", "model_label": "Model ID",
        "model_example": "model-id-da-cap",
        "description": "API HTTPS tương thích Chat Completions; nhập API base URL và model ID.",
        "defaults": {"base_url": ""},
        "environment_defaults": {"base_url_env": "OPENAI_BASE_URL", "api_key_env": "OPENAI_API_KEY"},
        "local_probe": False, "cloud_probe": True,
    },
    "chatgpt": {
        "label": "ChatGPT Plan", "connection": "cloud", "model_label": "Model slug",
        "model_example": "model-tu-lenh-models", "description": "Kết nối local bằng OAuth chính thức; không nhập API key. Chạy CLI chatgpt_auth login trước.",
        "defaults": {"account_ref": "owner"}, "local_probe": False, "cloud_probe": True,
    },
    "ltx_cloud": {
        "label": "LTX Cloud", "connection": "cloud", "model_label": "Model ID",
        "model_example": "ltx-2-3-fast", "description": "LTX V2 video; 720p, 24 fps, 6/8/10 giây. Chỉ gửi sau duyệt ngân sách.",
        "defaults": {"base_url": "https://api.ltx.io"},
        "environment_defaults": {"base_url_env": "LTX_BASE_URL", "api_key_env": "LTX_API_KEY"},
        "local_probe": False, "cloud_probe": False,
    },
    "elevenlabs": {
        "label": "ElevenLabs-compatible", "connection": "cloud", "model_label": "Model ID",
        "model_example": "model-id-da-cap",
        "description": "API HTTPS tạo hiệu ứng âm thanh hoặc nhạc; Owner tự chọn model và endpoint.",
        "defaults": {"base_url": ""},
        "environment_defaults": {"base_url_env": "ELEVENLABS_BASE_URL", "api_key_env": "ELEVENLABS_API_KEY"},
        "local_probe": False, "cloud_probe": False,
    },
}


def _required_text(value, pattern, name):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ModelConfigError("Invalid " + name)
    return value


def _local_url(value):
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


def _cloud_url(value):
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


def validate_profile(value, *, profile_id=None, preview=False):
    """Return canonical allowlisted profile; secrets are never accepted."""
    if not isinstance(value, dict):
        raise ModelConfigError("Model profile must be an object")
    allowed = {
        "id", "provider", "model", "enabled", "base_url",
        "base_url_env", "api_key_env", "api_key_protected",
    }
    if value.get("provider") == "chatgpt":
        allowed.add("account_ref")
    if value.get("provider") == "comfyui":
        allowed.update(("flux", "motion_encoder"))
    if not value.keys() <= allowed:
        raise ModelConfigError("Unknown or sensitive model profile fields")
    ident = _required_text(value.get("id", profile_id), ID_RE, "model ID")
    if profile_id is not None and ident != profile_id:
        raise ModelConfigError("Profile ID mismatch")
    provider = value.get("provider")
    if not isinstance(provider, str) or provider not in ADAPTERS:
        raise ModelConfigError("Unsupported provider")
    model = _required_text(value.get("model"), MODEL_RE, "model/checkpoint name")
    enabled = value.get("enabled")
    if type(enabled) is not bool:
        raise ModelConfigError("Invalid enabled state")
    common = {"id": ident, "provider": provider, "model": model,
              "enabled": enabled}
    fields = value.keys() - common.keys()
    if provider == "chatgpt":
        if fields != {"account_ref"}:
            raise ModelConfigError("ChatGPT requires an account reference, not a key or URL")
        common["account_ref"] = _required_text(value["account_ref"], ID_RE, "ChatGPT account reference")
    elif ADAPTERS[provider]["connection"] == "local":
        if fields != {"base_url"} and not (
                provider == "comfyui" and fields in ({"base_url", "flux"}, {"base_url", "motion_encoder"})):
            raise ModelConfigError("Fields do not match the selected adapter")
        common["base_url"] = _local_url(value.get("base_url"))
        if "flux" in fields:
            common["flux"] = flux_workflow.validate(value["flux"], model, common["base_url"])
        if "motion_encoder" in fields:
            encoder = value["motion_encoder"]
            if (not isinstance(encoder, str) or not 1 <= len(encoder) <= 512
                    or not Path(encoder).is_absolute() or encoder.startswith(("\\\\", "//"))
                    or any(ord(char) < 32 for char in encoder)):
                raise ModelConfigError("Motion encoder must be a local absolute file path")
            common["motion_encoder"] = encoder
    elif preview and fields == {"base_url"}:
        common["base_url"] = _cloud_url(value["base_url"])
    elif fields == {"base_url", "api_key_protected"} and profile_id is not None:
        key = value["api_key_protected"]
        try:
            valid_key = isinstance(key, str) and len(key) <= 16384 and base64.b64decode(key, validate=True)
        except (ValueError, binascii.Error):
            valid_key = False
        if not valid_key:
            raise ModelConfigError("Invalid protected API key")
        common.update(base_url=_cloud_url(value["base_url"]), api_key_protected=key)
    elif fields == ADAPTERS[provider]["environment_defaults"].keys():
        for key in fields:
            common[key] = _required_text(value[key], ENV_NAME, "environment variable name")
    else:
        raise ModelConfigError("Fields do not match the selected Cloud credentials")
    if provider == "ltx_cloud" and "base_url" in common and common["base_url"] not in {"https://api.ltx.io", "https://api.ltx.io/v2"}:
        raise ModelConfigError("LTX video chỉ chấp nhận endpoint HTTPS chính thức.")
    return common


def _save_profile(value, api_key, profiles):
    if not isinstance(value, dict) or "api_key_protected" in value:
        raise ModelConfigError("Invalid model profile")
    if value.get("provider") not in {"anthropic", "openai", "elevenlabs", "ltx_cloud"} or "base_url" not in value:
        if api_key is not None:
            raise ModelConfigError("API key chỉ dùng với endpoint Cloud nhập trực tiếp")
        return validate_profile(value)
    ident = _required_text(value.get("id"), ID_RE, "model ID")
    endpoint = _cloud_url(value["base_url"])
    previous = profiles.get(ident, {})
    if api_key is None:
        if previous.get("base_url") != endpoint:
            raise ModelConfigError("Nhập API key khi thêm hoặc thay đổi endpoint Cloud")
        protected = previous.get("api_key_protected")
    else:
        if not isinstance(api_key, str) or not re.fullmatch(r"[!-~]{1,4096}", api_key):
            raise ModelConfigError("API key không hợp lệ")
        protected = cloud_credentials.protect_api_key(api_key)
    if not protected:
        raise ModelConfigError("Hãy nhập API key cho endpoint Cloud")
    return validate_profile({**value, "base_url": endpoint, "api_key_protected": protected},
                            profile_id=ident)


def route_catalog():
    """Source-defined capabilities, with NO model/profile defaults.

    Model assignment and override live only in Owner SQLite. This read never
    touches TOML, external endpoints or storage.
    """
    catalog = {}
    for key, label, kind, _ in orchestrator_policy.CAPABILITIES:
        if key not in ROUTE_CAPABILITIES:
            continue
        deterministic = key == "ops.monitor"
        catalog[key] = {
            "id": key,
            "label": label,
            "kind": "rules" if deterministic else kind,
            "execution": "rules" if deterministic else "config_only",
        }
    if set(catalog) != ROUTE_CAPABILITIES:
        raise ModelConfigError("Capability catalog does not match active routes")
    return catalog

def _empty():
    return {"profiles": {}, "routes": {}}


def _database(path=None):
    return Path(path) if path is not None else DB_PATH


def _read_record(conn):
    # A rejected first write may leave an empty SQLite container on disk.
    # Treat a genuinely uninitialized hub as empty without masking corruption.
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='hub_state'"
    ).fetchone()
    if not has_table:
        return 0, _empty()
    row = conn.execute(
        "SELECT revision, payload FROM hub_state WHERE id=1"
    ).fetchone()
    if row is None:
        return 0, _empty()
    try:
        record = json.loads(row[1])
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ModelConfigError("Model Hub state is corrupt") from exc
    _validate_state(record)
    return row[0], record


def _validate_state(doc):
    if not isinstance(doc, dict) or set(doc) not in (
            {"profiles", "routes"}, {"profiles", "routes", "orchestrator"}):
        raise ModelConfigError("Model Hub state has invalid schema")
    if (not isinstance(doc["profiles"], dict)
            or len(doc["profiles"]) > MAX_PROFILE_COUNT
            or not isinstance(doc["routes"], dict)
            or len(doc["routes"]) > 40):
        raise ModelConfigError("Model Hub exceeds bounded limits")
    for ident, profile in doc["profiles"].items():
        validate_profile(profile, profile_id=ident)
    routes = route_catalog()
    if "orchestrator" in doc:
        orchestrator_policy.validate(doc["orchestrator"])
    for key, ref in doc["routes"].items():
        _required_text(key, TASK_RE, "stored task key")
        _required_text(ref, ID_RE, "stored model ID")
        if key not in routes or routes[key]["kind"] == "rules":
            raise ModelConfigError("Unknown or deterministic stored route")
    if len(json.dumps(doc, ensure_ascii=False).encode("utf-8")) > MAX_STATE_BYTES:
        raise ModelConfigError("Model Hub state exceeds safe size")


def _read_state(*, db_path=None):
    path = _database(db_path)
    if not path.is_file():
        return 0, _empty()
    ensure_local_root(path)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as conn:
        return _read_record(conn)


def _profiles(*, state=None):
    """Owner profiles only: empty DB yields no configured model."""
    doc = state if state is not None else _read_state()[1]
    return {ident: dict(profile) for ident, profile in doc["profiles"].items()}


def effective_models(*, db_path=None):
    """Effective text-only profile snapshot for local runtime certification.

    This is a read-only lookup, never model inference or a cloud request.
    """
    state = _read_state(db_path=db_path)[1]
    return {key: {k: v for k, v in value.items() if k != "id"}
            for key, value in _profiles(state=state).items()
            if value["provider"] in {"ollama", "anthropic", "openai", "chatgpt"}}


def _active_policy(state):
    return orchestrator_policy.validate(state.get("orchestrator", orchestrator_policy.defaults()))


def _orchestrator_catalog(state, profiles, routes):
    policy = _active_policy(state)
    by_route = {row["id"]: row for row in routes}
    capabilities = []
    for key, label, kind, tool in orchestrator_policy.CAPABILITIES:
        route = by_route.get(key)
        ref = route["model_ref"] if route else None
        decision = orchestrator_policy.resolve(key, profiles, ref)
        options = [ident for ident, profile in profiles.items()
                   if orchestrator_policy.compatible(kind, profile)]
        capabilities.append({
            "id": key, "label": label, "kind": kind, "tool": tool,
            "adapter": ("COMFYUI_FLUX" if key == "image.generate" and "flux" in profiles.get(ref, {})
                        else "EXISTING_TOOL" if key in {"film.assemble", "ops.monitor"}
                        else "NONE"),
            "model_ref": ref, "options": sorted(options),
            "status": ("LOCAL_RUNTIME" if key == "image.generate"
                       and "flux" in profiles.get(decision.get("model_ref"), {}) else decision["status"]),
            "existing_route": route is not None and kind != "tool",
        })
    return {"policy": policy, "capabilities": capabilities,
            "status": "CONFIG_ONLY", "owner_override": "orchestrator" in state}


def catalog(*, db_path=None):
    revision, state = _read_state(db_path=db_path)
    return _catalog(revision, state)


def capability_contract(capability, profile):
    """Describe adapter compatibility independently of runtime observations."""
    kind = orchestrator_policy.KINDS.get(capability)
    adapter = orchestrator_policy.runtime_adapter(kind, profile)
    local = ADAPTERS[profile["provider"]]["connection"] == "local"
    output = None
    adapter_id = None
    workflow_sha = None
    if adapter and kind in {"text", "vision"}:
        adapter_id = profile["provider"] if kind == "text" else profile["provider"] + "_vision"
        output = {"format": "structured_json"}
        if kind == "vision":
            output["input"] = "jpeg_contact_sheet"
            output["max_image_bytes"] = adapter.MAX_SHEET_BYTES
    elif adapter and kind in {"sound", "music"}:
        adapter_id = "elevenlabs_" + kind
        output = {"format": "mp3", "max_input_chars": 180, "max_output_bytes": adapter.MAX_AUDIO_BYTES}
    elif adapter and kind == "audio":
        adapter_id = "openai_compatible_speech"
        output = {"format": "wav", "max_input_chars": 180, "max_output_bytes": adapter.MAX_WAV_BYTES}
    elif adapter and kind == "image":
        adapter_id = "comfyui_flux_gguf"
        graph = json.dumps(profile["flux"]["workflow"], sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
        workflow_sha = hashlib.sha256(graph).hexdigest()
        output = {"format": "png", "batch": 1, "min_resolution": 256,
                  "max_resolution": profile["flux"]["max_resolution"], "dimension_multiple": 16,
                  "min_steps": 1, "max_steps": profile["flux"]["max_steps"]}
    elif adapter and kind == "video":
        adapter_id = adapter.ADAPTER_ID
        workflow_sha = adapter.workflow_sha()
        spec = adapter.output_profile()
        output = {"format": "mp4", "fps": spec.fps, "max_frames": spec.max_frames,
                  "resolution": list(spec.resolution)}
    reason = None
    if kind not in {"text", "image", "video", "vision", "audio", "sound", "music"}:
        reason = "UNSUPPORTED_CAPABILITY"
    elif not adapter:
        reason = {"image": "FLUX_WORKFLOW_REQUIRED", "video": "MOTION_PROFILE_INCOMPATIBLE",
                  "text": "TEXT_ADAPTER_REQUIRED", "vision": "VISION_ADAPTER_UNAVAILABLE",
                  "audio": "AUDIO_ADAPTER_UNAVAILABLE", "sound": "AUDIO_ADAPTER_UNAVAILABLE",
                  "music": "AUDIO_ADAPTER_UNAVAILABLE"}[kind]
    return {"capability": capability,
            "route_configurable": orchestrator_policy.compatible(kind, profile),
            "runtime_compatible": adapter is not None, "local_runtime_compatible": local and adapter is not None,
            "adapter": adapter_id,
            "reason": reason, "output_limits": output, "workflow_sha256": workflow_sha,
            "configuration_status": "CONFIGURED", "readiness": "NOT_CHECKED"}


def preview_profile(profile, *, expected_revision, db_path=None):
    """Validate a draft configuration and derive its contracts without saving or probing."""
    revision, _ = _read_state(db_path=db_path)
    if type(expected_revision) is not int or revision != expected_revision:
        raise ModelConfigError("MODEL_HUB_REVISION_CONFLICT")
    if not isinstance(profile, dict) or "api_key_protected" in profile:
        raise ModelConfigError("Unknown or sensitive model profile fields")
    canonical = validate_profile(profile, preview=True)
    return {"revision": revision, "capability_contracts": [
        capability_contract(key, canonical) for key, kind in orchestrator_policy.KINDS.items()
        if kind != "tool"]}


def capability_readiness(profile_id, capability, *, expected_revision, db_path=None):
    """Check a single capability against one immutable Owner revision."""
    _required_text(profile_id, ID_RE, "model ID")
    _required_text(capability, TASK_RE, "capability")
    revision, state = _read_state(db_path=db_path)
    if type(expected_revision) is not int or revision != expected_revision:
        raise ModelConfigError("MODEL_HUB_REVISION_CONFLICT")
    profile = _profiles(state=state).get(profile_id)
    if not profile:
        raise ModelConfigError("Unknown model ID")
    contract = capability_contract(capability, profile)
    kind = orchestrator_policy.KINDS.get(capability)
    if not profile["enabled"]:
        observation = "DISABLED"
    elif not contract["runtime_compatible"]:
        observation = contract["reason"]
    elif kind in {"sound", "music"}:
        observation = "AUDIO_GENERATION_NOT_PROBED"
    elif profile["provider"] == "ltx_cloud":
        observation = "CLOUD_VIDEO_NOT_PROBED"
    elif kind in {"text", "vision", "audio"}:
        if profile["provider"] == "ollama":
            observation = _check_ollama(profile)["status"]
        elif profile["provider"] == "chatgpt":
            from agentforge.features.film_studio import studio_chatgpt
            observation = studio_chatgpt.readiness(profile)
        else:
            from agentforge.features.film_studio import studio_cloud
            observation = studio_cloud.readiness(profile)
    elif kind == "image":
        from agentforge.features.media.flux_runtime import readiness
        observation = readiness(profile["flux"], urlsplit(profile["base_url"]).port, inspect_all_nodes=True)
    else:
        observation = orchestrator_policy.local_adapter(kind, profile).registry_readiness(profile)
    status, available, metadata_compatible = _preflight_result(observation, contract)
    return {**contract, "profile_id": profile_id, "revision": revision, "configuration_valid": True,
            "enabled": profile["enabled"], "status": status, "readiness": status,
            "runtime_available": available, "endpoint_metadata_compatible": metadata_compatible,
            "reason": None if status == "METADATA_COMPATIBLE" else observation,
            "scope": "METADATA_ONLY", "inference_invoked": False, "inference_verified": False,
            "endpoint_ownership": "NOT_CHECKED",
            "checked_at": datetime.now(timezone.utc).isoformat()}


def _preflight_result(observation, contract):
    if observation in {"DISABLED", "AUDIO_GENERATION_NOT_PROBED", "CLOUD_VIDEO_NOT_PROBED"}:
        return "NOT_CHECKED", None, None
    if not contract["runtime_compatible"] or observation == "MOTION_ENDPOINT_MISMATCH":
        return "UNSUPPORTED", None, None
    if observation in {"READY", "LOCAL_MODEL_FOUND"}:
        return "METADATA_COMPATIBLE", True, True
    if observation in {"MOTION_LAUNCHER_REQUIRED", "MEDIA_TOOLS_UNAVAILABLE", "MOTION_WEIGHTS_UNAVAILABLE"}:
        return "MISSING_DEPENDENCY", True, True
    if observation in {"GPU_UNAVAILABLE", "MODEL_NOT_INSTALLED", "MODEL_UNAVAILABLE",
                       "WORKFLOW_NODE_UNAVAILABLE", "MOTION_WORKFLOW_UNAVAILABLE"}:
        return "MISSING_DEPENDENCY", True, False
    return "UNAVAILABLE", False, None


def image_runtime(*, automated=False, db_path=None):
    revision, state = _read_state(db_path=db_path)
    profiles = _profiles(state=state)
    policy = _active_policy(state)
    ref = state["routes"].get("image.generate")
    decision = orchestrator_policy.resolve("image.generate", profiles, ref)
    profile = profiles.get(decision.get("model_ref"))
    if not profile or "flux" not in profile:
        raise ModelConfigError("Assign an enabled FLUX profile to image.generate")
    permissions = policy["permissions"]
    if automated and (policy["mode"] == "MANUAL" or not (
            permissions["assign_models"] and permissions["call_local"])):
        raise PermissionError("Owner policy does not allow automated local image calls")
    return revision, profile


PLANNING_CAPABILITIES = ("general.text", "film.storyboard", "character.select")


def draft_routes(*, db_path=None, moving=None, planning=False, motion_ref=None, direct_cloud=False):
    """Resolve text-only planning or full production from one Owner policy snapshot."""
    revision, state = _read_state(db_path=db_path)
    return revision, _draft_bindings(state, moving=moving, planning=planning, motion_ref=motion_ref, direct_cloud=direct_cloud)


@contextmanager
def studio_dispatch(*, moving, validate, db_path=None, motion_ref=None, direct_cloud=False):
    """Serialize final Studio admission with registry changes, across processes.

    Acquire after GPU admission. The caller releases on POST return, before
    history polling, output import, or any next job.
    """
    path = ensure_local_root(_database(db_path))
    if not path.is_file():
        raise ModelConfigError("Chưa có cấu hình Model Hub để gửi tác vụ Studio.")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=5)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if getattr(exc, "sqlite_errorcode", None) not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise
            raise ModelConfigError("Model Hub đang cập nhật cấu hình. Hãy tiếp tục lại sau khi cập nhật xong.") from None
        try:
            revision, state = _read_record(conn)
            try:
                bindings = _draft_bindings(state, moving=moving, motion_ref=motion_ref, direct_cloud=direct_cloud)
            except PermissionError as exc:
                raise ModelConfigError(str(exc)) from None
            validate(revision, bindings)
            yield revision
        finally:
            conn.rollback()


def draft_routes_at(revision, *, db_path=None, moving=None):
    """Resolve a legacy approval from Model Hub history without writing SQLite."""
    path = _database(db_path)
    if not path.is_file():
        return None
    with closing(sqlite3.connect(ensure_local_root(path).resolve().as_uri() + "?mode=ro",
                                 uri=True, timeout=5)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hub_history'").fetchone():
            return None
        row = conn.execute("SELECT payload FROM hub_history WHERE revision=?", (revision,)).fetchone()
    if row is None:
        return None
    state = json.loads(row[0])
    _validate_state(state)
    return _draft_bindings(state, moving=moving)


def _draft_bindings(state, *, moving, planning=False, motion_ref=None, direct_cloud=False):
    policy = _active_policy(state)
    permissions = policy["permissions"]
    if (policy["mode"] == "MANUAL" or not all(permissions[key] for key in
            ("plan", "assign_models"))):
        raise PermissionError("Hãy bật lập kế hoạch và phân công model trong AI điều phối.")
    if not planning and (not permissions["run_tools"] or "ffmpeg" not in policy["tools"]):
        raise PermissionError("Hãy bật chạy công cụ local và FFmpeg trong AI điều phối.")
    profiles = _profiles(state=state)
    refs = state["routes"]
    bindings = {}
    capabilities = PLANNING_CAPABILITIES if planning else (*PLANNING_CAPABILITIES, "image.generate", "film.motion")
    for capability in capabilities:
        if (capability == "film.motion" and moving is False) or (capability == "image.generate" and direct_cloud):
            continue
        ref = motion_ref if capability == "film.motion" and motion_ref else refs.get(capability)
        if ref is None and (capability == "character.select" or (capability == "film.motion" and moving is None)):
            continue
        profile = profiles.get(ref)
        if ref is None:
            raise ModelConfigError(f"{capability}: chưa phân công model cho Studio.")
        if not profile or not profile["enabled"]:
            raise ModelConfigError(f"{capability}: hồ sơ {ref} đã bị xóa hoặc đang tắt.")
        permission = "call_cloud" if ADAPTERS[profile["provider"]]["connection"] == "cloud" else "call_local"
        if not permissions[permission]:
            raise PermissionError(f"{capability}: chưa cấp quyền {permission} trong AI điều phối.")
        if not orchestrator_policy.runtime_adapter(orchestrator_policy.KINDS[capability], profile):
            raise ModelConfigError(f"{capability}: hồ sơ {ref} không tương thích với adapter Studio.")
        if capability == "film.motion" and direct_cloud and profile["provider"] != "ltx_cloud":
            raise ModelConfigError("Cloud trực tiếp cần adapter cloud video.")
        bindings[capability] = profile
    return bindings


def _catalog(revision, state):
    profiles = _profiles(state=state)
    refs = state["routes"]
    routes = []
    for key, route in route_catalog().items():
        selected = (None if route["kind"] == "rules"
                    else refs.get(key))
        if route["kind"] == "rules":
            status = "DETERMINISTIC"
        elif not selected:
            status = "UNCONFIGURED"
        elif selected not in profiles or not profiles[selected]["enabled"]:
            status = "INVALID_CONFIG"
        elif not orchestrator_policy.compatible(route["kind"], profiles[selected]):
            status = "INCOMPATIBLE"
        else:
            status = "LOCAL_RUNTIME" if key == "image.generate" and "flux" in profiles[selected] else "CONFIG_ONLY"
        routes.append({**route, "model_ref": selected,
                        "source": ("owner" if key in refs else "system"),
                       "status": status,
                       })
    return {
        "revision": revision,
        "adapters": [{"id": key, **copy.deepcopy(adapter)} for key, adapter in ADAPTERS.items()],
        "profiles": [{"id": k, **{field: value for field, value in v.items()
                                 if field != "api_key_protected"},
            "has_api_key": "api_key_protected" in v, "source": (
            "owner"),
            "health": "UNVERIFIED",
            "runtime_supported": v["provider"] in {"ollama", "anthropic", "openai", "elevenlabs", "chatgpt", "ltx_cloud"} or "flux" in v
                or orchestrator_policy.local_adapter("video", v) is not None,
            "capability_contracts": [capability_contract(key, v) for key, kind in orchestrator_policy.KINDS.items()
                                     if kind != "tool"]}
            for k, v in sorted(profiles.items())],
        "routes": routes,
        "production_options": _production_options(state),
        "orchestrator": _orchestrator_catalog(state, profiles, routes),
        "cloud_fallback": False,
        "gpu_auto_start": False,
        "provider_billing_verified": False,
        "configuration_only_warning": "A configured route does not establish runtime readiness",
    }


def probe_cloud_profile(profile_id, *, expected_revision, db_path=None):
    """Explicit one-call structured inference probe; no project data sent."""
    from agentforge.features.film_studio import studio_cloud
    _required_text(profile_id, ID_RE, "model ID")
    revision, state = _read_state(db_path=db_path)
    if type(expected_revision) is not int or revision != expected_revision:
        raise ModelConfigError("MODEL_HUB_REVISION_CONFLICT")
    profile = _profiles(state=state).get(profile_id)
    if profile and profile["enabled"] and profile["provider"] == "chatgpt":
        from agentforge.features.film_studio import studio_chatgpt
        return {**studio_chatgpt.probe(profile), "model": profile["model"], "revision": revision,
                "checked_at": datetime.now(timezone.utc).isoformat()}
    if not profile or not profile["enabled"] or profile["provider"] not in studio_cloud.PROVIDERS:
        raise ModelConfigError("Probe requires an enabled cloud text profile")
    return {**studio_cloud.probe(profile), "model": profile["model"], "revision": revision,
            "checked_at": datetime.now(timezone.utc).isoformat()}


def audio_generation_binding(capability, *, db_path=None, optional=False):
    if capability not in {"film.sound", "film.music"}:
        raise ModelConfigError("Unknown generated audio capability")
    revision, state = _read_state(db_path=db_path)
    ref = state["routes"].get(capability)
    if ref is None and optional:
        return None
    profile = _profiles(state=state).get(ref)
    if not orchestrator_policy.compatible(orchestrator_policy.KINDS[capability], profile):
        raise ModelConfigError(capability + ": cần phân công model âm thanh tương thích.")
    policy = _active_policy(state)
    permissions = policy["permissions"]
    if (policy["mode"] == "MANUAL" or not all(permissions[key] for key in ("assign_models", "call_cloud", "run_tools"))
            or "ffmpeg" not in policy["tools"]):
        raise PermissionError("Sinh âm thanh cloud cần quyền cloud và FFmpeg.")
    return revision, profile, policy["cloud_call_limit"]


def speech_binding(*, db_path=None):
    revision, state = _read_state(db_path=db_path)
    profile = _profiles(state=state).get(state["routes"].get("film.tts"))
    if not orchestrator_policy.compatible("audio", profile):
        raise ModelConfigError("film.tts: hãy phân công model speech cloud tương thích.")
    policy = _active_policy(state)
    permissions = policy["permissions"]
    if (policy["mode"] == "MANUAL" or not all(permissions[key] for key in ("assign_models", "call_cloud", "run_tools"))
            or "ffmpeg" not in policy["tools"]):
        raise PermissionError("film.tts: cần cấp quyền cloud và FFmpeg.")
    return revision, profile, policy["cloud_call_limit"]


def vision_binding(*, db_path=None):
    """Read one explicitly assigned review profile and its execution permissions."""
    revision, state = _read_state(db_path=db_path)
    profile = _profiles(state=state).get(state["routes"].get("vision.qa"))
    if not orchestrator_policy.compatible("vision", profile):
        raise ModelConfigError("vision.qa: hãy phân công model có hỗ trợ hình ảnh trong AI điều phối.")
    policy = _active_policy(state)
    permissions = policy["permissions"]
    permission = "call_cloud" if profile["provider"] in {"openai", "anthropic", "chatgpt"} else "call_local"
    if (policy["mode"] == "MANUAL" or not permissions["assign_models"] or not permissions[permission]
            or not permissions["run_tools"] or "ffmpeg" not in policy["tools"]):
        raise PermissionError("vision.qa: cần cấp quyền model và công cụ FFmpeg trong AI điều phối.")
    return revision, profile, policy["cloud_call_limit"]


def cloud_call_limit(profile, *, moving, planning, validate, db_path=None, motion_ref=None, direct_cloud=False, allow_motion=False):
    """Check permission and pinned routes against one snapshot before each dispatch."""
    revision, state = _read_state(db_path=db_path)
    bindings = _draft_bindings(state, moving=moving, planning=planning, motion_ref=motion_ref, direct_cloud=direct_cloud)
    validate(revision, bindings)
    capabilities = (*PLANNING_CAPABILITIES, "film.motion") if allow_motion else PLANNING_CAPABILITIES
    if not any(bindings.get(key) == profile for key in capabilities):
        raise ModelConfigError("Hồ sơ cloud không khớp phân công.")
    return _active_policy(state)["cloud_call_limit"]


def probe_local_profile(profile_id, *, expected_revision, db_path=None):
    """Run an explicitly authorized fixed-prompt probe from one config snapshot."""
    from datetime import datetime, timezone
    from agentforge.ops import runtime_certification as runtime

    _required_text(profile_id, ID_RE, "model ID")
    revision, state = _read_state(db_path=db_path)
    if type(expected_revision) is not int or revision != expected_revision:
        raise ModelConfigError("MODEL_HUB_REVISION_CONFLICT")
    profile = _profiles(state=state).get(profile_id)
    if not profile or not profile["enabled"] or profile["provider"] != "ollama":
        raise ModelConfigError("Probe requires an enabled local Ollama profile")
    host, port = runtime._local_endpoint(profile["base_url"])
    name = profile["model"]
    result = runtime._safe_probe(
        lambda: runtime._ollama_inference(profile_id, profile=(host, port, name)))
    return {**result, "model": name, "revision": revision,
            "checked_at": datetime.now(timezone.utc).isoformat()}


def flux_probe_profile(profile_id, *, expected_revision, db_path=None):
    _required_text(profile_id, ID_RE, "model ID")
    revision, state = _read_state(db_path=db_path)
    if type(expected_revision) is not int or revision != expected_revision:
        raise ModelConfigError("MODEL_HUB_REVISION_CONFLICT")
    profile = _profiles(state=state).get(profile_id)
    if not profile or not profile["enabled"] or "flux" not in profile:
        raise ModelConfigError("Probe requires an enabled ComfyUI FLUX profile")
    return revision, profile


def check_local_profile(profile_id, *, db_path=None, opener=None):
    """Owner-invoked metadata preflight for supported loopback profiles."""
    _required_text(profile_id, ID_RE, "model ID")
    profile = _profiles(state=_read_state(db_path=db_path)[1]).get(profile_id)
    if not profile:
        raise ModelConfigError("Unknown model ID")
    if not profile["enabled"]:
        return {"profile_id": profile_id, "status": "DISABLED",
                "inference_invoked": False}
    if "flux" in profile:
        from agentforge.features.media.flux_runtime import readiness
        status = readiness(profile["flux"], urlsplit(profile["base_url"]).port)
        return {"profile_id": profile_id, "status": status, "checked_at": datetime.now(timezone.utc).isoformat(),
                "inference_invoked": False}
    if profile["provider"] != "ollama":
        return {"profile_id": profile_id, "status": "NOT_CHECKED",
                "reason": "Only local Ollama metadata preflight is supported",
                "inference_invoked": False}
    return _check_ollama(profile, opener=opener)


def _check_ollama(profile, *, opener=None):
    import urllib.error
    import urllib.request

    profile_id = profile["id"]
    url = _local_url(profile["base_url"]) + "/api/tags"
    request = urllib.request.Request(
        url, headers={"Accept": "application/json"}, method="GET")
    # A local server could redirect requests to the Internet, or environment
    # proxies could intercept even loopback URLs. Never follow redirects and
    # never route this Owner metadata probe through OS/environment proxies.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    safe_open = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()).open
    try:
        with (opener or safe_open)(request, timeout=3) as response:
            if response.status != 200:
                return {"profile_id": profile_id, "status": "HTTP_ERROR",
                        "inference_invoked": False}
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("Too many model metadata bytes")
        models = json.loads(raw).get("models")
        if not isinstance(models, list):
            raise ValueError("Invalid Ollama tags metadata")
        found = any(isinstance(item, dict) and
                    item.get("name") == profile["model"] for item in models)
        status = "LOCAL_MODEL_FOUND" if found else "MODEL_NOT_INSTALLED"
    except urllib.error.HTTPError:
        status = "HTTP_ERROR"
    except (TimeoutError, urllib.error.URLError, OSError):
        status = "UNAVAILABLE"
    except (ValueError, UnicodeError, TypeError, AttributeError):
        status = "INVALID_RESPONSE"
    return {"profile_id": profile_id, "status": status,
            "inference_invoked": False}


def _tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS hub_state(
        id INTEGER PRIMARY KEY CHECK(id = 1),
        revision INTEGER NOT NULL,
        payload TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS hub_history(
        revision INTEGER PRIMARY KEY,
        payload TEXT NOT NULL,
        action TEXT NOT NULL,
        at TEXT NOT NULL)""")


def change(action, *, expected_revision, db_path=None, profile=None, profile_id=None,
           task_id=None, model_ref=None, target_revision=None, policy=None,
           api_key=None, intent=None):
    """CAS-guarded Owner mutation; snapshot history supports explicit rollback."""
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected non-negative revision")
    if action not in {"SAVE_MODEL_PROFILE", "DELETE_MODEL_PROFILE",
                      "SET_MODEL_ROUTE", "RESET_MODEL_ROUTE", "ROLLBACK_MODEL_HUB",
                      "SAVE_ORCHESTRATOR", "RESET_ORCHESTRATOR"}:
        raise PermissionError("Unknown Model Hub action")
    path = _database(db_path)
    ensure_local_root(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # sqlite transaction is one serialization boundary across owner sessions.
    with closing(sqlite3.connect(path, timeout=5)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        _tables(conn)
        revision, current = _read_record(conn)
        if revision != expected_revision:
            raise ValueError("MODEL_HUB_REVISION_CONFLICT")
        updated = copy.deepcopy(current)
        if action == "SAVE_MODEL_PROFILE":
            if intent is not None:
                if intent not in ("create", "edit") or not isinstance(profile, dict):
                    raise ModelConfigError("Invalid profile save intent")
                ident = _required_text(profile.get("id"), ID_RE, "model ID")
                exists = ident in updated["profiles"]
                if intent == "create" and exists:
                    raise ModelConfigError("MODEL_HUB_PROFILE_ALREADY_EXISTS")
                if intent == "edit" and not exists:
                    raise ModelConfigError("MODEL_HUB_PROFILE_REMOVED")
            p = _save_profile(profile, api_key, updated["profiles"])
            # Explicit Owner upsert only; no Git-bundled model can reappear.
            if p["id"] not in updated["profiles"] and len(updated["profiles"]) >= MAX_PROFILE_COUNT:
                raise ModelConfigError("Model registry is full")
            updated["profiles"][p["id"]] = p
        elif action == "DELETE_MODEL_PROFILE":
            _required_text(profile_id, ID_RE, "model ID")
            if profile_id not in updated["profiles"]:
                raise ModelConfigError("Unknown model profile")
            attached = set(updated["routes"].values())
            if profile_id in attached:
                raise ModelConfigError("Model is assigned; unassign it before deleting")
            del updated["profiles"][profile_id]
        elif action in {"SET_MODEL_ROUTE", "RESET_MODEL_ROUTE"}:
            routes = route_catalog()
            if task_id not in routes or routes[task_id]["kind"] == "rules":
                raise ModelConfigError("Unknown or deterministic task")
            if action == "SET_MODEL_ROUTE":
                _required_text(model_ref, ID_RE, "model reference")
                profiles = _profiles(state=updated)
                if model_ref not in profiles or not profiles[model_ref]["enabled"]:
                    raise ModelConfigError("Model is missing or disabled")
                kind = routes[task_id]["kind"]
                if not orchestrator_policy.compatible(kind, profiles[model_ref]):
                    raise ModelConfigError("Selected model does not support task")
                updated["routes"][task_id] = model_ref
            else:
                updated["routes"].pop(task_id, None)
        elif action == "SAVE_ORCHESTRATOR":
            updated["orchestrator"] = orchestrator_policy.validate(policy)
        elif action == "RESET_ORCHESTRATOR":
            # Reset execution permissions, not model assignments.
            updated.pop("orchestrator", None)
        else:
            if (type(target_revision) is not int or target_revision < 0
                    or target_revision >= revision):
                raise ValueError("Invalid rollback revision")
            row = conn.execute(
                "SELECT payload FROM hub_history WHERE revision=?",
                (target_revision,)).fetchone()
            if row is None:
                raise ValueError("Rollback snapshot not available")
            updated = json.loads(row[0])
        _validate_state(updated)
        moment = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute("INSERT OR IGNORE INTO hub_history VALUES(?,?,?,?)",
                     (revision, json.dumps(current, ensure_ascii=False),
                      "SNAPSHOT", moment))
        next_revision = revision + 1
        payload = json.dumps(updated, ensure_ascii=False, sort_keys=True)
        conn.execute("""INSERT INTO hub_state(id,revision,payload)
            VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET
            revision=excluded.revision,payload=excluded.payload""",
                     (next_revision, payload))
        conn.execute("INSERT INTO hub_history VALUES(?,?,?,?)",
                     (next_revision, payload, action, moment))
        result = _catalog(next_revision, updated)
    return result


def production_candidates(strategy, *, db_path=None):
    """Planning candidates: compatible profiles, with separate execution-admission metadata."""
    if strategy not in {"auto", "local", "hybrid", "cloud"}:
        raise ModelConfigError("Unknown production strategy.")
    revision, state = _read_state(db_path=db_path)
    return revision, _production_candidates(state, strategy)


def _production_candidates(state, strategy):
    candidates = []
    for ident, profile in _profiles(state=state).items():
        if not orchestrator_policy.compatible("video", profile):
            continue
        methods = ("cloud", "hybrid") if profile["provider"] == "ltx_cloud" else ("local",)
        for method in methods:
            if strategy not in {"auto", method}:
                continue
            try:
                _draft_bindings(state, moving=True, motion_ref=ident, direct_cloud=method == "cloud")
            except (ValueError, PermissionError):
                execution_ready = False
            else:
                execution_ready = True
            adapter = orchestrator_policy.runtime_adapter("video", profile)
            item = {"id": ident, "method": method, "model": profile["model"],
                    "max_frames": adapter.output_profile().max_frames,
                    "fps": adapter.output_profile().fps, "min_billable_seconds": 0,
                    "execution_ready": execution_ready}
            if method != "local":
                from agentforge.features.film_studio.studio_ltx_cloud import DURATIONS
                item.update(billable_durations_seconds=list(DURATIONS), min_billable_seconds=min(DURATIONS))
            candidates.append(item)
    return candidates


def production_profile(profile_id, method, *, db_path=None):
    """Select a configured video profile for timeline planning, never for dispatch."""
    if method not in {"local", "hybrid", "cloud"}:
        raise ModelConfigError("Unknown production method.")
    _, state = _read_state(db_path=db_path)
    profile = _profiles(state=state).get(profile_id)
    if (not orchestrator_policy.compatible("video", profile)
            or (method == "local") != (profile["provider"] != "ltx_cloud")):
        raise ModelConfigError("Model video đã thay đổi khi lập kế hoạch.")
    return profile


def _production_options(state):
    """Read-only UI options from the same admission logic as the router."""
    from agentforge.features.film_studio import draft_timeline, production_router
    candidates = _production_candidates(state, "auto")
    by_method = {method: sum(c["method"] == method for c in candidates)
                 for method in ("local", "hybrid", "cloud")}
    ready = {method: any(c["method"] == method and c["execution_ready"] for c in candidates)
             for method in by_method}
    motion = state["profiles"].get(state["routes"].get("film.motion"), {})
    try:
        _draft_bindings(state, moving=True)
    except (ValueError, PermissionError):
        assigned_ready = False
    else:
        assigned_ready = motion.get("provider") != "ltx_cloud"
    assigned_cloud = motion.get("provider") == "ltx_cloud"
    return {"methods": [
        {"id": "assigned", "available": not assigned_cloud, "execution_ready": assigned_ready},
        {"id": "auto", "available": bool(candidates), "execution_ready": any(ready.values())},
        *({"id": method, "available": bool(count), "execution_ready": ready[method]} for method, count in by_method.items()),
    ], "duration_bounds": {"motion": draft_timeline.duration_bounds(True),
                            "still": draft_timeline.duration_bounds(False)},
        "min_cloud_seconds": production_router.MIN_CLOUD_SECONDS,
        "max_cloud_seconds": production_router.MAX_CLOUD_SECONDS,
        "auto_min_cloud_seconds": 0 if by_method["local"] else production_router.MIN_CLOUD_SECONDS}
