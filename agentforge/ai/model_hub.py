"""Versioned Owner Model Hub; no model invocation at configuration time.

Owner-added model profiles and route assignments have one source of truth:
versioned SQLite. The capability catalog stays in reviewed Python source.
No profiles or assignments are created by default; GET is read-only.
All model routes are configuration-only until an explicitly reviewed runtime
consumes their bindings. A saved cloud profile never authorizes a cloud call.
"""
from __future__ import annotations

import copy
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

from agentforge.ai import cloud_credentials, orchestrator_policy, registry
from agentforge.ai.profile_config import local_url, cloud_url
from agentforge.ai.registry import ADAPTERS
from agentforge.ai.orchestrator_policy import ModelConfigError
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




def is_cloud(profile):
    return ADAPTERS.get((profile or {}).get("provider"), {}).get("connection") == "cloud"


def _required_text(value, pattern, name):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ModelConfigError("Invalid " + name)
    return value


def validate_profile(value, *, profile_id=None, preview=False):
    """Return canonical allowlisted profile; secrets are never accepted."""
    if not isinstance(value, dict):
        raise ModelConfigError("Model profile must be an object")
    provider = value.get("provider")
    if not isinstance(provider, str) or provider not in ADAPTERS:
        raise ModelConfigError("Unsupported provider")
    descriptor = ADAPTERS[provider]
    options = registry.profile_options(provider)
    allowed = {"id", "provider", "model", "enabled", "base_url",
               "base_url_env", "api_key_env", "api_key_protected"}
    allowed.update(descriptor["defaults"])
    allowed.update(options.fields)
    if not value.keys() <= allowed:
        raise ModelConfigError("Unknown or sensitive model profile fields")
    ident = _required_text(value.get("id", profile_id), ID_RE, "model ID")
    if profile_id is not None and ident != profile_id:
        raise ModelConfigError("Profile ID mismatch")
    model = _required_text(value.get("model"), MODEL_RE, "model/checkpoint name")
    enabled = value.get("enabled")
    if type(enabled) is not bool:
        raise ModelConfigError("Invalid enabled state")
    common = {"id": ident, "provider": provider, "model": model,
              "enabled": enabled}
    fields = value.keys() - common.keys()
    extra = fields & options.fields
    if extra not in options.variants:
        raise ModelConfigError("Fields do not match the selected adapter")
    fields -= extra
    if "account_ref" in descriptor["defaults"]:
        if fields != {"account_ref"}:
            raise ModelConfigError("OAuth requires an account reference, not a key or URL")
        common["account_ref"] = _required_text(value["account_ref"], ID_RE, "account reference")
    elif descriptor["connection"] == "local":
        if fields != {"base_url"}:
            raise ModelConfigError("Fields do not match the selected adapter")
        common["base_url"] = local_url(value.get("base_url"))
    elif preview and fields == {"base_url"}:
        common["base_url"] = cloud_url(value["base_url"])
    elif fields == {"base_url", "api_key_protected"} and profile_id is not None:
        key = value["api_key_protected"]
        try:
            valid_key = isinstance(key, str) and len(key) <= 16384 and base64.b64decode(key, validate=True)
        except (ValueError, binascii.Error):
            valid_key = False
        if not valid_key:
            raise ModelConfigError("Invalid protected API key")
        common.update(base_url=cloud_url(value["base_url"]), api_key_protected=key)
    elif fields == descriptor.get("environment_defaults", {}).keys() and fields:
        for key in fields:
            common[key] = _required_text(value[key], ENV_NAME, "environment variable name")
    else:
        raise ModelConfigError("Fields do not match the selected Cloud credentials")
    common.update(options.validate(common, {key: value[key] for key in extra}))
    return common


def _save_profile(value, api_key, profiles):
    if not isinstance(value, dict) or "api_key_protected" in value:
        raise ModelConfigError("Invalid model profile")
    adapter = ADAPTERS.get(value.get("provider"), {})
    if adapter.get("connection") != "cloud" or "base_url" not in adapter.get("defaults", {}) or "base_url" not in value:
        if api_key is not None:
            raise ModelConfigError("API key chỉ dùng với endpoint Cloud nhập trực tiếp")
        return validate_profile(value)
    ident = _required_text(value.get("id"), ID_RE, "model ID")
    endpoint = cloud_url(value["base_url"])
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
            if orchestrator_policy.runtime_adapter("text", value) is not None}


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
            "adapter": ("EXISTING_TOOL" if kind == "tool" else
                        (capability_contract(key, profiles[ref])["adapter"] or "NONE") if ref in profiles else "NONE"),
            "model_ref": ref, "options": sorted(options),
            "status": ("LOCAL_RUNTIME" if key == "image.generate" and decision.get("model_ref") in profiles
                       and not is_cloud(profiles[decision["model_ref"]]) else decision["status"]),
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
    input_modes = None
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
        adapter_id = adapter.ADAPTER_ID
        workflow_sha = adapter.workflow_sha(profile)
        output = adapter.output_limits(profile)
    elif adapter and kind == "video":
        adapter_id = adapter.ADAPTER_ID
        workflow_sha = adapter.workflow_sha(profile)
        spec = adapter.output_profile(profile)
        input_modes = list(adapter.input_modes(profile))
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
            **({"input_modes": input_modes} if input_modes is not None else {}),
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
    else:
        adapter = registry.resolve(kind, profile)
        check = getattr(adapter, "registry_readiness", None) or getattr(adapter, "readiness", None)
        observation = check(profile) if check else "NOT_CHECKED"
    status, available, metadata_compatible = _preflight_result(observation, contract)
    return {**contract, "profile_id": profile_id, "revision": revision, "configuration_valid": True,
            "enabled": profile["enabled"], "status": status, "readiness": status,
            "runtime_available": available, "endpoint_metadata_compatible": metadata_compatible,
            "reason": None if status == "METADATA_COMPATIBLE" else observation,
            "scope": "METADATA_ONLY", "inference_invoked": False, "inference_verified": False,
            "endpoint_ownership": "NOT_CHECKED",
            "checked_at": datetime.now(timezone.utc).isoformat()}


def _preflight_result(observation, contract):
    if observation in {"DISABLED", "NOT_CHECKED", "AUDIO_GENERATION_NOT_PROBED", "CLOUD_VIDEO_NOT_PROBED", "CLOUD_IMAGE_NOT_PROBED"}:
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
    adapter = orchestrator_policy.runtime_adapter("image", profile)
    if not profile or is_cloud(profile) or not callable(getattr(adapter, "local_image_config", None)):
        raise ModelConfigError("Assign an enabled local image workflow to image.generate")
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
        permission = "call_cloud" if is_cloud(profile) else "call_local"
        if not permissions[permission]:
            raise PermissionError(f"{capability}: chưa cấp quyền {permission} trong AI điều phối.")
        adapter = orchestrator_policy.runtime_adapter(orchestrator_policy.KINDS[capability], profile)
        if not adapter:
            raise ModelConfigError(f"{capability}: hồ sơ {ref} không tương thích với adapter Studio.")
        if capability == "film.motion":
            if direct_cloud and not is_cloud(profile):
                raise ModelConfigError("Cloud trực tiếp cần adapter cloud video.")
            mode = "text-to-video" if direct_cloud else "image-to-video"
            if mode not in adapter.input_modes(profile):
                raise ModelConfigError(f"film.motion: adapter không hỗ trợ {mode}.")
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
            status = "LOCAL_RUNTIME" if key == "image.generate" and not is_cloud(profiles[selected]) else "CONFIG_ONLY"
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
            "runtime_supported": any(orchestrator_policy.runtime_adapter(kind, v) is not None
                                     for kind in set(orchestrator_policy.KINDS.values()) - {"tool"}),
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


def _probe_text(profile_id, *, expected_revision, connection, db_path=None):
    """Explicit fixed-prompt probe through the resolved text capability."""
    _required_text(profile_id, ID_RE, "model ID")
    revision, state = _read_state(db_path=db_path)
    if type(expected_revision) is not int or revision != expected_revision:
        raise ModelConfigError("MODEL_HUB_REVISION_CONFLICT")
    profile = _profiles(state=state).get(profile_id)
    adapter = orchestrator_policy.runtime_adapter("text", profile)
    if (not profile or not profile["enabled"] or
            ADAPTERS[profile["provider"]]["connection"] != connection or
            not callable(getattr(adapter, "probe", None))):
        raise ModelConfigError("Probe requires an enabled " + connection + " text profile")
    return {**adapter.probe(profile), "model": profile["model"], "revision": revision,
            "checked_at": datetime.now(timezone.utc).isoformat()}


def probe_cloud_profile(profile_id, *, expected_revision, db_path=None):
    return _probe_text(profile_id, expected_revision=expected_revision, connection="cloud", db_path=db_path)


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
    permission = "call_cloud" if is_cloud(profile) else "call_local"
    if (policy["mode"] == "MANUAL" or not permissions["assign_models"] or not permissions[permission]
            or not permissions["run_tools"] or "ffmpeg" not in policy["tools"]):
        raise PermissionError("vision.qa: cần cấp quyền model và công cụ FFmpeg trong AI điều phối.")
    return revision, profile, policy["cloud_call_limit"]


def cloud_call_limit(profile, *, moving, planning, validate, db_path=None, motion_ref=None, direct_cloud=False, allow_motion=False, allow_image=False):
    """Check permission and pinned routes against one snapshot before each dispatch."""
    revision, state = _read_state(db_path=db_path)
    bindings = _draft_bindings(state, moving=moving, planning=planning, motion_ref=motion_ref, direct_cloud=direct_cloud)
    validate(revision, bindings)
    capabilities = (*PLANNING_CAPABILITIES, *(("film.motion",) if allow_motion else ()),
                    *(("image.generate",) if allow_image else ()))
    if not is_cloud(profile) or not any(bindings.get(key) == profile for key in capabilities):
        raise ModelConfigError("Hồ sơ cloud không khớp phân công.")
    return _active_policy(state)["cloud_call_limit"]


def probe_local_profile(profile_id, *, expected_revision, db_path=None):
    return _probe_text(profile_id, expected_revision=expected_revision, connection="local", db_path=db_path)


def media_probe_profile(profile_id, *, expected_revision, db_path=None):
    _required_text(profile_id, ID_RE, "model ID")
    revision, state = _read_state(db_path=db_path)
    if type(expected_revision) is not int or revision != expected_revision:
        raise ModelConfigError("MODEL_HUB_REVISION_CONFLICT")
    profile = _profiles(state=state).get(profile_id)
    if not profile or not profile["enabled"] or not ADAPTERS[profile["provider"]].get("media_probe"):
        raise ModelConfigError("Probe requires an enabled cloud media profile")
    return profile


def flux_probe_profile(profile_id, *, expected_revision, db_path=None):
    _required_text(profile_id, ID_RE, "model ID")
    revision, state = _read_state(db_path=db_path)
    if type(expected_revision) is not int or revision != expected_revision:
        raise ModelConfigError("MODEL_HUB_REVISION_CONFLICT")
    profile = _profiles(state=state).get(profile_id)
    adapter = orchestrator_policy.runtime_adapter("image", profile)
    if (not profile or not profile["enabled"] or is_cloud(profile)
            or not callable(getattr(adapter, "local_image_config", None))):
        raise ModelConfigError("Probe requires an enabled local image workflow profile")
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
    if not is_cloud(profile):
        for kind in ("text", "image", "video"):
            adapter = orchestrator_policy.runtime_adapter(kind, profile)
            check = getattr(adapter, "check_metadata", None)
            if callable(check):
                return check(profile, opener=opener)
    return {"profile_id": profile_id, "status": "NOT_CHECKED",
            "reason": "No local metadata probe for this profile",
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


def _update_route(updated, task_id, model_ref):
    routes = route_catalog()
    if task_id not in routes or routes[task_id]["kind"] == "rules":
        raise ModelConfigError("Unknown or deterministic task")
    if model_ref is not None:
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


def change(action, *, expected_revision, db_path=None, profile=None, profile_id=None,
           task_id=None, model_ref=None, policy=None,
           api_key=None, intent=None, route_changes=None):
    """CAS-guarded Owner mutation; history verifies pinned Studio bindings."""
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected non-negative revision")
    if action not in {"SAVE_MODEL_PROFILE", "DELETE_MODEL_PROFILE",
                      "SET_MODEL_ROUTE", "RESET_MODEL_ROUTE",
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
            if action == "SET_MODEL_ROUTE":
                _required_text(model_ref, ID_RE, "model reference")
            _update_route(updated, task_id, model_ref if action == "SET_MODEL_ROUTE" else None)
        elif action == "SAVE_ORCHESTRATOR":
            updated["orchestrator"] = orchestrator_policy.validate(policy)
            if route_changes is not None:
                if not isinstance(route_changes, dict):
                    raise ModelConfigError("Invalid model assignments")
                for task, model in route_changes.items():
                    _update_route(updated, task, model)
        elif action == "RESET_ORCHESTRATOR":
            # Reset execution permissions, not model assignments.
            updated.pop("orchestrator", None)
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


def assigned_motion_profile(*, db_path=None):
    """Read the assigned video profile for planning only; no media admission or I/O."""
    _, state = _read_state(db_path=db_path)
    profile = _profiles(state=state).get(state["routes"].get("film.motion"))
    if orchestrator_policy.compatible("video", profile):
        return profile
    return None


def production_candidates(strategy, *, db_path=None):
    """Planning candidates: compatible profiles, with separate execution-admission metadata."""
    if strategy not in {"auto", "local", "hybrid", "cloud"}:
        raise ModelConfigError("Unknown production strategy.")
    revision, state = _read_state(db_path=db_path)
    return revision, _production_candidates(state, strategy)


def _video_methods(profile, adapter):
    modes = adapter.input_modes(profile)
    if is_cloud(profile):
        return tuple(method for method, mode in (("cloud", "text-to-video"), ("hybrid", "image-to-video"))
                     if mode in modes)
    # Local production currently implements I2V. Do not advertise unimplemented local T2V.
    return ("local",) if "image-to-video" in modes else ()


def _production_candidates(state, strategy):
    candidates = []
    for ident, profile in _profiles(state=state).items():
        if not orchestrator_policy.compatible("video", profile):
            continue
        adapter = orchestrator_policy.runtime_adapter("video", profile)
        for method in _video_methods(profile, adapter):
            if strategy not in {"auto", method}:
                continue
            try:
                _draft_bindings(state, moving=True, motion_ref=ident, direct_cloud=method == "cloud")
            except (ValueError, PermissionError):
                execution_ready = False
            else:
                execution_ready = True
            spec = adapter.output_profile(profile)
            item = {"id": ident, "method": method, "model": profile["model"],
                    "max_frames": spec.max_frames,
                    "fps": spec.fps, "min_billable_seconds": 0,
                    "input_modes": list(adapter.input_modes(profile)),
                    "execution_ready": execution_ready}
            if method != "local":
                durations = adapter.billable_durations(profile)
                item.update(billable_durations_seconds=list(durations), min_billable_seconds=min(durations),
                            native_audio=adapter.native_audio(profile))
            candidates.append(item)
    return candidates


def production_profile(profile_id, method, *, db_path=None):
    """Select a configured video profile for timeline planning, never for dispatch."""
    if method not in {"local", "hybrid", "cloud"}:
        raise ModelConfigError("Unknown production method.")
    _, state = _read_state(db_path=db_path)
    profile = _profiles(state=state).get(profile_id)
    if (not orchestrator_policy.compatible("video", profile)
            or method not in _video_methods(profile, orchestrator_policy.runtime_adapter("video", profile))):
        raise ModelConfigError("Model video đã thay đổi khi lập kế hoạch.")
    return profile


def _production_options(state):
    """Read-only UI options from the same admission logic as the router."""
    from agentforge.features.film_studio import draft_timeline, production_router
    from agentforge.features.film_studio.studio_contracts import BRIEF_LIMIT
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
        assigned_ready = not is_cloud(motion)
    assigned_cloud = is_cloud(motion)
    cloud_minimum = min((2 * c["min_billable_seconds"] for c in candidates if c["method"] != "local"),
                        default=production_router.MIN_CLOUD_SECONDS)
    return {"methods": [
        {"id": "assigned", "available": not assigned_cloud, "execution_ready": assigned_ready},
        {"id": "auto", "available": bool(candidates), "execution_ready": any(ready.values())},
        *({"id": method, "available": bool(count), "execution_ready": ready[method]} for method, count in by_method.items()),
    ], "brief_limit": BRIEF_LIMIT,
        "duration_bounds": {"motion": draft_timeline.duration_bounds(True),
                            "still": draft_timeline.duration_bounds(False)},
        "min_cloud_seconds": cloud_minimum,
        "max_cloud_seconds": production_router.MAX_CLOUD_SECONDS,
        "auto_min_cloud_seconds": 0 if by_method["local"] else cloud_minimum}
