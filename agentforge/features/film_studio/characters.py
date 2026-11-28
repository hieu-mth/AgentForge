"""Local-first character metadata registry. No implicit model training or uploads."""
import os
import re
import sqlite3
from contextlib import contextmanager
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from agentforge.paths import REPOSITORY_ROOT, ensure_local_root

_LOCK = threading.RLock()
_ID = re.compile(r"^[a-f0-9]{32}$")
def _db_path(path=None):
    candidate = Path(path) if path is not None else Path(
        os.environ.get("AGENTFORGE_CHARACTER_DB", "data/characters.sqlite3"))
    if not candidate.is_absolute():
        candidate = REPOSITORY_ROOT / candidate
    return ensure_local_root(candidate)


@contextmanager
def _db(path=None, *, create=False):
    target = _db_path(path)
    if not create and not target.is_file():
        yield None
        return
    if create:
        target.parent.mkdir(parents=True, exist_ok=True)
        ensure_local_root(target)
        conn = sqlite3.connect(target, timeout=10)
    else:
        # Open existing SQLite read-only, without creating database/journal files.
        conn = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        if create:
            conn.execute("""CREATE TABLE IF NOT EXISTS characters (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, species TEXT NOT NULL,
                appearance TEXT NOT NULL, personality TEXT NOT NULL,
                voice TEXT NOT NULL, model_ref TEXT NOT NULL,
                reference_notes TEXT NOT NULL, version INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
        with conn:
            yield conn
    finally:
        conn.close()


def _clean(value, limit=2000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Invalid character field")
    return value.strip()

def _validate(data):
    if not isinstance(data, dict):
        raise ValueError("Character must be an object")
    name = _clean(data.get("name"), 100)
    if not name:
        raise ValueError("Character name required")
    return {key: _clean(data.get(key, ""), limit) for key,limit in [
        ("name",100),("species",80),("appearance",2000),("personality",2000),
        ("voice",300),("model_ref",200),("reference_notes",2000)]}

def _archive_exists(conn):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_archives'").fetchone())


def list_characters(path=None, *, include_archived=False):
    with _LOCK, _db(path) as conn:
        if conn is None:
            return {"characters": []}
        archive = _archive_exists(conn)
        if archive:
            query = ("SELECT c.*, a.character_id IS NOT NULL AS archived FROM characters c "
                     "LEFT JOIN character_archives a ON a.character_id=c.id "
                     + ("" if include_archived else "WHERE a.character_id IS NULL ")
                     + "ORDER BY c.updated_at DESC, c.id DESC")
        else:
            query = "SELECT *, 0 AS archived FROM characters ORDER BY updated_at DESC, id DESC"
        return {"characters": [dict(row) for row in conn.execute(query)]}


def _save_record(conn, data, values):
    now = datetime.now(timezone.utc).isoformat()
    identifier = data.get("id")
    if identifier is None:
        identifier = uuid.uuid4().hex
        conn.execute("""INSERT INTO characters
            (id,name,species,appearance,personality,voice,model_ref,reference_notes,version,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
            (identifier, *(values[k] for k in values), now, now))
    else:
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise ValueError("Invalid character id")
        expected = data.get("expected_version")
        if type(expected) is not int or expected < 1:
            raise ValueError("Expected version required")
        if _archive_exists(conn) and conn.execute(
                "SELECT 1 FROM character_archives WHERE character_id=?", (identifier,)).fetchone():
            raise ValueError("Restore archived character before editing")
        cursor = conn.execute("""UPDATE characters SET
            name=?,species=?,appearance=?,personality=?,voice=?,model_ref=?,reference_notes=?,
            version=version+1,updated_at=? WHERE id=? AND version=?""",
            (*(values[k] for k in values),now,identifier,expected))
        if cursor.rowcount != 1:
            raise ValueError("Character changed or not found; refresh before editing")
    return dict(conn.execute("SELECT * FROM characters WHERE id=?", (identifier,)).fetchone())


def save_character(data, path=None):
    values = _validate(data)
    with _LOCK, _db(path, create=True) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return _save_record(conn, data, values)


def set_archived(identifier, expected_version, archived, path=None):
    if (not isinstance(identifier, str) or not _ID.fullmatch(identifier)
            or type(expected_version) is not int or expected_version < 1 or type(archived) is not bool):
        raise ValueError("Invalid character archive request")
    with _LOCK, _db(path, create=True) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT version FROM characters WHERE id=?", (identifier,)).fetchone()
        if row is None or row["version"] != expected_version:
            raise ValueError("Character changed or not found; refresh before editing")
        conn.execute("CREATE TABLE IF NOT EXISTS character_archives (character_id TEXT PRIMARY KEY)")
        if archived:
            conn.execute("INSERT OR IGNORE INTO character_archives VALUES (?)", (identifier,))
        else:
            conn.execute("DELETE FROM character_archives WHERE character_id=?", (identifier,))
        conn.execute("UPDATE characters SET version=version+1, updated_at=? WHERE id=?",
                     (datetime.now(timezone.utc).isoformat(), identifier))
    return {"id": identifier, "archived": archived}
