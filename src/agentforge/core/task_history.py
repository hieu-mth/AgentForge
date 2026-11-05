"""S1: durable local task states and append-only events.

SQLite is a record of execution, not an execution sandbox or source of truth
for permissions. Recovery never silently reruns actions after a crash.
"""
import argparse
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from agentforge.paths import REPOSITORY_ROOT
from uuid import uuid4

ROOT = REPOSITORY_ROOT
DEFAULT_DB = ROOT / "data" / "company" / "s1_tasks.sqlite3"
TASK_ID = re.compile(r"[a-f0-9]{32}\Z")
KINDS = {"skill", "workflow"}
STATES = {"QUEUED", "RUNNING", "WAITING_APPROVAL", "SUCCEEDED", "FAILED", "INTERRUPTED"}
TRANSITIONS = {
    "QUEUED": {"RUNNING", "WAITING_APPROVAL", "FAILED"},
    "RUNNING": {"WAITING_APPROVAL", "SUCCEEDED", "FAILED", "INTERRUPTED"},
    "WAITING_APPROVAL": {"RUNNING", "FAILED"},
    "SUCCEEDED": set(), "FAILED": set(), "INTERRUPTED": set(),
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value, *, limit):
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError("Task record exceeds size limit")
    return encoded


def _path(db_path):
    path = Path(db_path) if db_path is not None else DEFAULT_DB
    for component in (path, *path.parents):
        if component.is_symlink() or (
            hasattr(component, "is_junction") and component.is_junction()
        ):
            raise PermissionError("Task database symlinks/junctions are forbidden")
    return path


def _connect(db_path):
    path = _path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE IF NOT EXISTS tasks ("
                 "task_id TEXT PRIMARY KEY, kind TEXT NOT NULL, skill_id TEXT NOT NULL,"
                 "parent_id TEXT REFERENCES tasks(task_id), status TEXT NOT NULL,"
                 "request_json TEXT NOT NULL, result_json TEXT, error TEXT,"
                 "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS events ("
                 "event_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 "task_id TEXT NOT NULL REFERENCES tasks(task_id),"
                 "at TEXT NOT NULL, name TEXT NOT NULL, detail_json TEXT NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)")
    conn.commit()
    return conn


def _id(value):
    if not isinstance(value, str) or not TASK_ID.fullmatch(value):
        raise ValueError("Invalid task ID")
    return value


def create_task(kind, skill_id, request, *, parent_id=None, db_path=None):
    if kind not in KINDS or not isinstance(skill_id, str) or not 3 <= len(skill_id) <= 80:
        raise ValueError("Invalid task kind or skill")
    if parent_id is not None:
        _id(parent_id)
    if not isinstance(request, dict):
        raise ValueError("Task input must be an object")
    raw_request = _json(request, limit=8192)
    task_id, now = uuid4().hex, _now()
    with closing(_connect(db_path)) as conn, conn:
        conn.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (task_id, kind, skill_id, parent_id, "QUEUED",
                      raw_request, None, None, now, now))
        conn.execute("INSERT INTO events(task_id,at,name,detail_json) VALUES(?,?,?,?)",
                     (task_id, now, "CREATED", "{}"))
    return task_id


def transition(task_id, status, *, result=None, error=None, db_path=None):
    _id(task_id)
    if status not in STATES:
        raise ValueError("Invalid state")
    raw_result = None if result is None else _json(result, limit=65536)
    if error is not None and not isinstance(error, str):
        raise ValueError("Task error must be text")
    error = error[:240] if error else None
    with closing(_connect(db_path)) as conn, conn:
        row = conn.execute("SELECT status FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown task")
        previous = row["status"]
        if status not in TRANSITIONS[previous]:
            raise ValueError(f"Invalid task transition: {previous} -> {status}")
        now = _now()
        changed = conn.execute(
            "UPDATE tasks SET status=?, result_json=COALESCE(?,result_json), "
            "error=?, updated_at=? WHERE task_id=? AND status=?",
            (status, raw_result, error, now, task_id, previous),
        )
        if changed.rowcount != 1:
            raise RuntimeError("Task state changed concurrently")
        conn.execute("INSERT INTO events(task_id,at,name,detail_json) VALUES(?,?,?,?)",
                     (task_id, now, status, "{}"))


def checkpoint(task_id, name, detail, *, db_path=None):
    _id(task_id)
    if not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,39}", name):
        raise ValueError("Invalid checkpoint event")
    raw = _json(detail, limit=4096)
    with closing(_connect(db_path)) as conn, conn:
        row = conn.execute("SELECT status FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None or row["status"] != "RUNNING":
            raise ValueError("Only running tasks can checkpoint")
        conn.execute("INSERT INTO events(task_id,at,name,detail_json) VALUES(?,?,?,?)",
                     (task_id, _now(), name, raw))


def get_task(task_id, *, db_path=None):
    _id(task_id)
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown task")
        task = dict(row)
        task["request"] = json.loads(task.pop("request_json"))
        raw_result = task.pop("result_json")
        task["result"] = json.loads(raw_result) if raw_result is not None else None
        task["events"] = [
            {"at": e["at"], "name": e["name"],
             "detail": json.loads(e["detail_json"])}
            for e in conn.execute("SELECT at,name,detail_json FROM events "
                                  "WHERE task_id=? ORDER BY event_id", (task_id,))
        ]
        return task


def list_tasks(*, db_path=None, limit=50):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Invalid task list limit")
    with closing(_connect(db_path)) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT task_id, kind, skill_id, parent_id, status, error,"
            "created_at, updated_at FROM tasks ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        )]


def recover(*, db_path=None):
    """Explicitly mark orphaned RUNNING tasks interrupted, never replay them."""
    interrupted = 0
    with closing(_connect(db_path)) as conn, conn:
        rows = conn.execute("SELECT task_id FROM tasks WHERE status='RUNNING'").fetchall()
        for row in rows:
            now = _now()
            changed = conn.execute("UPDATE tasks SET status='INTERRUPTED', updated_at=? "
                                   "WHERE task_id=? AND status='RUNNING'",
                                   (now, row["task_id"]))
            if changed.rowcount == 1:
                interrupted += 1
                conn.execute("INSERT INTO events(task_id,at,name,detail_json) VALUES(?,?,?,?)",
                             (row["task_id"], now, "INTERRUPTED", '{"reason":"explicit_recovery"}'))
    return interrupted


def main():
    parser = argparse.ArgumentParser(description="S1 durable local task history")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("show").add_argument("task_id")
    cmd = sub.add_parser("recover", help="Mark abandoned RUNNING as INTERRUPTED, never replay")
    cmd.add_argument("--confirm-recover", action="store_true")
    args = parser.parse_args()
    if args.command == "list":
        result = list_tasks()
    elif args.command == "show":
        result = get_task(args.task_id)
    else:
        if not args.confirm_recover:
            parser.error("Explicit --confirm-recover required")
        result = {"interrupted": recover()}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
