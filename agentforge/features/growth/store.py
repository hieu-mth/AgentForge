"""S5 local, single-owner growth records: campaigns, lead states, handoffs and cash.

All platform/post/payment evidence is OWNER-ATTESTED and NOT externally
verified. No client contact details, credentials, phone numbers or payment
identifiers are accepted by the schema. No network or publishing actions.
"""
import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from agentforge.paths import REPOSITORY_ROOT
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = REPOSITORY_ROOT
DB = ROOT / "data" / "company" / "s5_growth.sqlite3"
CAMPAIGN = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
KEY = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,63}\Z")
REF = re.compile(r"[A-Za-z][A-Za-z0-9_./:-]{2,119}\Z")
UUID = re.compile(r"[0-9a-f]{32}\Z")
CHANNELS = {"youtube", "tiktok", "website", "affiliate", "other"}
LEAD_TRANSITIONS = {
    "NEW": {"CONTACTED", "QUALIFIED", "LOST"},
    "CONTACTED": {"QUALIFIED", "LOST"},
    "QUALIFIED": {"WON", "LOST"},
    "WON": set(), "LOST": set(),
}


class GrowthError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe(path):
    for node in (path, *path.parents):
        if node.is_symlink() or (hasattr(node, "is_junction") and node.is_junction()):
            raise GrowthError("Symlink/junction paths are forbidden")


def _identifier(value, regex, label):
    if not isinstance(value, str) or not regex.fullmatch(value):
        raise GrowthError(f"Invalid {label}")
    return value


def _text(value, *, max_length, field):
    if not isinstance(value, str):
        raise GrowthError(f"Invalid {field}")
    value = unicodedata.normalize("NFC", value.strip())
    if not 3 <= len(value) <= max_length or any(ord(c) < 32 for c in value):
        raise GrowthError(f"Invalid {field} text or length")
    return value


def _amount(value):
    if type(value) is not int or not 0 < value <= 10**13:
        raise GrowthError("Amount must be a positive integer in VND")
    return value


def _url(channel, url):
    """Accept canonical public evidence URLs, not a URL fetch directive."""
    if channel not in {"youtube", "tiktok"} or not isinstance(url, str):
        raise GrowthError("Unsupported published channel or URL")
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.username or parts.password or parts.port
            or parts.query or parts.fragment or parts.hostname is None
            or parts.netloc != parts.hostname or len(url) > 300):
        raise GrowthError("Only canonical HTTPS post permalinks without query allowed")
    host, path = parts.hostname, parts.path
    if channel == "youtube":
        if host in {"youtube.com", "www.youtube.com"} and re.fullmatch(
                r"/shorts/[A-Za-z0-9_-]{6,32}", path):
            return url
        if host == "youtu.be" and re.fullmatch(r"/[A-Za-z0-9_-]{6,32}", path):
            return url
    if channel == "tiktok" and host in {"tiktok.com", "www.tiktok.com"}:
        if re.fullmatch(r"/@[A-Za-z0-9_.-]{2,32}/video/[0-9]{8,32}", path):
            return url
    raise GrowthError("Unsupported post permalink path/domain")


def _connect(db_path=None, *, create=False):
    path = Path(db_path) if db_path is not None else DB
    _safe(path)
    if not create and not path.is_file():
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    if create:
        db.executescript("""
          CREATE TABLE IF NOT EXISTS campaigns(
            campaign TEXT PRIMARY KEY, title TEXT NOT NULL,
            analytics_dataset TEXT, budget_vnd INTEGER NOT NULL,
            synthetic INTEGER NOT NULL, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS packages(
            package_id TEXT PRIMARY KEY,
            campaign TEXT NOT NULL REFERENCES campaigns(campaign),
            channel TEXT NOT NULL, media_run_id TEXT NOT NULL,
            package_path TEXT NOT NULL, sha256 TEXT NOT NULL,
            source_video_sha256 TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(campaign,channel,media_run_id));
          CREATE TABLE IF NOT EXISTS posts(
            package_id TEXT PRIMARY KEY REFERENCES packages(package_id),
            channel TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
            owner_attested_at TEXT NOT NULL, externally_verified INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS leads(
            lead_id TEXT PRIMARY KEY,
            campaign TEXT NOT NULL REFERENCES campaigns(campaign),
            channel TEXT NOT NULL, status TEXT NOT NULL,
            consent_attested INTEGER NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS money(
            campaign TEXT NOT NULL REFERENCES campaigns(campaign),
            tx_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL,
            amount_vnd INTEGER NOT NULL, evidence_ref TEXT NOT NULL,
            s3_tx_id TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(campaign,tx_id));
          CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign TEXT NOT NULL REFERENCES campaigns(campaign),
            kind TEXT NOT NULL, at TEXT NOT NULL,
            record_ref TEXT NOT NULL, detail_json TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS ix_leads_campaign ON leads(campaign,status);
          CREATE INDEX IF NOT EXISTS ix_money_campaign ON money(campaign,kind,status);
          CREATE UNIQUE INDEX IF NOT EXISTS ux_money_s3_tx
            ON money(campaign,s3_tx_id) WHERE s3_tx_id<>'';
        """)
        db.commit()
    return db


def campaign_info(campaign, *, db_path=None):
    _identifier(campaign, CAMPAIGN, "campaign")
    db = _connect(db_path)
    if db is None:
        raise GrowthError("Campaign does not exist")
    with closing(db):
        row = db.execute("SELECT * FROM campaigns WHERE campaign=?", (campaign,)).fetchone()
        if row is None:
            raise GrowthError("Campaign does not exist")
        return dict(row)


def list_campaigns(*, db_path=None, limit=30):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise GrowthError("Invalid limit")
    db = _connect(db_path)
    if db is None:
        return []
    with closing(db):
        return [dict(x) for x in db.execute(
            "SELECT * FROM campaigns ORDER BY created_at DESC,campaign LIMIT ?", (limit,))]


def create_campaign(payload, *, confirm_write=False, db_path=None,
                    analytics_db_path=None):
    if confirm_write is not True:
        raise PermissionError("Owner confirmation required to create a campaign")
    if not isinstance(payload, dict) or set(payload) != {
            "campaign", "title", "analytics_dataset", "budget_vnd", "synthetic"}:
        raise GrowthError("Campaign schema mismatch")
    campaign = _identifier(payload["campaign"], CAMPAIGN, "campaign")
    title = _text(payload["title"], max_length=120, field="title")
    budget = payload["budget_vnd"]
    if type(budget) is not int or not 0 <= budget <= 10**13:
        raise GrowthError("Invalid VND bookkeeping budget")
    synthetic = payload["synthetic"]
    if type(synthetic) is not bool:
        raise GrowthError("Synthetic must be boolean")
    dataset = payload["analytics_dataset"]
    if not isinstance(dataset, str) or len(dataset) > 40:
        raise GrowthError("Invalid analytics dataset")
    if dataset:
        from agentforge import analytics_store
        records = analytics_store.load_data(dataset, db_path=analytics_db_path)
        if records["synthetic"] is not synthetic:
            raise GrowthError("S3 dataset provenance conflicts with campaign")
    with closing(_connect(db_path, create=True)) as db, db:
        try:
            db.execute("INSERT INTO campaigns VALUES (?,?,?,?,?,?)",
                       (campaign, title, dataset or None, budget, int(synthetic), _now()))
            db.execute("INSERT INTO events(campaign,kind,at,record_ref,detail_json) "
                       "VALUES(?,?,?,?,?)", (campaign, "CAMPAIGN_CREATED", _now(),
                                            campaign, "{}"))
        except sqlite3.IntegrityError as exc:
            raise GrowthError("Campaign already exists; no overwrite") from exc
    return {"campaign": campaign, "status": "CREATED",
            "synthetic": synthetic, "budget_vnd": budget,
            "analytics_dataset": dataset, "publishing_authorized": False,
            "spending_authorized": False}


def save_package(campaign, channel, run_id, path, sha256, source_sha256,
                 *, db_path=None):
    """Called ONLY after pack has been built and checked; idempotent by media."""
    _identifier(campaign, CAMPAIGN, "campaign")
    if channel not in {"youtube", "tiktok"}:
        raise GrowthError("Unsupported channel")
    _identifier(run_id, UUID, "media run")
    _identifier(sha256, re.compile(r"[a-f0-9]{64}\Z"), "package hash")
    _identifier(source_sha256, re.compile(r"[a-f0-9]{64}\Z"), "video hash")
    package_id = uuid4().hex
    with closing(_connect(db_path, create=True)) as db, db:
        try:
            db.execute("INSERT INTO packages VALUES (?,?,?,?,?,?,?,?,?)",
                       (package_id, campaign, channel, run_id, str(path), sha256,
                        source_sha256, "READY_FOR_OWNER_UPLOAD", _now()))
            db.execute("INSERT INTO events(campaign,kind,at,record_ref,detail_json) "
                       "VALUES(?,?,?,?,?)", (campaign, "BUNDLE_PREPARED", _now(),
                                            package_id, "{}"))
        except sqlite3.IntegrityError as exc:
            raise GrowthError("Package for this campaign/channel/media already exists") from exc
    return {"package_id": package_id, "campaign": campaign,
            "channel": channel, "status": "READY_FOR_OWNER_UPLOAD",
            "archive_path": str(path), "sha256": sha256,
            "published": False, "externally_verified": False}


def find_package(package_id, *, db_path=None):
    _identifier(package_id, UUID, "package ID")
    db = _connect(db_path)
    if db is None:
        raise GrowthError("Package not found")
    with closing(db):
        row = db.execute("SELECT * FROM packages WHERE package_id=?",
                         (package_id,)).fetchone()
        if row is None:
            raise GrowthError("Package not found")
        return dict(row)


def _event_payload(kind, data):
    if not isinstance(data, dict):
        raise GrowthError("Record data must be an object")
    required = {
        "lead_new": {"campaign", "channel", "consent_confirmed"},
        "lead_status": {"lead_id", "status"},
        "post_attest": {"package_id", "url", "confirm_owner_posted"},
        "money": {"campaign", "tx_id", "kind", "status", "amount_vnd",
                  "evidence_ref", "s3_tx_id"},
    }
    if kind not in required or set(data) != required[kind]:
        raise GrowthError("Event kind/schema mismatch")
    return data


def validate_event_payload(kind, data):
    """Reject PII-shaped/unsafe event input BEFORE S1 Task History persists it.

    Campaign/lead references and channel URLs are opaque metadata, not
    private customer contact information. Nested payload schema is strict.
    """
    _event_payload(kind, data)
    if kind == "lead_new":
        _identifier(data["campaign"], CAMPAIGN, "campaign")
        if data["channel"] not in CHANNELS or data["consent_confirmed"] is not True:
            raise GrowthError("Source and explicit consent attestation required")
    elif kind == "lead_status":
        _identifier(data["lead_id"], UUID, "lead ID")
        if data["status"] not in {"CONTACTED", "QUALIFIED", "WON", "LOST"}:
            raise GrowthError("Unsupported lead status")
    elif kind == "post_attest":
        _identifier(data["package_id"], UUID, "package ID")
        if data["confirm_owner_posted"] is not True:
            raise PermissionError("Owner must explicitly attest external manual upload")
        # Full channel/permalink validation needs the associated package.
        if not isinstance(data["url"], str) or len(data["url"]) > 300:
            raise GrowthError("Invalid post URL")
        parsed = urlsplit(data["url"])
        if parsed.scheme != "https" or parsed.hostname not in {
            "youtube.com", "www.youtube.com", "youtu.be",
            "tiktok.com", "www.tiktok.com"
        } or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise GrowthError("Only public, canonical platform URLs allowed")
    else:
        _identifier(data["campaign"], CAMPAIGN, "campaign")
        _identifier(data["tx_id"], KEY, "transaction ID")
        if data["kind"] not in {"commission", "cost"} or data["status"] not in {
            "pending", "owner_confirmed"
        }:
            raise GrowthError("Invalid financial kind/status")
        _amount(data["amount_vnd"])
        evidence, s3_tx_id = data["evidence_ref"], data["s3_tx_id"]
        if not isinstance(evidence, str) or not isinstance(s3_tx_id, str):
            raise GrowthError("Invalid financial provenance")
        if data["status"] == "owner_confirmed":
            _identifier(evidence, REF, "owner evidence")
        elif evidence and not REF.fullmatch(evidence):
            raise GrowthError("Invalid pending evidence")
        if s3_tx_id:
            _identifier(s3_tx_id, KEY, "S3 transaction ID")
    return data


def record_event(kind, data, *, confirm_write=False, db_path=None):
    """Manual business events with hard record schemas; never contact customers."""
    if confirm_write is not True:
        raise PermissionError("Owner confirmation required to record events")
    data = validate_event_payload(kind, data)
    if kind == "lead_new":
        campaign = _identifier(data["campaign"], CAMPAIGN, "campaign")
        if data["channel"] not in CHANNELS or data["consent_confirmed"] is not True:
            raise GrowthError("Source and explicit consent attestation required")
        with closing(_connect(db_path, create=True)) as db, db:
            if db.execute("SELECT 1 FROM campaigns WHERE campaign=?",
                          (campaign,)).fetchone() is None:
                raise GrowthError("Campaign not found")
            lid, now = uuid4().hex, _now()
            db.execute("INSERT INTO leads VALUES (?,?,?,?,?,?,?)",
                       (lid, campaign, data["channel"], "NEW", 1, now, now))
            db.execute("INSERT INTO events(campaign,kind,at,record_ref,detail_json)"
                       " VALUES(?,?,?,?,?)", (campaign, "LEAD_NEW", now, lid, "{}"))
        return {"status": "RECORDED", "kind": "lead_new", "campaign": campaign,
                "lead_id": lid, "lead_status": "NEW", "personal_data_stored": False}
    if kind == "lead_status":
        lid = _identifier(data["lead_id"], UUID, "lead ID")
        target = data["status"]
        if target not in {"CONTACTED", "QUALIFIED", "WON", "LOST"}:
            raise GrowthError("Unsupported lead status")
        with closing(_connect(db_path, create=True)) as db, db:
            row = db.execute("SELECT campaign,status FROM leads WHERE lead_id=?",
                             (lid,)).fetchone()
            if row is None or target not in LEAD_TRANSITIONS[row["status"]]:
                raise GrowthError("Invalid lead state transition")
            changed = db.execute("UPDATE leads SET status=?,updated_at=? "
                                 "WHERE lead_id=? AND status=?",
                                 (target, _now(), lid, row["status"]))
            if changed.rowcount != 1:
                raise GrowthError("Lead status changed concurrently")
            db.execute("INSERT INTO events(campaign,kind,at,record_ref,detail_json)"
                       " VALUES(?,?,?,?,?)", (row["campaign"], "LEAD_"+target,
                                              _now(), lid, "{}"))
        return {"status": "RECORDED", "kind": kind, "lead_id": lid,
                "lead_status": target, "personal_data_stored": False}
    if kind == "post_attest":
        pack = find_package(data["package_id"], db_path=db_path)
        if data["confirm_owner_posted"] is not True:
            raise PermissionError("Owner must explicitly attest external manual upload")
        public_url = _url(pack["channel"], data["url"])
        with closing(_connect(db_path, create=True)) as db, db:
            try:
                db.execute("INSERT INTO posts VALUES (?,?,?,?,0)",
                           (pack["package_id"], pack["channel"], public_url, _now()))
                db.execute("UPDATE packages SET status='OWNER_REPORTED_POSTED' "
                           "WHERE package_id=? AND status='READY_FOR_OWNER_UPLOAD'",
                           (pack["package_id"],))
                db.execute("INSERT INTO events(campaign,kind,at,record_ref,detail_json)"
                           " VALUES(?,?,?,?,?)", (pack["campaign"], "POST_ATTESTED",
                                                  _now(), pack["package_id"], "{}"))
            except sqlite3.IntegrityError as exc:
                raise GrowthError("Duplicate post URL/package; no overwrite") from exc
        return {"status": "OWNER_REPORTED_POSTED", "kind": kind,
                "package_id": pack["package_id"], "channel": pack["channel"],
                "external_publication_verified": False, "platform_api_used": False}
    # Manual commission/cost ledger. No actual bank/payment action.
    campaign = _identifier(data["campaign"], CAMPAIGN, "campaign")
    tx_id = _identifier(data["tx_id"], KEY, "transaction ID")
    if data["kind"] not in {"commission", "cost"} or data["status"] not in {
            "pending", "owner_confirmed"}:
        raise GrowthError("Invalid financial kind/status")
    amount = _amount(data["amount_vnd"])
    evidence = data["evidence_ref"]
    s3_tx_id = data["s3_tx_id"]
    if not isinstance(evidence, str) or not isinstance(s3_tx_id, str):
        raise GrowthError("Invalid financial provenance")
    if data["status"] == "owner_confirmed":
        _identifier(evidence, REF, "owner evidence")
    elif evidence and not REF.fullmatch(evidence):
        raise GrowthError("Invalid pending evidence")
    if s3_tx_id:
        _identifier(s3_tx_id, KEY, "S3 transaction ID")
    with closing(_connect(db_path, create=True)) as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT budget_vnd FROM campaigns WHERE campaign=?",
                             (campaign,)).fetchone()
            if row is None:
                raise GrowthError("Campaign not found")
            if data["kind"] == "cost":
                booked = db.execute(
                    "SELECT COALESCE(SUM(amount_vnd),0) FROM money "
                    "WHERE campaign=? AND kind='cost'", (campaign,)).fetchone()[0]
                if booked + amount > row["budget_vnd"]:
                    raise GrowthError("Owner bookkeeping cost cap exceeded; no record written")
            try:
                db.execute("INSERT INTO money VALUES (?,?,?,?,?,?,?,?)",
                           (campaign, tx_id, data["kind"], data["status"],
                            amount, evidence, s3_tx_id, _now()))
            except sqlite3.IntegrityError as exc:
                raise GrowthError("Duplicate transaction ID; no overwrite") from exc
            db.execute("INSERT INTO events(campaign,kind,at,record_ref,detail_json) "
                       "VALUES(?,?,?,?,?)",
                       (campaign, "FINANCIAL_"+data["kind"].upper(), _now(), tx_id, "{}"))
    return {"status": "RECORDED", "kind": "money", "campaign": campaign,
            "tx_id": tx_id, "amount_vnd": amount,
            "owner_recorded_only": True, "bank_reconciled": False,
            "payment_executed": False}


def load_campaign(campaign, *, db_path=None):
    info = campaign_info(campaign, db_path=db_path)
    with closing(_connect(db_path)) as db:
        leads = [dict(x) for x in db.execute(
            "SELECT lead_id,channel,status,created_at FROM leads WHERE campaign=? "
            "ORDER BY created_at,lead_id", (campaign,))]
        packages = [dict(x) for x in db.execute(
            "SELECT package_id,channel,media_run_id,sha256,status,created_at,"
            "source_video_sha256,package_path FROM packages WHERE campaign=? "
            "ORDER BY created_at,package_id", (campaign,))]
        posts = [dict(x) for x in db.execute(
            "SELECT p.package_id,p.channel,p.externally_verified FROM posts p "
            "JOIN packages b ON b.package_id=p.package_id WHERE b.campaign=?",
            (campaign,))]
        money = [dict(x) for x in db.execute(
            "SELECT tx_id,kind,status,amount_vnd,s3_tx_id FROM money "
            "WHERE campaign=? ORDER BY created_at,tx_id", (campaign,))]
        events = [dict(x) for x in db.execute(
            "SELECT kind,at,record_ref FROM events WHERE campaign=? ORDER BY id",
            (campaign,))]
    return {"campaign": info, "leads": leads, "packages": packages,
            "posts": posts, "money": money, "events": events}
