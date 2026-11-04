"""AgentForge local-first backup, verify and non-destructive staged restore.

Backups contain sensitive unencrypted local business data. No cloud upload.
SQLite snapshots are taken via sqlite3.Connection.backup() (not raw copying
a live database). Restore NEVER overwrites data; only extracts into a new
empty staging directory for manual review while services are stopped.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "company"
WORKSPACE = ROOT / "workspace"
OUT = ROOT / "workspace" / "backups"
MAX_FILE = 250 * 1024 * 1024
MAX_TOTAL = 1_500 * 1024 * 1024
MAX_ENTRIES = 2500
ARCHIVE_NAME = re.compile(r"agentforge-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}\.zip\Z")


class BackupError(ValueError):
    pass


def _safe(path):
    path = Path(path)
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise BackupError("Symlink/junction in backup source or destination")
    return path


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _sqlite_snapshot(source):
    """Online, transaction-consistent SQLite byte snapshot; fail on corruption."""
    with tempfile.TemporaryDirectory() as temporary:
        tmp = Path(temporary) / "snapshot.sqlite3"
        with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True,
                                    timeout=5)) as origin:
            with closing(sqlite3.connect(tmp, timeout=5)) as clone:
                origin.backup(clone)
                result = clone.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise BackupError("SQLite integrity_check failed")
        if tmp.stat().st_size > MAX_FILE:
            raise BackupError("SQLite database exceeds per-file backup limit")
        return tmp.read_bytes()


def _paths(include_workspace):
    if type(include_workspace) is not bool:
        raise BackupError("include_workspace must be boolean")
    result = []
    if DATA_DIR.is_dir():
        for p in sorted(DATA_DIR.glob("*.sqlite3")):
            if _safe(p).is_file():
                result.append(("data/company/" + p.name, p, True))
    if include_workspace and WORKSPACE.is_dir():
        for name in ("products", "media", "growth"):
            base = WORKSPACE / name
            if not base.exists():
                continue
            _safe(base)
            for p in sorted(base.rglob("*")):
                _safe(p)
                if p.is_file():
                    result.append((p.relative_to(ROOT).as_posix(), p, False))
    if len(result) > MAX_ENTRIES:
        raise BackupError("Backup source file count exceeds safety limit")
    return result


def create(*, include_workspace=False, confirm_backup=False, out_dir=None):
    if confirm_backup is not True:
        raise PermissionError("Explicit --confirm-backup required")
    target = _safe(Path(out_dir) if out_dir is not None else OUT)
    files = _paths(include_workspace)
    if not files:
        raise BackupError("No local data files to back up")
    target.mkdir(parents=True, exist_ok=True)
    name = "agentforge-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + \
           "-" + uuid4().hex[:8] + ".zip"
    destination = _safe(target / name)
    manifest = {
        "schema": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "include_workspace": include_workspace,
        "contents": [], "unencrypted_sensitive_backup": True,
        "contains_credentials_checked": False,
        "external_upload_performed": False,
    }
    total = 0
    try:
        with zipfile.ZipFile(destination, "x", allowZip64=True) as archive:
            for arc, source, is_db in files:
                if source.stat().st_size > MAX_FILE:
                    raise BackupError("File exceeds 250 MB budget")
                raw = _sqlite_snapshot(source) if is_db else source.read_bytes()
                total += len(raw)
                if total > MAX_TOTAL:
                    raise BackupError("Backup size exceeds 1.5GB safety limit")
                archive.writestr(arc, raw, compress_type=zipfile.ZIP_DEFLATED)
                manifest["contents"].append({
                    "path": arc, "bytes": len(raw),
                    "sha256": _digest(raw), "sqlite": is_db,
                })
            archive.writestr("manifest.json", json.dumps(
                manifest, sort_keys=True, ensure_ascii=False).encode("utf-8"),
                compress_type=zipfile.ZIP_DEFLATED)
        verified = verify(destination)
        if verified["status"] != "PASS":
            raise BackupError("Backup verification did not pass")
        return {"status": "CREATED_AND_VERIFIED", "archive": str(destination),
                "files": len(manifest["contents"]), "total_bytes": total,
                "unencrypted": True, "external_upload": False}
    except FileExistsError:
        # Exclusive-create failure: never remove a prior owner's archive.
        raise
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _read_manifest(archive):
    names = archive.namelist()
    if (len(names) > MAX_ENTRIES + 1 or len(names) != len(set(names))
            or names.count("manifest.json") != 1):
        raise BackupError("Duplicate/missing ZIP entries")
    try:
        m = json.loads(archive.read("manifest.json"))
    except (ValueError, KeyError, UnicodeError, RuntimeError) as exc:
        raise BackupError("Invalid backup manifest") from exc
    if m.get("schema") != 1 or not isinstance(m.get("contents"), list):
        raise BackupError("Unsupported manifest schema")
    expected = {"manifest.json"}
    for item in m["contents"]:
        if not isinstance(item, dict) or set(item) != {
                "path", "bytes", "sha256", "sqlite"}:
            raise BackupError("Invalid manifest file entry")
        p = item["path"]
        if (not isinstance(p, str) or p.startswith("/") or "\\" in p
                or any(part in {"", ".", ".."} for part in p.split("/"))
                or not p.startswith(("data/company/", "workspace/products/",
                                      "workspace/media/", "workspace/growth/"))
                or len(p) > 260 or p in expected
                or not isinstance(item["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                or type(item["bytes"]) is not int
                or not 0 <= item["bytes"] <= MAX_FILE
                or type(item["sqlite"]) is not bool):
            raise BackupError("Unsafe ZIP manifest path or metadata")
        if item["sqlite"] != (p.startswith("data/company/") and p.endswith(".sqlite3")):
            raise BackupError("Database classification mismatch")
        expected.add(p)
    if set(names) != expected:
        raise BackupError("ZIP contains unmanifested files")
    return m


def _sqlite_bytes_ok(raw):
    with tempfile.TemporaryDirectory() as temp:
        p = Path(temp) / "check.sqlite3"
        p.write_bytes(raw)
        try:
            with closing(sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)) as db:
                check = db.execute("PRAGMA integrity_check").fetchone()
                return check is not None and check[0] == "ok"
        except sqlite3.DatabaseError:
            return False


def verify(path):
    source = _safe(Path(path))
    if not source.is_file() or not ARCHIVE_NAME.fullmatch(source.name):
        raise BackupError("Unknown backup filename")
    if source.stat().st_size > MAX_TOTAL:
        raise BackupError("Archive exceeds allowed size")
    try:
        with zipfile.ZipFile(source) as archive:
            m = _read_manifest(archive)
            total = 0
            for item in m["contents"]:
                info = archive.getinfo(item["path"])
                if info.file_size != item["bytes"]:
                    raise BackupError("Declared and stored file lengths differ")
                total += info.file_size
                if total > MAX_TOTAL:
                    raise BackupError("Uncompressed archive exceeds budget")
                with archive.open(item["path"]) as f:
                    raw = f.read(item["bytes"] + 1)
                if len(raw) != item["bytes"] or _digest(raw) != item["sha256"]:
                    raise BackupError("Backup checksum mismatch")
                if item["sqlite"] and not _sqlite_bytes_ok(raw):
                    raise BackupError("Restored SQLite snapshot fails integrity_check")
            return {"status": "PASS", "files": len(m["contents"]),
                    "total_bytes": total, "unencrypted": True,
                    "external_upload": False}
    except (zipfile.BadZipFile, OSError, RuntimeError, KeyError) as exc:
        raise BackupError("Backup ZIP unreadable or incomplete") from exc


def stage_restore(path, destination, *, confirm_restore=False):
    """Extract only into a NEW destination, never mutate active databases."""
    if confirm_restore is not True:
        raise PermissionError("Explicit --confirm-restore required")
    target = _safe(Path(destination))
    if target.exists():
        raise BackupError("Restore destination must not exist; no overwrite")
    report = verify(path)
    if report["status"] != "PASS":
        raise BackupError("Backup must pass verification before staging")
    target.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(path) as archive:
            m = _read_manifest(archive)
            for item in m["contents"]:
                p = _safe(target.joinpath(*item["path"].split("/")))
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("xb") as output, archive.open(item["path"]) as src:
                    checksum = hashlib.sha256()
                    copied = 0
                    while True:
                        chunk = src.read(min(1024 * 1024, item["bytes"] - copied + 1))
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > item["bytes"]:
                            raise BackupError("ZIP entry exceeded declared size during extraction")
                        checksum.update(chunk)
                        output.write(chunk)
                    if copied != item["bytes"] or checksum.hexdigest() != item["sha256"]:
                        raise BackupError("Archive changed since verification; staging discarded")
        return {"status": "RESTORED_TO_STAGING_ONLY",
                "destination": str(target), "files": report["files"],
                "active_databases_overwritten": False,
                "manual_owner_inspection_required": True}
    except BaseException:
        shutil.rmtree(target)
        raise


def main():
    parser = argparse.ArgumentParser(description="Local SQLite/artifact backup, verify and safe restore staging")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create")
    c.add_argument("--include-workspace", action="store_true")
    c.add_argument("--confirm-backup", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("archive")
    r = sub.add_parser("stage-restore")
    r.add_argument("archive")
    r.add_argument("destination")
    r.add_argument("--confirm-restore", action="store_true")
    args = parser.parse_args()
    if args.command == "create":
        result = create(include_workspace=args.include_workspace,
                        confirm_backup=args.confirm_backup)
    elif args.command == "verify":
        result = verify(args.archive)
    else:
        result = stage_restore(args.archive, args.destination,
                               confirm_restore=args.confirm_restore)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
