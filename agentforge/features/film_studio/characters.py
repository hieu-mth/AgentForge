"""Local-first character metadata registry. No implicit model training or uploads."""
import json
import os
import re
import sqlite3
from contextlib import contextmanager
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.RLock()
_ID = re.compile(r"^[a-f0-9]{32}$")
_DEFAULT_DB = Path(os.environ.get("AGENTFORGE_CHARACTER_DB", "data/characters.sqlite3"))

@contextmanager
def _db(path=None):
    target = Path(path) if path is not None else _DEFAULT_DB
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("""CREATE TABLE IF NOT EXISTS characters (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, species TEXT NOT NULL,
        appearance TEXT NOT NULL, personality TEXT NOT NULL,
        voice TEXT NOT NULL, model_ref TEXT NOT NULL,
        reference_notes TEXT NOT NULL, version INTEGER NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    try:
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

def list_characters(path=None):
    with _LOCK, _db(path) as conn:
        return {"characters": [dict(row) for row in conn.execute(
            "SELECT * FROM characters ORDER BY updated_at DESC, id DESC LIMIT 500")]}

def save_character(data, path=None):
    values = _validate(data)
    now = datetime.now(timezone.utc).isoformat()
    identifier = data.get("id")
    with _LOCK, _db(path) as conn:
        if identifier is None:
            identifier = uuid.uuid4().hex
            conn.execute("""INSERT INTO characters
                (id,name,species,appearance,personality,voice,model_ref,reference_notes,version,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
                (identifier, *(values[k] for k in values), now, now))
        else:
            if not isinstance(identifier,str) or not _ID.fullmatch(identifier):
                raise ValueError("Invalid character id")
            expected = data.get("expected_version")
            if type(expected) is not int or expected < 1:
                raise ValueError("Expected version required")
            cursor = conn.execute("""UPDATE characters SET
                name=?,species=?,appearance=?,personality=?,voice=?,model_ref=?,reference_notes=?,
                version=version+1,updated_at=? WHERE id=? AND version=?""",
                (*(values[k] for k in values),now,identifier,expected))
            if cursor.rowcount != 1:
                raise ValueError("Character changed or not found; refresh before editing")
        return dict(conn.execute("SELECT * FROM characters WHERE id=?", (identifier,)).fetchone())
