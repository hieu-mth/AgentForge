"""Versioned, local-only Owner Model Hub; no model invocation at configuration time.

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
ROUTE_CAPABILITIES = frozenset({
    "general.text", "film.storyboard", "film.motion",
    "image.generate", "ops.monitor",
})
# Persisted Owner overlays for retired products are accepted read-only but
# excluded from active routes. Never rewrite the Owner's SQLite on GET.

ID_RE = re.compile(r"[a-z][a-z0-9_]{2,39}\Z")
TASK_RE = re.compile(r"[a-z][a-z0-9_.]{2,59}\Z")
MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}\Z")
KINDS = {"text", "image", "video", "rules"}
EXECUTIONS = {"config_only", "rules"}
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
        "model_example": "wan2.2_5b",
        "description": "Hồ sơ ảnh hoặc video. Đăng ký chỉ lưu cấu hình cho ComfyUI.",
        "defaults": {"base_url": "http://127.0.0.1:8188"}, "local_probe": False,
        "flux_workflow_max_bytes": flux_workflow.MAX_WORKFLOW_BYTES,
        "motion_encoder_supported": True,
    },
    "anthropic": {
        "label": "Anthropic-compatible", "connection": "cloud", "model_label": "Model ID",
        "model_example": "model-id-da-cap",
        "description": "Lưu cấu hình endpoint tương thích Anthropic. Dashboard chưa hỗ trợ chạy thử cloud.",
        "defaults": {"base_url": ""},
        "legacy_defaults": {"base_url_env": "ANTHROPIC_BASE_URL",
                            "api_key_env": "ANTHROPIC_AUTH_TOKEN"}, "local_probe": False,
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


def validate_profile(value, *, profile_id=None):
    """Return canonical allowlisted profile; secrets are never accepted."""
    if not isinstance(value, dict):
        raise ModelConfigError("Model profile must be an object")
    allowed = {
        "id", "provider", "model", "enabled", "base_url",
        "base_url_env", "api_key_env", "api_key_protected",
    }
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
    if ADAPTERS[provider]["connection"] == "local":
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
    elif fields == {"base_url", "api_key_protected"} and profile_id is not None:
        key = value["api_key_protected"]
        try:
            valid_key = isinstance(key, str) and len(key) <= 16384 and base64.b64decode(key, validate=True)
        except (ValueError, binascii.Error):
            valid_key = False
        if not valid_key:
            raise ModelConfigError("Invalid protected API key")
        common.update(base_url=_cloud_url(value["base_url"]), api_key_protected=key)
    elif fields == ADAPTERS[provider]["legacy_defaults"].keys():
        for key in fields:
            common[key] = _required_text(value[key], ENV_NAME, "environment variable name")
    else:
        raise ModelConfigError("Fields do not match the selected Cloud credentials")
    return common


def _save_profile(value, api_key, profiles):
    if not isinstance(value, dict) or "api_key_protected" in value:
        raise ModelConfigError("Invalid model profile")
    if value.get("provider") != "anthropic" or "base_url" not in value:
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
    # Unknown keys in older Owner SQLite are inert archival data, not routes.
    # Read safely without rewriting the Owner database during GET.
    defaults = route_catalog()
    if "orchestrator" in doc:
        orchestrator_policy.validate(
            doc["orchestrator"], id_pattern=ID_RE, extra_routes=_extra_capabilities(defaults))
    for key, ref in doc["routes"].items():
        _required_text(key, TASK_RE, "stored task key")
        _required_text(ref, ID_RE, "stored model ID")
        if key in defaults and defaults[key]["kind"] == "rules":
            raise ModelConfigError("Deterministic monitoring cannot use a model")
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
            if value["provider"] in {"ollama", "anthropic"}}


def _extra_capabilities(routes):
    return {key for key, kind in orchestrator_policy.KINDS.items()
            if key not in routes and kind != "tool"}


def _orchestrator_catalog(state, profiles, routes):
    policy = {**orchestrator_policy.defaults(), **state.get("orchestrator", {})}
    by_route = {row["id"]: row for row in routes}
    capabilities = []
    for key, label, kind, tool in orchestrator_policy.CAPABILITIES:
        route = by_route.get(key)
        ref = route["model_ref"] if route else policy["mappings"].get(key)
        decision = orchestrator_policy.resolve(key, policy, profiles, ref)
        options = [ident for ident, profile in profiles.items()
                   if orchestrator_policy.compatible(kind, profile)]
        capabilities.append({
            "id": key, "label": label, "kind": kind, "tool": tool,
            "adapter": ("COMFYUI_FLUX" if key == "image.generate" and "flux" in profiles.get(ref, {})
                        else "EXISTING_TOOL" if key in {"film.tts", "film.assemble", "ops.monitor"}
                        else "NONE"),
            "model_ref": ref, "options": sorted(options),
            "status": ("LOCAL_RUNTIME" if key == "image.generate"
                       and "flux" in profiles.get(decision.get("model_ref"), {}) else decision["status"]),
            "existing_route": route is not None and kind != "tool",
            "default_ref": None,
        })
    return {"policy": policy, "capabilities": capabilities,
            "status": "CONFIG_ONLY", "owner_override": "orchestrator" in state}


def catalog(*, db_path=None):
    revision, state = _read_state(db_path=db_path)
    return _catalog(revision, state)


def capability_contract(capability, profile):
    """Describe adapter compatibility independently of runtime observations."""
    kind = orchestrator_policy.KINDS.get(capability)
    adapter = orchestrator_policy.local_adapter(kind, profile)
    output = None
    adapter_id = None
    workflow_sha = None
    if adapter and kind == "text":
        adapter_id = "ollama"
        output = {"format": "structured_json"}
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
    if kind not in {"text", "image", "video", "vision"}:
        reason = "UNSUPPORTED_CAPABILITY"
    elif kind == "text" and profile["provider"] == "anthropic":
        reason = "CLOUD_PREFLIGHT_UNSUPPORTED"
    elif not adapter:
        reason = {"image": "FLUX_WORKFLOW_REQUIRED", "video": "MOTION_PROFILE_INCOMPATIBLE",
                  "text": "LOCAL_TEXT_ADAPTER_REQUIRED", "vision": "VISION_ADAPTER_UNAVAILABLE"}[kind]
    return {"capability": capability,
            "route_configurable": orchestrator_policy.compatible(kind, profile),
            "local_runtime_compatible": adapter is not None, "adapter": adapter_id,
            "reason": reason, "output_limits": output, "workflow_sha256": workflow_sha,
            "configuration_status": "CONFIGURED", "readiness": "NOT_CHECKED"}


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
    elif not contract["local_runtime_compatible"]:
        observation = contract["reason"]
    elif kind == "text":
        observation = _check_ollama(profile)["status"]
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
    if observation in {"DISABLED", "CLOUD_PREFLIGHT_UNSUPPORTED"}:
        return "NOT_CHECKED", None, None
    if not contract["local_runtime_compatible"] or observation == "MOTION_ENDPOINT_MISMATCH":
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
    policy = state.get("orchestrator", orchestrator_policy.defaults())
    ref = state["routes"].get("image.generate")
    decision = orchestrator_policy.resolve("image.generate", policy, profiles, ref)
    profile = profiles.get(decision.get("model_ref"))
    if not profile or "flux" not in profile:
        raise ModelConfigError("Assign an enabled FLUX profile to image.generate")
    permissions = policy["permissions"]
    if automated and (policy["mode"] == "MANUAL" or not (
            permissions["assign_local"] and permissions["call_local"])):
        raise PermissionError("Owner policy does not allow automated local image calls")
    return revision, profile


def draft_routes(*, db_path=None):
    """Resolve local production capabilities from one Owner policy snapshot."""
    from agentforge.features.film_studio import studio_runtime

    revision, state = _read_state(db_path=db_path)
    policy = state.get("orchestrator", orchestrator_policy.defaults())
    permissions = policy["permissions"]
    if (policy["mode"] == "MANUAL" or not all(permissions[key] for key in
            ("plan", "assign_local", "call_local", "run_tools")) or "ffmpeg" not in policy["tools"]):
        raise PermissionError("Enable local planning, assignment, model calls and FFmpeg in AI Orchestrator")
    profiles = _profiles(state=state)
    bindings = {}
    for capability in ("general.text", "film.storyboard", "character.select", "image.generate", "film.motion"):
        ref = state["routes"].get(capability, policy["mappings"].get(capability))
        decision = orchestrator_policy.resolve(capability, policy, profiles, ref)
        profile = profiles.get(decision.get("model_ref"))
        if profile:
            bindings[capability] = profile
    for capability, resolve in (("general.text", studio_runtime.text_adapter),
                                ("film.storyboard", studio_runtime.text_adapter),
                                ("image.generate", studio_runtime.image_adapter)):
        try:
            resolve(bindings.get(capability))
        except ValueError as exc:
            raise ModelConfigError(f"{capability}: {exc}") from None
    return revision, bindings


def _catalog(revision, state):
    profiles = _profiles(state=state)
    routes = []
    for key, route in route_catalog().items():
        selected = (None if route["kind"] == "rules"
                    else state["routes"].get(key))
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
                        "source": ("owner" if key in state["routes"] else "system"),
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
            "runtime_supported": v["provider"] in {"ollama", "anthropic"} or "flux" in v
                or orchestrator_policy.local_adapter("video", v) is not None,
            "capability_contracts": [capability_contract(key, v) for key, kind in orchestrator_policy.KINDS.items()
                                     if kind != "tool"]}
            for k, v in sorted(profiles.items())],
        "routes": routes,
        "orchestrator": _orchestrator_catalog(state, profiles, routes),
        "cloud_fallback": False,
        "gpu_auto_start": False,
        "provider_billing_verified": False,
        "configuration_only_warning": "A configured route does not establish local runtime readiness",
    }


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


def _save_orchestrator(updated, policy, route_changes):
    routes = route_catalog()
    policy = orchestrator_policy.validate(
        policy, id_pattern=ID_RE, extra_routes=_extra_capabilities(routes))
    editable = {key for key in routes if orchestrator_policy.KINDS.get(key)
                in {"text", "image", "video"}}
    if not isinstance(route_changes, dict) or not route_changes.keys() <= editable:
        raise ModelConfigError("Danh sách tuyến điều phối không hợp lệ")
    profiles = _profiles(state=updated)

    def validate_ref(ref, kind, *, local=False):
        if not isinstance(ref, str) or not ID_RE.fullmatch(ref):
            raise ModelConfigError("Mã model không hợp lệ")
        profile = profiles.get(ref)
        if not orchestrator_policy.compatible(kind, profile):
            raise ModelConfigError("Model không khả dụng hoặc không tương thích")
        if local and profile["provider"] != "ollama":
            raise ModelConfigError("Model dự phòng phải là Ollama local")

    if policy["primary"] is not None:
        validate_ref(policy["primary"], "text")
    for ref in policy["allowed_profiles"]:
        if not profiles.get(ref, {}).get("enabled"):
            raise ModelConfigError("Danh sách đề xuất chứa model không khả dụng")
    for key, ref in policy["mappings"].items():
        validate_ref(ref, orchestrator_policy.KINDS[key])
    for key, ref in policy["fallbacks"].items():
        validate_ref(ref, "text", local=True)
        primary = route_changes.get(key, updated["routes"].get(key))
        if ref == primary:
            raise ModelConfigError("Model dự phòng phải khác model chính")
    for key, ref in route_changes.items():
        if ref is None:
            updated["routes"].pop(key, None)
        else:
            validate_ref(ref, routes[key]["kind"])
            updated["routes"][key] = ref
    updated["orchestrator"] = policy


def change(action, *, expected_revision, db_path=None, profile=None, profile_id=None,
           task_id=None, model_ref=None, target_revision=None, policy=None, route_changes=None,
           api_key=None):
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
            p = _save_profile(profile, api_key, updated["profiles"])
            # Explicit Owner upsert only; no Git-bundled model can reappear.
            if p["id"] not in updated["profiles"] and len(updated["profiles"]) >= MAX_PROFILE_COUNT:
                raise ModelConfigError("Model registry is full")
            updated["profiles"][p["id"]] = p
        elif action == "DELETE_MODEL_PROFILE":
            _required_text(profile_id, ID_RE, "model ID")
            if profile_id not in updated["profiles"]:
                raise ModelConfigError("Unknown model profile")
            attached = {ref for key, ref in updated["routes"].items()
                        if key in route_catalog()}
            current_policy = updated.get("orchestrator", orchestrator_policy.defaults())
            attached.update([current_policy["primary"]])
            attached.update(current_policy["allowed_profiles"])
            attached.update(current_policy["mappings"].values())
            attached.update(current_policy["fallbacks"].values())
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
            _save_orchestrator(updated, policy, route_changes)
        elif action == "RESET_ORCHESTRATOR":
            updated.pop("orchestrator", None)
            for key in route_catalog():
                if orchestrator_policy.KINDS.get(key) in {"text", "image", "video"}:
                    updated["routes"].pop(key, None)
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
