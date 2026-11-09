"""Versioned, local-only Owner Model Hub; no model invocation at configuration time.

Git-owned models.toml and task_routes.toml are defaults. Dashboard writes an
audited SQLite overlay, never TOML, API credentials or generated workflows.
Only text routes marked "wired" affect the existing LLM runtime. Media routes
are intentionally configuration-only until their adapters consume the routing
contract. Any new cloud provider use still needs explicit run-time consent.
"""
from __future__ import annotations

import copy
from contextlib import closing
import json
import re
import sqlite3
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from agentforge.ai.model_registry import (
    DEFAULT_CONFIG, ENV_NAME, ModelConfigError, load_models,
)
from agentforge.ai.worker_registry import load_worker
from agentforge.paths import COMPANY_DATA_DIR, CONFIG_DIR, ensure_local_root

DB_PATH = COMPANY_DATA_DIR / "model_hub.sqlite3"
ROUTES_FILE = CONFIG_DIR / "task_routes.toml"
ID_RE = re.compile(r"[a-z][a-z0-9_]{2,39}\Z")
TASK_RE = re.compile(r"[a-z][a-z0-9_.]{2,59}\Z")
MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}\Z")
KINDS = {"text", "image", "video", "rules"}
EXECUTIONS = {"wired", "config_only", "rules"}
MAX_PROFILE_COUNT = 32
MAX_STATE_BYTES = 65536


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


def validate_profile(value, *, profile_id=None):
    """Return canonical allowlisted profile; secrets are never accepted."""
    if not isinstance(value, dict):
        raise ModelConfigError("Model profile must be an object")
    if len(value) > 6 or not set(value).issubset({
        "id", "provider", "model", "enabled", "base_url",
        "base_url_env", "api_key_env",
    }):
        raise ModelConfigError("Unknown or sensitive model profile fields")
    ident = _required_text(value.get("id", profile_id), ID_RE, "model ID")
    if profile_id is not None and ident != profile_id:
        raise ModelConfigError("Profile ID mismatch")
    provider = value.get("provider")
    if provider not in {"ollama", "anthropic", "comfyui"}:
        raise ModelConfigError("Unsupported provider")
    model = _required_text(value.get("model"), MODEL_RE, "model/checkpoint name")
    enabled = value.get("enabled")
    if type(enabled) is not bool:
        raise ModelConfigError("Invalid enabled state")
    common = {"id": ident, "provider": provider, "model": model,
              "enabled": enabled}
    if provider in {"ollama", "comfyui"}:
        if set(value) - {"id", "provider", "model", "enabled", "base_url"}:
            raise ModelConfigError("Local provider accepts only a loopback URL")
        common["base_url"] = _local_url(value.get("base_url"))
    else:
        if set(value) - {"id", "provider", "model", "enabled",
                         "base_url_env", "api_key_env"}:
            raise ModelConfigError("Cloud provider accepts only env names")
        for key in ("base_url_env", "api_key_env"):
            env = value.get(key)
            if not isinstance(env, str) or not ENV_NAME.fullmatch(env):
                raise ModelConfigError("Cloud credentials must use env references")
            common[key] = env
    return common


def _defaults():
    """Read reviewed task keys; worker default model stays in worker.toml."""
    try:
        raw = tomllib.loads(ROUTES_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ModelConfigError("Cannot load default routing") from exc
    if set(raw) != {"routes"} or not isinstance(raw["routes"], dict):
        raise ModelConfigError("Invalid default routes")
    routes = {}
    wired_workers = set()
    for key, value in raw["routes"].items():
        _required_text(key, TASK_RE, "task key")
        if (not isinstance(value, dict) or
                not set(value).issubset({"label", "kind", "execution",
                                          "worker", "default_model"})):
            raise ModelConfigError("Invalid route config")
        label = value.get("label")
        kind = value.get("kind")
        execution = value.get("execution")
        worker = value.get("worker")
        if not isinstance(label, str) or not 1 <= len(label) <= 90:
            raise ModelConfigError("Route label is missing")
        if kind not in KINDS or execution not in EXECUTIONS:
            raise ModelConfigError("Invalid route kind")
        if (execution == "rules") != (kind == "rules"):
            raise ModelConfigError("Rules must be deterministic")
        if execution == "wired" and kind != "text":
            raise ModelConfigError("Non-text adapters are not wired yet")
        if worker is not None:
            _required_text(worker, ID_RE, "worker ID")
            if execution != "wired" or worker in wired_workers:
                raise ModelConfigError("Worker can have only one active route")
            wired_workers.add(worker)
        default_model = value.get("default_model")
        if worker is not None:
            if default_model is not None:
                raise ModelConfigError("Worker model belongs in worker.toml")
            default_model = load_worker(worker)["model_ref"]
        if default_model is not None:
            _required_text(default_model, ID_RE, "default model reference")
        if execution == "wired" and not default_model:
            raise ModelConfigError("Wired route needs a default model")
        routes[key] = {"id": key, "label": label, "kind": kind,
                       "execution": execution, "worker": worker,
                       "default_model": default_model}
    return routes


def _empty():
    return {"profiles": {}, "routes": {}}


def _database(path=None):
    return Path(path) if path is not None else DB_PATH


def _read_record(conn):
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
    if not isinstance(doc, dict) or set(doc) != {"profiles", "routes"}:
        raise ModelConfigError("Model Hub state has invalid schema")
    if (not isinstance(doc["profiles"], dict)
            or len(doc["profiles"]) > MAX_PROFILE_COUNT
            or not isinstance(doc["routes"], dict)
            or len(doc["routes"]) > 40):
        raise ModelConfigError("Model Hub exceeds bounded limits")
    for ident, profile in doc["profiles"].items():
        validate_profile(profile, profile_id=ident)
    defaults = _defaults()
    for key, ref in doc["routes"].items():
        if key not in defaults:
            raise ModelConfigError("Unknown task route")
        if defaults[key]["kind"] == "rules":
            raise ModelConfigError("Deterministic monitoring cannot use a model")
        _required_text(ref, ID_RE, "routed model ID")
    if len(json.dumps(doc, ensure_ascii=False).encode("utf-8")) > MAX_STATE_BYTES:
        raise ModelConfigError("Model Hub state exceeds safe size")


def _read_state(*, db_path=None):
    path = _database(db_path)
    if not path.is_file():
        return 0, _empty()
    ensure_local_root(path)
    with closing(sqlite3.connect(path, timeout=5)) as conn:
        return _read_record(conn)


def _profiles(*, state=None):
    # Always use explicit default-config path, never recursively load an overlay.
    baseline = load_models(DEFAULT_CONFIG)
    merged = {name: {"id": name, **item}
              for name, item in baseline.items()}
    doc = state if state is not None else _read_state()[1]
    for ident, profile in doc["profiles"].items():
        if ident in merged and profile["provider"] != merged[ident]["provider"]:
            raise ModelConfigError("Cannot change the provider of a built-in model")
        merged[ident] = dict(profile)
    return merged


def effective_models(*, db_path=None):
    """Only text providers returned to agentforge.model; no ComfyUI execution."""
    state = _read_state(db_path=db_path)[1]
    return {key: {k: v for k, v in value.items() if k != "id"}
            for key, value in _profiles(state=state).items()
            if value["provider"] in {"ollama", "anthropic"}}


def model_for_worker(worker_id, fallback, *, db_path=None):
    """Return (model_ref, revision, changed_by_owner); no network or fallback."""
    revision, state = _read_state(db_path=db_path)
    for key, config in _defaults().items():
        if config["execution"] == "wired" and config["worker"] == worker_id:
            return state["routes"].get(key, config["default_model"]), revision, (
                key in state["routes"])
    if worker_id is None:
        return state["routes"].get("general.text", fallback), revision, (
            "general.text" in state["routes"])
    return fallback, revision, False


def catalog(*, db_path=None):
    revision, state = _read_state(db_path=db_path)
    profiles = _profiles(state=state)
    routes = []
    for key, route in _defaults().items():
        selected = state["routes"].get(key, route["default_model"])
        if route["kind"] == "rules":
            status = "DETERMINISTIC"
        elif not selected:
            status = "UNCONFIGURED"
        elif selected not in profiles or not profiles[selected]["enabled"]:
            status = "INVALID_CONFIG"
        elif (route["kind"] == "text") != (
                profiles[selected]["provider"] in {"ollama", "anthropic"}):
            status = "INCOMPATIBLE"
        elif route["kind"] in {"video", "image"} and (
                profiles[selected]["provider"] != "comfyui"):
            status = "INCOMPATIBLE"
        else:
            status = "ROUTED" if route["execution"] == "wired" else "CONFIG_ONLY"
        routes.append({**route, "model_ref": selected,
                       "source": "owner" if key in state["routes"] else "default",
                       "status": status,
                       "runtime_wired": route["execution"] == "wired"})
    return {
        "revision": revision,
        "profiles": [{"id": k, **v, "source": (
            "owner" if k in state["profiles"] else "git"),
            "health": "UNVERIFIED",
            "runtime_supported": v["provider"] in {"ollama", "anthropic"}}
            for k, v in sorted(profiles.items())],
        "routes": routes,
        "cloud_fallback": False,
        "gpu_auto_start": False,
        "provider_billing_verified": False,
        "configuration_only_warning": "Video/image routing is not wired to inference",
    }


def check_local_profile(profile_id, *, db_path=None, opener=None):
    """Owner-invoked, bounded GET to a loopback Ollama tags endpoint ONLY.

    Cloud providers and ComfyUI video checkpoints are not probed by this
    endpoint. No generation, model download, GPU run or billing is triggered.
    """
    import urllib.error
    import urllib.request

    _required_text(profile_id, ID_RE, "model ID")
    profile = _profiles(state=_read_state(db_path=db_path)[1]).get(profile_id)
    if not profile:
        raise ModelConfigError("Unknown model ID")
    if not profile["enabled"]:
        return {"profile_id": profile_id, "status": "DISABLED",
                "inference_invoked": False}
    if profile["provider"] != "ollama":
        return {"profile_id": profile_id, "status": "NOT_CHECKED",
                "reason": "Only local Ollama metadata preflight is supported",
                "inference_invoked": False}
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


def change(action, *, expected_revision, db_path=None, profile=None,
           task_id=None, model_ref=None, target_revision=None):
    """CAS-guarded Owner mutation; snapshot history supports explicit rollback."""
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Expected non-negative revision")
    if action not in {"SAVE_MODEL_PROFILE", "SET_MODEL_ROUTE",
                      "RESET_MODEL_ROUTE", "ROLLBACK_MODEL_HUB"}:
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
            p = validate_profile(profile)
            baseline = load_models(DEFAULT_CONFIG)
            if p["id"] in baseline and p["provider"] != baseline[p["id"]]["provider"]:
                raise ModelConfigError("Cannot change built-in model provider")
            updated["profiles"][p["id"]] = p
        elif action in {"SET_MODEL_ROUTE", "RESET_MODEL_ROUTE"}:
            routes = _defaults()
            if task_id not in routes or routes[task_id]["kind"] == "rules":
                raise ModelConfigError("Unknown or deterministic task")
            if action == "SET_MODEL_ROUTE":
                _required_text(model_ref, ID_RE, "model reference")
                profiles = _profiles(state=updated)
                if model_ref not in profiles or not profiles[model_ref]["enabled"]:
                    raise ModelConfigError("Model is missing or disabled")
                kind = routes[task_id]["kind"]
                provider = profiles[model_ref]["provider"]
                if ((kind == "text" and provider not in {"ollama", "anthropic"})
                        or (kind in {"video", "image"} and provider != "comfyui")):
                    raise ModelConfigError("Selected model does not support task")
                updated["routes"][task_id] = model_ref
            else:
                updated["routes"].pop(task_id, None)
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
        # Reject edits that disable a model still used by a wired route.
        view = _profiles(state=updated)
        for key, route in _defaults().items():
            if route["execution"] == "wired":
                selected = updated["routes"].get(key, route["default_model"])
                if (selected not in view or not view[selected]["enabled"] or
                        view[selected]["provider"] not in {"ollama", "anthropic"}):
                    raise ModelConfigError("A wired task would lose its text model")
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
    return catalog(db_path=db_path)
