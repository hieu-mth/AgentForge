"""Owner-initiated fresh-start for local AgentForge runtime data.

Never deletes user content. Moves *entire* data/ and workspace/ directories
into a timestamped sibling archive outside the Git repository. Stop all
AgentForge processes before running (including schedulers). No network access.

CLI:
  python scripts/archive_local_state.py report
  python scripts/archive_local_state.py archive --confirm-stopped --confirm-archive ARCHIVE_LOCAL_STATE
  python scripts/archive_local_state.py restore ARCHIVE_ID --confirm-stopped --confirm-restore RESTORE_LOCAL_STATE

Restore refuses to overwrite any existing data/ or workspace/ directory.
"""
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT.parent / "AgentForge-local-state-archives"
ACTIVE = ("data", "workspace")
ID_PATTERN = re.compile(r"state-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\Z")


def _linked(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _safe_chain(path):
    for entry in (path, *path.parents):
        if _linked(entry):
            raise PermissionError("Linked/junction storage locations are refused")
    return path


def report():
    _safe_chain(ROOT)
    _safe_chain(ARCHIVE_ROOT)
    entries = []
    for name in ACTIVE:
        path = _safe_chain(ROOT / name)
        entries.append({"name": name, "exists": path.exists(),
                        "directory": path.is_dir() if path.exists() else False})
    return {"operation": "REPORT_ONLY", "root": str(ROOT),
            "archive_parent": str(ARCHIVE_ROOT),
            "scope": entries, "includes_credentials_or_private_content": True,
            "requires_stopped_services": True, "deleted_files": 0}


def _manifest(folder, *, status, names):
    # The journal is written before the first rename and after each rename,
    # helping manual recovery if Windows/power loss interrupts the operation.
    file = folder / "manifest.json"
    temp = folder / "manifest.new"
    payload = {"schema": 1, "status": status, "names": names,
               "root": str(ROOT), "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "permanent_deletion": False}
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp, file)


def archive(*, confirm_stopped=False, confirmation=""):
    if not confirm_stopped or confirmation != "ARCHIVE_LOCAL_STATE":
        raise PermissionError("Stop all AgentForge processes and explicitly authorize archival")
    report()
    existing = []
    for name in ACTIVE:
        path = _safe_chain(ROOT / name)
        if path.exists():
            if not path.is_dir():
                raise ValueError("Runtime location is not a directory: " + name)
            existing.append(name)
    if not existing:
        return {"status": "ALREADY_EMPTY", "archived": [], "deleted_files": 0}
    ARCHIVE_ROOT.mkdir(exist_ok=True)
    _safe_chain(ARCHIVE_ROOT)
    ident = "state-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    folder = _safe_chain(ARCHIVE_ROOT / ident)
    folder.mkdir(exist_ok=False)
    moved = []
    try:
        _manifest(folder, status="MOVING", names=existing)
        for name in existing:
            source = _safe_chain(ROOT / name)
            destination = _safe_chain(folder / name)
            if destination.exists():
                raise FileExistsError("Archive destination unexpectedly exists")
            os.replace(source, destination)
            moved.append(name)
            _manifest(folder, status="MOVING", names=moved)
        _manifest(folder, status="ARCHIVED", names=moved)
    except BaseException:
        # Best-effort rollback; never overwrite a newly recreated destination.
        for name in reversed(moved):
            destination = ROOT / name
            source = folder / name
            if not destination.exists() and source.exists():
                os.replace(source, destination)
        _manifest(folder, status="INTERRUPTED_INSPECT_MANUALLY", names=moved)
        raise
    return {"status": "ARCHIVED", "archive_id": ident,
            "location": str(folder), "archived": moved,
            "deleted_files": 0, "restore_possible": True}


def restore(archive_id, *, confirm_stopped=False, confirmation=""):
    if not confirm_stopped or confirmation != "RESTORE_LOCAL_STATE":
        raise PermissionError("Stop all AgentForge processes and explicitly authorize restore")
    if not isinstance(archive_id, str) or not ID_PATTERN.fullmatch(archive_id):
        raise ValueError("Invalid archive identifier")
    _safe_chain(ROOT)
    folder = _safe_chain(ARCHIVE_ROOT / archive_id)
    manifest_file = _safe_chain(folder / "manifest.json")
    if not manifest_file.is_file():
        raise FileNotFoundError("Archive manifest not found")
    doc = json.loads(manifest_file.read_text(encoding="utf-8"))
    names = doc.get("names")
    if (doc.get("schema") != 1 or doc.get("status") != "ARCHIVED"
            or doc.get("root") != str(ROOT)
            or not isinstance(names, list) or not names
            or len(names) != len(set(names))
            or any(n not in ACTIVE for n in names)):
        raise ValueError("Archive is not a completed matching state snapshot")
    for name in names:
        source = _safe_chain(folder / name)
        target = _safe_chain(ROOT / name)
        if not source.is_dir() or target.exists():
            raise FileExistsError("Refusing to overwrite active state; stop and inspect manually")
    moved = []
    try:
        _manifest(folder, status="RESTORING", names=names)
        for name in names:
            os.replace(folder / name, ROOT / name)
            moved.append(name)
        _manifest(folder, status="RESTORED", names=names)
    except BaseException:
        for name in reversed(moved):
            source = ROOT / name
            target = folder / name
            if source.exists() and not target.exists():
                os.replace(source, target)
        _manifest(folder, status="INTERRUPTED_INSPECT_MANUALLY", names=names)
        raise
    return {"status": "RESTORED", "archive_id": archive_id,
            "restored": moved, "overwritten": False, "deleted_files": 0}


def main():
    parser = argparse.ArgumentParser(description="Safe AgentForge local state reset")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("report")
    p = sub.add_parser("archive")
    p.add_argument("--confirm-stopped", action="store_true")
    p.add_argument("--confirm-archive", default="")
    r = sub.add_parser("restore")
    r.add_argument("archive_id")
    r.add_argument("--confirm-stopped", action="store_true")
    r.add_argument("--confirm-restore", default="")
    args = parser.parse_args()
    if args.action == "report":
        result = report()
    elif args.action == "archive":
        result = archive(confirm_stopped=args.confirm_stopped,
                         confirmation=args.confirm_archive)
    else:
        result = restore(args.archive_id, confirm_stopped=args.confirm_stopped,
                         confirmation=args.confirm_restore)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
