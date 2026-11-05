"""Owner-configured limits for prompt-first workspace, not provider billing.

Only restricts the /api/workspace/request UX path; legacy S4 CLI and
Autopilot have their own separate permission gates and independent quotas.
SQLite contains no API tokens, customer data, or currency amounts.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from agentforge import brain_store

DB = brain_store.ROOT / "data" / "company" / "workspace_policy.sqlite3"
DEFAULT = {"max_estimated_model_calls": 1, "website_enabled": True,
           "storyboard_enabled": True}


def _path(path):
    path = Path(path) if path is not None else DB
    for node in (path, *path.parents):
        if node.is_symlink() or (hasattr(node, "is_junction") and node.is_junction()):
            raise PermissionError("Symlink/junction workspace policy path refused")
    return path


def _connect(path=None, *, create=False):
    target = _path(path)
    if not create and not target.is_file():
        return None
    if create:
        target.parent.mkdir(parents=True, exist_ok=True)
        _path(target.parent)
    db = sqlite3.connect(target, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    if create:
        db.execute("""CREATE TABLE IF NOT EXISTS policy (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            max_estimated_model_calls INTEGER NOT NULL,
            website_enabled INTEGER NOT NULL,
            storyboard_enabled INTEGER NOT NULL,
            updated_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS changes (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            old_model_calls INTEGER NOT NULL, new_model_calls INTEGER NOT NULL,
            old_website INTEGER NOT NULL, new_website INTEGER NOT NULL,
            old_storyboard INTEGER NOT NULL, new_storyboard INTEGER NOT NULL,
            changed_at TEXT NOT NULL)""")
        db.commit()
    return db


def read(*, db_path=None):
    db = _connect(db_path)
    if db is None:
        return {**DEFAULT, "source": "DEFAULT", "provider_billing_verified": False}
    with closing(db):
        row = db.execute("SELECT * FROM policy WHERE singleton=1").fetchone()
    if row is None:
        return {**DEFAULT, "source": "DEFAULT", "provider_billing_verified": False}
    return {
        "max_estimated_model_calls": row["max_estimated_model_calls"],
        "website_enabled": bool(row["website_enabled"]),
        "storyboard_enabled": bool(row["storyboard_enabled"]),
        "source": "OWNER_SET", "provider_billing_verified": False,
    }


def configure(*, max_estimated_model_calls, website_enabled, storyboard_enabled,
              confirm=False, db_path=None):
    if confirm is not True:
        raise PermissionError("Explicit owner workspace policy confirmation required")
    if (type(max_estimated_model_calls) is not int or
            not 0 <= max_estimated_model_calls <= 3 or
            type(website_enabled) is not bool or
            type(storyboard_enabled) is not bool):
        raise ValueError("Invalid workspace policy fields")
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect(db_path, create=True)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT * FROM policy WHERE singleton=1").fetchone()
            old = (DEFAULT["max_estimated_model_calls"],
                   int(DEFAULT["website_enabled"]), int(DEFAULT["storyboard_enabled"])) if row is None else (
                   row["max_estimated_model_calls"], row["website_enabled"], row["storyboard_enabled"])
            new = (max_estimated_model_calls, int(website_enabled), int(storyboard_enabled))
            db.execute("""INSERT INTO policy VALUES(1,?,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                  max_estimated_model_calls=excluded.max_estimated_model_calls,
                  website_enabled=excluded.website_enabled,
                  storyboard_enabled=excluded.storyboard_enabled,
                  updated_at=excluded.updated_at""", (*new, now))
            db.execute("INSERT INTO changes(old_model_calls,new_model_calls,"
                       "old_website,new_website,old_storyboard,new_storyboard,changed_at) "
                       "VALUES(?,?,?,?,?,?,?)",
                       (old[0], new[0], old[1], new[1], old[2], new[2], now))
            db.commit()
        except Exception:
            db.rollback()
            raise
    return read(db_path=db_path)
