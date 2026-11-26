"""SQLite persistence for Studio drafts; no provider or worker dependencies."""
import json
import re
import sqlite3
from contextlib import closing, contextmanager

from agentforge.paths import ensure_local_root


class DraftNotFound(KeyError):
    """A valid production identifier has no persisted record."""


class DraftStoreUnavailable(RuntimeError):
    def __init__(self, message="Không truy cập được SQLite của bản nháp."):
        super().__init__(message)


@contextmanager
def connect(db_path, create=False):
    try:
        path = ensure_local_root(db_path)
        if not create and not path.exists():
            yield None
            return
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path if create else path.as_uri() + "?mode=ro", uri=not create, timeout=3)
        with closing(conn), conn:
            if create:
                conn.execute("CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
            yield conn
    except sqlite3.DatabaseError as exc:
        code = getattr(exc, "sqlite_errorcode", 0) & 0xff
        if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise DraftStoreUnavailable("SQLite của bản nháp đang bận. Hãy thử lại.") from exc
        if code in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}:
            raise DraftStoreUnavailable("Tệp SQLite của bản nháp bị hỏng hoặc sai định dạng.") from exc
        raise DraftStoreUnavailable() from exc
    except OSError as exc:
        raise DraftStoreUnavailable() from exc


def decode_row(row):
    try:
        job = json.loads(row[0])
        if (not isinstance(job, dict) or not isinstance(job.get("id"), str)
                or not isinstance(job.get("brief"), dict) or not isinstance(job.get("status"), str)):
            raise ValueError("Invalid draft record")
        return job
    except (ValueError, TypeError) as exc:
        raise DraftStoreUnavailable("Bản ghi bản nháp trong SQLite bị lỗi.") from exc


def validate_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("Invalid production ID")
    return value


def read(db_path, ident):
    validate_id(ident)
    with connect(db_path) as conn:
        row = conn.execute("SELECT body FROM drafts WHERE id=?", (ident,)).fetchone() if conn else None
        if row is None:
            raise DraftNotFound(ident)
        return decode_row(row)


def save(db_path, job, *, updated_at):
    job["updated_at"] = updated_at
    with connect(db_path, True) as conn:
        conn.execute("INSERT INTO drafts(id,body) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                     (job["id"], json.dumps(job, ensure_ascii=False)))


def cancellation(db_path, ident, *, mark=False):
    with connect(db_path, mark) as conn:
        if conn is None:
            return False
        if mark:
            conn.execute("CREATE TABLE IF NOT EXISTS draft_cancellations (id TEXT PRIMARY KEY)")
            conn.execute("INSERT OR IGNORE INTO draft_cancellations VALUES (?)", (ident,))
        table = conn.execute("SELECT 1 FROM sqlite_master WHERE name='draft_cancellations'").fetchone()
        return bool(table and conn.execute("SELECT 1 FROM draft_cancellations WHERE id=?", (ident,)).fetchone())


def recent(db_path):
    with connect(db_path) as conn:
        if conn is None:
            return []
        return [decode_row(row) for row in conn.execute(
            """SELECT body FROM drafts
               ORDER BY COALESCE(julianday(json_extract(body, '$.updated_at')),
                                 julianday(json_extract(body, '$.created_at'))) DESC, rowid DESC
               LIMIT 30""")]


def pending(db_path):
    with connect(db_path) as conn:
        return bool(conn and conn.execute(
            "SELECT 1 FROM drafts WHERE json_extract(body,'$.status') IN "
            "('QUEUED','RUNNING','WAITING_RESOURCES') LIMIT 1").fetchone())


def next_queued(db_path):
    with connect(db_path) as conn:
        if conn is None or conn.execute(
                "SELECT 1 FROM drafts WHERE json_extract(body,'$.status') IN "
                "('RUNNING','WAITING_RESOURCES') LIMIT 1").fetchone():
            return None
        row = conn.execute("SELECT body FROM drafts WHERE json_extract(body,'$.status')='QUEUED' "
                           "ORDER BY rowid LIMIT 1").fetchone()
        return decode_row(row) if row else None


def queue_full(conn, limit):
    statuses = [row[0] for row in conn.execute(
        "SELECT json_extract(body,'$.status') FROM drafts "
        "WHERE json_extract(body,'$.status') IN ('QUEUED','RUNNING','WAITING_RESOURCES')")]
    return "WAITING_RESOURCES" in statuses or len(statuses) >= limit


def insert_queued(conn, job, limit):
    """Caller owns the write transaction and worker admission lock."""
    row = conn.execute("SELECT body FROM drafts WHERE id=?", (job["id"],)).fetchone()
    if row:
        prior = decode_row(row)
        if prior.get("submitted_brief", prior["brief"]) != job["brief"]:
            raise ValueError("Production ID already belongs to another brief")
        return prior
    if queue_full(conn, limit):
        raise ValueError("Draft queue is full or paused for resources")
    conn.execute("INSERT INTO drafts VALUES (?,?)", (job["id"], json.dumps(job, ensure_ascii=False)))
    return None


def approve_queued(conn, job, limit):
    if queue_full(conn, limit):
        raise ValueError("Hàng đợi production đầy hoặc đang chờ tài nguyên.")
    conn.execute("UPDATE drafts SET body=? WHERE id=?", (json.dumps(job, ensure_ascii=False), job["id"]))


def delete_record(conn, ident):
    conn.execute("DELETE FROM drafts WHERE id=?", (ident,))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='draft_cancellations'").fetchone():
        conn.execute("DELETE FROM draft_cancellations WHERE id=?", (ident,))


def other_waiting(db_path, ident):
    with connect(db_path) as conn:
        return bool(conn and conn.execute(
            "SELECT 1 FROM drafts WHERE id<>? AND json_extract(body,'$.status')="
            "'WAITING_RESOURCES' LIMIT 1", (ident,)).fetchone())
