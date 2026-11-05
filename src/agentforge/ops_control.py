"""Owner-local emergency pause for NEW AgentForge skill/Goal/schedule dispatch.

No running subprocess or external API can be forcibly stopped safely; this
state is checked before future actions and between bounded Goal steps. Existing
actions may finish or become INTERRUPTED. It is not OS sandboxing or a service.
Corrupted state is fail-closed PAUSED. Default with no file is ACTIVE for
backward-compatible local operation. Owner must explicitly resume.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentforge.ops_backup import _safe

STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "company" / "ops_control.json"
MAX_BYTES = 4096
MODES = {"ACTIVE", "PAUSED"}


def read(*, path=None):
    try:
        target = _safe(Path(path) if path is not None else STATE_FILE)
    except (ValueError, OSError):
        return {"mode": "PAUSED", "reason": "INVALID_STATE", "persisted": True}
    if not target.exists():
        return {"mode": "ACTIVE", "reason": "DEFAULT_LOCAL", "persisted": False}
    if not target.is_file() or target.stat().st_size > MAX_BYTES:
        return {"mode": "PAUSED", "reason": "INVALID_STATE", "persisted": True}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or value.get("schema") != 1
                or value.get("mode") not in MODES
                or not isinstance(value.get("updated_at_utc"), str)):
            raise ValueError("Invalid state")
        return {"mode": value["mode"], "reason": "OWNER_SET",
                "persisted": True, "updated_at_utc": value["updated_at_utc"]}
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError, OSError):
        return {"mode": "PAUSED", "reason": "INVALID_STATE", "persisted": True}


def require_active(*, path=None):
    state = read(path=path)
    if state["mode"] != "ACTIVE":
        raise PermissionError("OPERATIONS_PAUSED: Owner must resume before new dispatch")
    return True


def set_mode(mode, *, confirm=False, path=None):
    if not isinstance(mode, str) or mode not in MODES or confirm is not True:
        raise PermissionError("Explicit owner confirmation required to pause or resume")
    target = _safe(Path(path) if path is not None else STATE_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    _safe(target.parent)
    temp = _safe(target.with_name(target.name + "." + uuid4().hex + ".tmp"))
    try:
        with temp.open("x", encoding="utf-8") as fp:
            json.dump({"schema": 1, "mode": mode,
                       "updated_at_utc": datetime.now(timezone.utc).isoformat()},
                      fp, separators=(",", ":"), ensure_ascii=False)
            fp.flush()
            os.fsync(fp.fileno())
        _safe(target)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    result = read(path=target)
    if result["mode"] != mode:
        raise RuntimeError("Operations pause state did not persist")
    return result


def main():
    parser = argparse.ArgumentParser(description="Owner-local pause/resume dispatch control")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    pause = sub.add_parser("pause")
    pause.add_argument("--confirm-pause", action="store_true")
    resume = sub.add_parser("resume")
    resume.add_argument("--confirm-resume", action="store_true")
    args = parser.parse_args()
    if args.action == "status":
        result = read()
    elif args.action == "pause":
        result = set_mode("PAUSED", confirm=args.confirm_pause)
    else:
        result = set_mode("ACTIVE", confirm=args.confirm_resume)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
