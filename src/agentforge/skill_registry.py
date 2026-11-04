"""S1.1: declarative Skill Contract and Registry (discovery only).

No manifest can import Python, run a model, open a browser, spend money,
grant permissions, or execute tools. Invocation and policy enforcement belong
to later milestones. Only a small documented schema subset is supported.
"""
import argparse
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_ID_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z")
WORKER_ID_RE = re.compile(r"[a-z][a-z0-9_]{2,63}\Z")
FIELD_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
MANIFEST_FIELDS = {
    "schema_version", "id", "version", "description", "worker_id",
    "execution_mode", "required_permissions", "required_tools",
    "artifact_types", "quality_checks", "limits", "input_schema",
    "output_schema",
}
SCHEMA_FIELDS = {"type", "properties", "required", "additional_properties"}
LIMIT_FIELDS = {"timeout_seconds", "estimated_model_calls"}
MODES = {"read_only", "owner_gated"}
PERMISSIONS = {
    "workspace.read", "workspace.propose", "workspace.write",
    "model.invoke", "network.search", "network.read", "browser.run",
    "process.run",
}
TOOLS = {"filesystem", "model", "search", "https_reader", "browser",
         "raster", "audio", "ffmpeg", "tts_engine", "sqlite"}
FIELD_TYPES = {"string", "integer", "number", "boolean", "array", "object"}
MAX_MANIFEST_BYTES = 12_000


class SkillConfigError(ValueError):
    """Invalid or unsupported skill contract; fail closed."""


def _safe_path(path):
    # Junctions are important on Windows; refuse symlink/junction paths.
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise SkillConfigError("Symlink or junction skill path is forbidden")


def _skill_id(value):
    if not isinstance(value, str) or not SKILL_ID_RE.fullmatch(value):
        raise SkillConfigError("Invalid skill ID")
    return value


def _names(value, field, *, options=None, pattern=FIELD_RE, allow_empty=False):
    if (not isinstance(value, list) or (not value and not allow_empty)
            or len(value) > 20 or any(not isinstance(v, str) for v in value)
            or len(set(value)) != len(value)):
        raise SkillConfigError(f"Invalid {field}")
    for name in value:
        if not pattern.fullmatch(name) or (options is not None and name not in options):
            raise SkillConfigError(f"Unsupported {field}: {name}")
    return value


def _schema(raw, label):
    if not isinstance(raw, dict) or set(raw) != SCHEMA_FIELDS:
        raise SkillConfigError(f"Invalid {label} fields")
    if raw["type"] != "object" or type(raw["additional_properties"]) is not bool:
        raise SkillConfigError(f"{label} must describe an object")
    props = raw["properties"]
    if not isinstance(props, dict) or not 1 <= len(props) <= 20:
        raise SkillConfigError(f"Invalid {label} properties")
    for name, kind in props.items():
        if (not isinstance(name, str) or not FIELD_RE.fullmatch(name)
                or not isinstance(kind, str) or kind not in FIELD_TYPES):
            raise SkillConfigError(f"Unsupported {label} property: {name}")
    required = _names(raw["required"], f"{label}.required", allow_empty=True)
    if not set(required).issubset(props):
        raise SkillConfigError(f"{label} required fields must be defined")
    return raw


def _contract(data, requested_id):
    if not isinstance(data, dict) or set(data) != MANIFEST_FIELDS:
        raise SkillConfigError("Missing or unauthorized skill manifest fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise SkillConfigError("Unsupported skill contract version")
    if _skill_id(data["id"]) != requested_id:
        raise SkillConfigError("Skill ID does not match directory")
    if not isinstance(data["version"], str) or not VERSION_RE.fullmatch(data["version"]):
        raise SkillConfigError("Invalid skill semantic version")
    desc = data["description"]
    if not isinstance(desc, str) or not 10 <= len(desc.strip()) <= 240:
        raise SkillConfigError("Invalid skill description")
    worker = data["worker_id"]
    if not isinstance(worker, str) or not WORKER_ID_RE.fullmatch(worker):
        raise SkillConfigError("Invalid skill worker ID")
    if data["execution_mode"] not in MODES:
        raise SkillConfigError("Unsupported execution mode")
    _names(data["required_permissions"], "required_permissions",
           options=PERMISSIONS, pattern=re.compile(r"[a-z]+\.[a-z_]+\Z"))
    _names(data["required_tools"], "required_tools", options=TOOLS)
    _names(data["artifact_types"], "artifact_types")
    _names(data["quality_checks"], "quality_checks")
    limits = data["limits"]
    if not isinstance(limits, dict) or set(limits) != LIMIT_FIELDS:
        raise SkillConfigError("Invalid limits")
    seconds, calls = limits["timeout_seconds"], limits["estimated_model_calls"]
    if (type(seconds) is not int or not 1 <= seconds <= 3600
            or type(calls) is not int or not 0 <= calls <= 20):
        raise SkillConfigError("Invalid skill resource hints")
    if data["execution_mode"] == "read_only" and any(
        p in data["required_permissions"] for p in ("workspace.write", "workspace.propose", "model.invoke", "network.read", "network.search", "browser.run", "process.run")
    ):
        raise SkillConfigError("Read-only skill cannot declare side-effect permissions")
    _schema(data["input_schema"], "input_schema")
    _schema(data["output_schema"], "output_schema")
    return data


def load_skill(skill_id, *, root=None):
    """Read and validate one built-in manifest. Never import handler code."""
    skill_id = _skill_id(skill_id)
    project = Path(root) if root is not None else ROOT
    folder = project / "skills" / skill_id
    manifest = folder / "skill.toml"
    _safe_path(manifest)
    if not manifest.is_file():
        raise SkillConfigError(f"Skill manifest not found: {skill_id}")
    if manifest.stat().st_size > MAX_MANIFEST_BYTES:
        raise SkillConfigError("Skill manifest exceeds size limit")
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise SkillConfigError(f"Cannot parse skill: {skill_id}") from exc
    return _contract(data, skill_id)


def load_registry(*, root=None):
    """Fail the entire registry if a manifest is malformed or duplicated."""
    project = Path(root) if root is not None else ROOT
    folder = project / "skills"
    _safe_path(folder)
    if not folder.is_dir():
        raise SkillConfigError("Skill directory not found")
    registry = {}
    for entry in sorted(folder.iterdir(), key=lambda item: item.name):
        _safe_path(entry)
        if not entry.is_dir():
            raise SkillConfigError(f"Unexpected skill directory entry: {entry.name}")
        skill = load_skill(entry.name, root=project)
        if skill["id"] in registry:
            raise SkillConfigError(f"Duplicate skill ID: {skill['id']}")
        registry[skill["id"]] = skill
    if not registry:
        raise SkillConfigError("Skill registry is empty")
    return registry


def validate_payload(skill, payload, *, direction="input"):
    """Validate a shallow object against our small, explicit schema subset.

    This checks only top-level JSON types, presence and extra keys. It does not
    validate nested structures, authorize actions, or execute any skill.
    """
    if direction not in {"input", "output"}:
        raise SkillConfigError("Invalid payload direction")
    schema = _schema(skill[f"{direction}_schema"], f"{direction}_schema")
    if not isinstance(payload, dict):
        raise SkillConfigError(f"{direction} payload must be an object")
    missing = set(schema["required"]) - set(payload)
    if missing:
        raise SkillConfigError(f"Missing {direction} fields: {sorted(missing)}")
    extras = set(payload) - set(schema["properties"])
    if extras and not schema["additional_properties"]:
        raise SkillConfigError(f"Unexpected {direction} fields: {sorted(extras)}")
    for name, value in payload.items():
        if name not in schema["properties"]:
            continue
        kind = schema["properties"][name]
        valid = {
            "string": lambda x: isinstance(x, str),
            "integer": lambda x: type(x) is int,
            "number": lambda x: type(x) in (int, float),
            "boolean": lambda x: type(x) is bool,
            "array": lambda x: isinstance(x, list),
            "object": lambda x: isinstance(x, dict),
        }[kind](value)
        if not valid:
            raise SkillConfigError(f"Invalid {direction} field type: {name} ({kind})")
    return payload


def main():
    parser = argparse.ArgumentParser(description="S1.1 Skill Registry — discovery only")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List declarative skills without invoking them")
    sub.add_parser("validate", help="Validate all skill manifests without invoking them")
    sub.add_parser("inspect", help="Inspect a skill contract").add_argument("skill_id")
    args = parser.parse_args()
    if args.command == "inspect":
        result = {**load_skill(args.skill_id), "invocation_enabled": False}
    else:
        registry = load_registry()
        if args.command == "list":
            result = [
                {"id": skill["id"], "version": skill["version"],
                 "description": skill["description"],
                 "execution_mode": skill["execution_mode"],
                 "invocation_enabled": False}
                for skill in registry.values()
            ]
        else:
            result = {"status": "VALID", "skill_count": len(registry),
                      "invocation_enabled": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
