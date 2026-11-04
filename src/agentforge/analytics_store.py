"""S3 verified-source-aware *local* analytics ingestion and storage.

CSV is user-supplied evidence, not a trusted platform API or proof of payment.
All imports are atomic, idempotent by file SHA, and reject overlapping daily
performance keys or duplicate financial transactions (no silent overwrite).
"""
import csv
import hashlib
import io
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "workspace" / "analytics" / "inbox"
DB = ROOT / "data" / "company" / "s3_analytics.sqlite3"
DATASET = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
FILENAME = re.compile(r"[a-z][a-z0-9_-]{1,59}\.csv\Z")
IDENT = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{1,49}\Z")
REF = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_./:-]{1,119}\Z")
CHANNELS = {"youtube", "tiktok", "website", "affiliate", "other"}
SOURCE_KINDS = {"manual", "user_platform_export"}
PERF_COLUMNS = ("date", "campaign", "channel", "content", "variant",
                "impressions", "views", "clicks", "leads", "orders",
                "watch_seconds")
LEDGER_COLUMNS = ("tx_id", "date", "campaign", "kind", "status",
                  "amount_vnd", "evidence_ref")
MAX_BYTES, MAX_ROWS = 1_000_000, 2000


class AnalyticsError(ValueError):
    pass


def _safe_path(path):
    for node in (path, *path.parents):
        if node.is_symlink() or (hasattr(node, "is_junction") and node.is_junction()):
            raise AnalyticsError("Symlink or junction paths are forbidden")


def _name(value, pattern, label):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise AnalyticsError(f"Invalid {label}")
    return value


def _day(raw):
    if not isinstance(raw, str):
        raise AnalyticsError("Invalid observation date")
    try:
        value = date.fromisoformat(raw)
    except ValueError as exc:
        raise AnalyticsError("Date must be YYYY-MM-DD") from exc
    if value.isoformat() != raw or not (date(2020, 1, 1) <= value <= date.today()):
        raise AnalyticsError("Date must be a valid past/current ISO date")
    return raw


def _int(raw, field, maximum=10**12):
    if not isinstance(raw, str) or not re.fullmatch(r"0|[1-9][0-9]*", raw):
        raise AnalyticsError(f"{field} must be a nonnegative integer")
    value = int(raw)
    if value > maximum:
        raise AnalyticsError(f"{field} exceeds allowed range")
    return value


def _csv_rows(filename, kind):
    _name(filename, FILENAME, "CSV filename")
    if kind not in ("performance", "ledger"):
        raise AnalyticsError("Unsupported dataset kind")
    path = INBOX / filename
    _safe_path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise AnalyticsError("Input CSV missing or exceeds 1 MB")
    raw = path.read_bytes()
    try:
        body = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise AnalyticsError("CSV must be UTF-8") from exc
    try:
        reader = csv.DictReader(io.StringIO(body, newline=""), strict=True)
        columns = PERF_COLUMNS if kind == "performance" else LEDGER_COLUMNS
        if reader.fieldnames is None or tuple(reader.fieldnames) != columns:
            raise AnalyticsError(f"Expected CSV header: {','.join(columns)}")
        rows = []
        seen = set()
        for i, item in enumerate(reader, 1):
            if i > MAX_ROWS:
                raise AnalyticsError("CSV exceeds 2000 rows")
            if None in item or any(v is None for v in item.values()):
                raise AnalyticsError(f"CSV row {i} has missing/extra columns")
            if kind == "performance":
                row = _performance(item)
                key = tuple(row[k] for k in ("date", "campaign", "channel",
                                             "content", "variant"))
            else:
                row = _ledger(item)
                key = row["tx_id"]
            if key in seen:
                raise AnalyticsError("Duplicate observation or transaction within CSV")
            seen.add(key)
            rows.append(row)
        if not rows:
            raise AnalyticsError("CSV contains no records")
    except csv.Error as exc:
        raise AnalyticsError("Malformed CSV") from exc
    return rows, hashlib.sha256(raw).hexdigest()


def _performance(row):
    output = {
        "date": _day(row["date"]),
        "campaign": _name(row["campaign"], IDENT, "campaign ID"),
        "channel": row["channel"],
        "content": _name(row["content"], IDENT, "content ID"),
        "variant": _name(row["variant"], IDENT, "variant"),
    }
    if output["channel"] not in CHANNELS:
        raise AnalyticsError("Unsupported channel")
    for key in PERF_COLUMNS[5:]:
        output[key] = _int(row[key], key)
    return output


def _ledger(row):
    output = {
        "tx_id": _name(row["tx_id"], IDENT, "transaction ID"),
        "date": _day(row["date"]),
        "campaign": _name(row["campaign"], IDENT, "campaign ID"),
        "kind": row["kind"], "status": row["status"],
        "amount_vnd": _int(row["amount_vnd"], "amount_vnd", 10**13),
        "evidence_ref": row["evidence_ref"],
    }
    if output["kind"] not in ("revenue", "cost"):
        raise AnalyticsError("Ledger kind must be revenue or cost")
    if output["status"] not in ("pending", "owner_confirmed"):
        raise AnalyticsError("Ledger status must be pending or owner_confirmed")
    if output["status"] == "owner_confirmed":
        _name(output["evidence_ref"], REF, "owner-entered evidence reference")
    elif output["evidence_ref"] and not REF.fullmatch(output["evidence_ref"]):
        raise AnalyticsError("Invalid evidence reference")
    return output


def _connect(db_path=None, *, create=False):
    path = Path(db_path) if db_path is not None else DB
    _safe_path(path)
    if not create and not path.is_file():
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if create:
        conn.executescript("""
          CREATE TABLE IF NOT EXISTS datasets(
            dataset TEXT PRIMARY KEY, synthetic INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS imports(
            import_id TEXT PRIMARY KEY, dataset TEXT NOT NULL REFERENCES datasets(dataset),
            kind TEXT NOT NULL, filename TEXT NOT NULL, source_kind TEXT NOT NULL,
            sha256 TEXT NOT NULL, imported_at TEXT NOT NULL, row_count INTEGER NOT NULL,
            UNIQUE(dataset,kind,sha256));
          CREATE TABLE IF NOT EXISTS performance(
            dataset TEXT NOT NULL REFERENCES datasets(dataset),
            import_id TEXT NOT NULL REFERENCES imports(import_id),
            date TEXT NOT NULL, campaign TEXT NOT NULL, channel TEXT NOT NULL,
            content TEXT NOT NULL, variant TEXT NOT NULL,
            impressions INTEGER NOT NULL, views INTEGER NOT NULL, clicks INTEGER NOT NULL,
            leads INTEGER NOT NULL, orders INTEGER NOT NULL, watch_seconds INTEGER NOT NULL,
            UNIQUE(dataset,date,campaign,channel,content,variant));
          CREATE TABLE IF NOT EXISTS ledger(
            dataset TEXT NOT NULL REFERENCES datasets(dataset),
            import_id TEXT NOT NULL REFERENCES imports(import_id),
            tx_id TEXT NOT NULL, date TEXT NOT NULL, campaign TEXT NOT NULL,
            kind TEXT NOT NULL, status TEXT NOT NULL, amount_vnd INTEGER NOT NULL,
            evidence_ref TEXT NOT NULL, UNIQUE(dataset,tx_id));
          CREATE INDEX IF NOT EXISTS ix_perf_campaign ON performance(dataset,campaign);
          CREATE INDEX IF NOT EXISTS ix_ledger_campaign ON ledger(dataset,campaign);
        """)
        conn.commit()
    return conn


def import_csv(dataset, kind, filename, *, source_kind="manual",
               synthetic=False, confirm_write=False, db_path=None):
    """Owner-approved CSV import, all-or-nothing with repeated-SHA no-op."""
    if confirm_write is not True:
        raise PermissionError("Import requires explicit owner confirmation")
    _name(dataset, DATASET, "dataset")
    if source_kind not in SOURCE_KINDS or type(synthetic) is not bool:
        raise AnalyticsError("Invalid provenance or synthetic flag")
    rows, digest = _csv_rows(filename, kind)  # validate before any DB writes
    with closing(_connect(db_path, create=True)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT synthetic FROM datasets WHERE dataset=?", (dataset,)
            ).fetchone()
            if existing is not None and bool(existing["synthetic"]) != synthetic:
                raise AnalyticsError("Cannot mix demo and non-demo sources in one dataset")
            if existing is None:
                conn.execute("INSERT INTO datasets VALUES (?,?)", (dataset, int(synthetic)))
            prior = conn.execute(
                "SELECT import_id,row_count FROM imports WHERE dataset=? AND kind=? AND sha256=?",
                (dataset, kind, digest)
            ).fetchone()
            if prior:
                conn.commit()
                return {"status": "ALREADY_IMPORTED", "dataset": dataset,
                        "import_id": prior["import_id"], "rows": prior["row_count"],
                        "source_sha256": digest, "synthetic": synthetic}
            import_id, now = uuid4().hex, datetime.now(timezone.utc).isoformat()
            conn.execute("INSERT INTO imports VALUES (?,?,?,?,?,?,?,?)",
                         (import_id, dataset, kind, filename, source_kind,
                          digest, now, len(rows)))
            if kind == "performance":
                conn.executemany(
                    "INSERT INTO performance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(dataset, import_id, *(row[key] for key in PERF_COLUMNS))
                     for row in rows])
            else:
                conn.executemany(
                    "INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?,?)",
                    [(dataset, import_id, *(row[key] for key in LEDGER_COLUMNS))
                     for row in rows])
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise AnalyticsError(
                "Duplicate observation/transaction across imports; no rows inserted"
            ) from exc
        except Exception:
            conn.rollback()
            raise
    return {"status": "IMPORTED", "dataset": dataset, "import_id": import_id,
            "rows": len(rows), "source_sha256": digest, "synthetic": synthetic}


def load_data(dataset, *, campaign=None, db_path=None):
    _name(dataset, DATASET, "dataset")
    if campaign is not None:
        _name(campaign, IDENT, "campaign")
    conn = _connect(db_path)
    if conn is None:
        raise AnalyticsError("No analytics dataset has been imported")
    with closing(conn):
        meta = conn.execute(
            "SELECT synthetic FROM datasets WHERE dataset=?", (dataset,)
        ).fetchone()
        if meta is None:
            raise AnalyticsError("Dataset not found")
        imports = [dict(x) for x in conn.execute(
            "SELECT kind,filename,source_kind,sha256,imported_at,row_count "
            "FROM imports WHERE dataset=? ORDER BY imported_at,import_id",
            (dataset,))]
        where = "dataset=?"
        params = [dataset]
        if campaign is not None:
            where += " AND campaign=?"
            params.append(campaign)
        performance = [dict(x) for x in conn.execute(
            "SELECT date,campaign,channel,content,variant,impressions,views,clicks,"
            "leads,orders,watch_seconds FROM performance WHERE " + where +
            " ORDER BY date,channel,content,variant", params)]
        ledger = [dict(x) for x in conn.execute(
            "SELECT date,campaign,kind,status,amount_vnd FROM ledger WHERE " + where +
            " ORDER BY date,tx_id", params)]
    return {"dataset": dataset, "campaign": campaign,
            "synthetic": bool(meta["synthetic"]), "imports": imports,
            "performance": performance, "ledger": ledger}


def list_datasets(*, db_path=None):
    conn = _connect(db_path)
    if conn is None:
        return []
    with closing(conn):
        return [dict(row) for row in conn.execute("""
            SELECT d.dataset,d.synthetic,
              (SELECT COUNT(*) FROM performance p WHERE p.dataset=d.dataset) AS performance_rows,
              (SELECT COUNT(*) FROM ledger l WHERE l.dataset=d.dataset) AS ledger_rows
            FROM datasets d ORDER BY d.dataset LIMIT 50
        """)]
