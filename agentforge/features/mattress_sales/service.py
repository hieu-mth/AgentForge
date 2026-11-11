"""MVP mattress inquiries, quotes, fulfilment and durable notification outbox.

This feature is deliberately independent from the S5 anonymous growth metrics.
All client contact details stay in local SQLite. Reads never create a database;
every mutation requires an Owner acknowledgement. No automatic order, pricing,
delivery, public endpoint, credential storage, message resend or model calls.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentforge.paths import COMPANY_DATA_DIR, ensure_local_root

DB = COMPANY_DATA_DIR / "mattress_sales.sqlite3"
HEX32 = re.compile(r"[a-f0-9]{32}\Z")
REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,79}\Z")
PHONE = re.compile(r"(?:0[0-9]{9,10}|\+84[0-9]{9,10})\Z")
SOURCES = frozenset({"REFERRAL", "WALK_IN", "WEBSITE_IMPORT"})
STATUSES = frozenset({
    "NEW", "CONTACTED", "QUOTED", "OWNER_CONFIRMED",
    "DELIVERY_PLANNED", "DELIVERED", "LOST", "CANCELLED",
})
NEXT = {
    "NEW": {"CONTACTED", "LOST"},
    "CONTACTED": {"QUOTED", "LOST"},
    "QUOTED": {"OWNER_CONFIRMED", "LOST"},
    "OWNER_CONFIRMED": {"DELIVERY_PLANNED", "CANCELLED"},
    "DELIVERY_PLANNED": {"DELIVERED", "CANCELLED"},
    "DELIVERED": set(), "LOST": set(), "CANCELLED": set(),
}
NOTICES = {"PENDING", "DISPATCHING", "SENT", "SENT_MANUAL", "NEEDS_REVIEW"}


class MattressError(ValueError):
    pass


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _text(value, name, limit, *, optional=False):
    if value is None and optional:
        return ""
    if not isinstance(value, str):
        raise MattressError("Invalid " + name)
    value = unicodedata.normalize("NFC", value.strip())
    if (len(value) > limit or (not optional and len(value) < 2)
            or any(ord(ch) < 32 or ord(ch) == 127 or
                   ch in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for ch in value)):
        raise MattressError("Invalid " + name)
    return value


def _id(value):
    if not isinstance(value, str) or not HEX32.fullmatch(value):
        raise MattressError("Invalid identifier")
    return value


def _amount(value, name, *, allow_zero=False):
    if type(value) is not int or not (0 if allow_zero else 1) <= value <= 10**11:
        raise MattressError("Invalid " + name + " in VND")
    return value


def _path(db_path):
    path = Path(db_path) if db_path is not None else DB
    ensure_local_root(path)
    return path


def _connect(db_path=None, *, create=False):
    path = _path(db_path)
    if not create and not path.is_file():
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=15, isolation_level=None)
    else:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                             uri=True, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    if create:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS leads(
                lead_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                payload_sha TEXT NOT NULL,
                source TEXT NOT NULL,
                source_ref TEXT,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                interest TEXT NOT NULL,
                area TEXT NOT NULL,
                consent_to_contact INTEGER NOT NULL CHECK(consent_to_contact=1),
                status TEXT NOT NULL,
                quoted_product TEXT,
                quoted_vnd INTEGER,
                shipping_coverage TEXT NOT NULL DEFAULT 'UNKNOWN',
                shipping_fee_vnd INTEGER,
                shipping_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source, source_ref)
            );
            CREATE TABLE IF NOT EXISTS notices(
                notice_id TEXT PRIMARY KEY,
                lead_id TEXT NOT NULL REFERENCES leads(lead_id),
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(lead_id, kind)
            );
            CREATE TABLE IF NOT EXISTS events(
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id TEXT NOT NULL REFERENCES leads(lead_id),
                at TEXT NOT NULL,
                action TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_leads_updated ON leads(updated_at DESC);
            CREATE INDEX IF NOT EXISTS ix_notices_status ON notices(status,created_at);
        """)
    return db


def _lead_payload(payload):
    if not isinstance(payload, dict) or set(payload) != {
            "request_id", "source", "source_ref", "customer_name", "phone",
            "interest", "area", "consent_to_contact"}:
        raise MattressError("Lead fields are invalid")
    request_id = _id(payload["request_id"])
    source = payload["source"]
    if source not in SOURCES:
        raise MattressError("Invalid lead source")
    source_ref = payload["source_ref"]
    if source_ref is None and source != "WEBSITE_IMPORT":
        pass
    elif not isinstance(source_ref, str) or not REF.fullmatch(source_ref):
        raise MattressError("A trusted source reference is required")
    name = _text(payload["customer_name"], "customer name", 100)
    phone = payload["phone"]
    if not isinstance(phone, str) or not PHONE.fullmatch(phone.strip()):
        raise MattressError("Invalid contact phone")
    interest = _text(payload["interest"], "interest", 160, optional=True)
    area = _text(payload["area"], "area", 100, optional=True)
    if payload["consent_to_contact"] is not True:
        raise PermissionError("Customer permission to be contacted is required")
    normalized = {"request_id": request_id, "source": source,
                  "source_ref": source_ref, "customer_name": name,
                  "phone": phone.strip(), "interest": interest, "area": area,
                  "consent_to_contact": True}
    digest = hashlib.sha256(json.dumps(
        normalized, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return normalized, digest


def _event(db, lead_id, action, old, new):
    db.execute("""INSERT INTO events(lead_id,at,action,from_status,to_status)
                  VALUES(?,?,?,?,?)""", (lead_id, _utc(), action, old, new))


def _notice(db, lead_id, kind):
    now = _utc()
    db.execute("""INSERT OR IGNORE INTO notices
                  (notice_id,lead_id,kind,status,created_at,updated_at)
                  VALUES(?,?,?,'PENDING',?,?)""",
               (uuid4().hex, lead_id, kind, now, now))


def _row(db, lead_id):
    row = db.execute("SELECT * FROM leads WHERE lead_id=?", (_id(lead_id),)).fetchone()
    if row is None:
        raise KeyError("Lead does not exist")
    return row


def _public(row):
    item = dict(row)
    item.pop("payload_sha", None)
    return item


def create_lead(payload, *, confirmed=False, db_path=None):
    if confirmed is not True:
        raise PermissionError("Owner must approve recording a customer's contact")
    fields, digest = _lead_payload(payload)
    db = _connect(db_path, create=True)
    with closing(db):
        db.execute("BEGIN IMMEDIATE")
        try:
            existing = db.execute("SELECT * FROM leads WHERE request_id=?",
                                  (fields["request_id"],)).fetchone()
            if existing is not None:
                if existing["payload_sha"] != digest:
                    raise MattressError("Idempotency key reused for different data")
                db.commit()
                return {"created": False, "lead": _public(existing)}
            if fields["source_ref"] is not None:
                existing = db.execute(
                    "SELECT * FROM leads WHERE source=? AND source_ref=?",
                    (fields["source"], fields["source_ref"])).fetchone()
                if existing is not None:
                    db.commit()
                    return {"created": False, "lead": _public(existing)}
            now, lead_id = _utc(), uuid4().hex
            db.execute("""INSERT INTO leads(lead_id,request_id,payload_sha,source,
                source_ref,customer_name,phone,interest,area,consent_to_contact,
                status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,1,'NEW',?,?)""",
                (lead_id, fields["request_id"], digest, fields["source"],
                 fields["source_ref"], fields["customer_name"], fields["phone"],
                 fields["interest"], fields["area"], now, now))
            _event(db, lead_id, "LEAD_RECORDED", None, "NEW")
            _notice(db, lead_id, "NEW_LEAD")
            db.commit()
            return {"created": True,
                    "lead": get_lead(lead_id, db_path=db_path)}
        except Exception:
            db.rollback()
            raise


def list_leads(*, db_path=None, limit=100):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise MattressError("Invalid page limit")
    db = _connect(db_path)
    if db is None:
        return []
    with closing(db):
        return [_public(row) for row in db.execute(
            "SELECT * FROM leads ORDER BY created_at DESC,lead_id DESC LIMIT ?",
            (limit,)).fetchall()]


def get_lead(lead_id, *, db_path=None):
    _id(lead_id)
    db = _connect(db_path)
    if db is None:
        raise KeyError("Lead does not exist")
    with closing(db):
        return _public(_row(db, lead_id))


def list_notices(*, db_path=None, limit=100):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise MattressError("Invalid notice limit")
    db = _connect(db_path)
    if db is None:
        return []
    with closing(db):
        return [dict(row) for row in db.execute(
            "SELECT notice_id,lead_id,kind,status,created_at,updated_at "
            "FROM notices ORDER BY created_at DESC,notice_id DESC LIMIT ?",
            (limit,))]


def _transition(db, row, desired, action):
    if desired not in NEXT[row["status"]]:
        raise MattressError("Invalid sale status transition")
    now = _utc()
    updated = db.execute(
        "UPDATE leads SET status=?,updated_at=? WHERE lead_id=? AND status=?",
        (desired, now, row["lead_id"], row["status"]))
    if updated.rowcount != 1:
        raise MattressError("Sale state changed; refresh before retry")
    _event(db, row["lead_id"], action, row["status"], desired)
    return now


def change_status(lead_id, desired, *, ack, db_path=None):
    _id(lead_id)
    allowed = {"CONTACTED": "OWNER_CONTACTED_CUSTOMER",
               "DELIVERY_PLANNED": "OWNER_PLANNED_DELIVERY",
               "DELIVERED": "OWNER_CONFIRMED_DELIVERY",
               "LOST": "OWNER_MARKED_LOST",
               "CANCELLED": "OWNER_CANCELLED_ORDER"}
    if desired not in allowed or ack != allowed[desired]:
        raise PermissionError("Explicit Owner status acknowledgement required")
    db = _connect(db_path, create=True)
    with closing(db):
        db.execute("BEGIN IMMEDIATE")
        try:
            row = _row(db, lead_id)
            _transition(db, row, desired, desired)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return get_lead(lead_id, db_path=db_path)


def quote(lead_id, product, price_vnd, *, ack, db_path=None):
    if ack != "OWNER_SET_QUOTE":
        raise PermissionError("Owner must approve the product/quote")
    _id(lead_id)
    product = _text(product, "confirmed product", 140)
    price = _amount(price_vnd, "quoted price")
    db = _connect(db_path, create=True)
    with closing(db):
        db.execute("BEGIN IMMEDIATE")
        try:
            row = _row(db, lead_id)
            if row["status"] != "CONTACTED":
                raise MattressError("Customer must be contacted before quoting")
            db.execute("UPDATE leads SET quoted_product=?,quoted_vnd=? WHERE lead_id=?",
                       (product, price, lead_id))
            _transition(db, row, "QUOTED", "OWNER_QUOTED")
            db.commit()
        except Exception:
            db.rollback()
            raise
    return get_lead(lead_id, db_path=db_path)


def verify_delivery(lead_id, coverage, fee_vnd, note, *, ack, db_path=None):
    if ack != "OWNER_CHECKED_CARRIER":
        raise PermissionError("Owner must verify shipping with the carrier")
    _id(lead_id)
    if coverage not in {"SUPPORTED", "UNSUPPORTED"}:
        raise MattressError("Delivery coverage must be explicitly checked")
    fee = _amount(fee_vnd, "shipping fee", allow_zero=True) if (
        coverage == "SUPPORTED") else None
    if coverage == "UNSUPPORTED" and fee_vnd is not None:
        raise MattressError("Unsupported shipping cannot have a quoted fee")
    note = _text(note, "carrier note", 250)
    db = _connect(db_path, create=True)
    with closing(db):
        db.execute("BEGIN IMMEDIATE")
        try:
            row = _row(db, lead_id)
            if row["status"] != "QUOTED":
                raise MattressError("Quote is required before checking delivery")
            db.execute("""UPDATE leads SET shipping_coverage=?,shipping_fee_vnd=?,
                shipping_note=?,updated_at=? WHERE lead_id=?""",
                       (coverage, fee, note, _utc(), lead_id))
            _event(db, lead_id, "OWNER_VERIFIED_CARRIER", "QUOTED", "QUOTED")
            db.commit()
        except Exception:
            db.rollback()
            raise
    return get_lead(lead_id, db_path=db_path)


def confirm_order(lead_id, *, customer_agreed=False, ack=None, db_path=None):
    if ack != "OWNER_CONFIRM_ORDER" or customer_agreed is not True:
        raise PermissionError("Owner and customer confirmation both required")
    _id(lead_id)
    db = _connect(db_path, create=True)
    with closing(db):
        db.execute("BEGIN IMMEDIATE")
        try:
            row = _row(db, lead_id)
            if (row["status"] != "QUOTED"
                    or row["quoted_vnd"] is None
                    or row["shipping_coverage"] != "SUPPORTED"
                    or row["shipping_fee_vnd"] is None):
                raise MattressError("Verified product, price, shipping area and fee required")
            _transition(db, row, "OWNER_CONFIRMED", "OWNER_CONFIRM_ORDER")
            _notice(db, lead_id, "ORDER_CONFIRMED")
            db.commit()
        except Exception:
            db.rollback()
            raise
    return get_lead(lead_id, db_path=db_path)


def message_for_notice(notice_id, *, db_path=None):
    _id(notice_id)
    db = _connect(db_path)
    if db is None:
        raise KeyError("Notification does not exist")
    with closing(db):
        row = db.execute(
            "SELECT notices.kind,leads.* FROM notices JOIN leads USING(lead_id) "
            "WHERE notices.notice_id=?", (notice_id,)).fetchone()
        if row is None:
            raise KeyError("Notification does not exist")
        # Explicit contact consent was required before storing this record.
        if row["kind"] == "ORDER_CONFIRMED":
            return (f"ĐƠN ĐÃ XÁC NHẬN {row['lead_id'][:8]}\n"
                    f"Khách: {row['customer_name']}\n"
                    f"SĐT: {row['phone']}\n"
                    f"Nệm: {row['quoted_product']}\n"
                    f"Giá đã báo: {row['quoted_vnd']:,} VND\n"
                    f"Phí giao hàng đã xác minh: {row['shipping_fee_vnd']:,} VND\n"
                    "Owner cần phối hợp vận chuyển; không tự tạo vận đơn.")
        return (f"KHÁCH HỎI MUA NỆM {row['lead_id'][:8]}\n"
                f"Khách: {row['customer_name']}\n"
                f"SĐT: {row['phone']}\n"
                f"Quan tâm: {row['interest'] or 'Chưa xác định'}\n"
                f"Khu vực: {row['area'] or 'Chưa xác định'}\n"
                "Chưa có đơn hoặc giao hàng được xác nhận.")


def mark_notified(notice_id, *, ack, db_path=None):
    if ack != "OWNER_ATTEST_ACTUALLY_NOTIFIED":
        raise PermissionError("Owner must attest the message was actually sent")
    _id(notice_id)
    db = _connect(db_path, create=True)
    with closing(db):
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT lead_id,status FROM notices WHERE notice_id=?",
                             (notice_id,)).fetchone()
            if row is None:
                raise KeyError("Notification does not exist")
            if row["status"] not in ("PENDING", "NEEDS_REVIEW", "DISPATCHING"):
                raise MattressError("Cannot mark notification in this state")
            db.execute("UPDATE notices SET status='SENT_MANUAL',updated_at=? "
                       "WHERE notice_id=?", (_utc(), notice_id))
            _event(db, row["lead_id"], "OWNER_ATTESTED_MANUAL_NOTICE", None, None)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"notice_id": notice_id, "status": "SENT_MANUAL"}


def claim_notice(notice_id, *, ack, db_path=None):
    if ack != "OWNER_AUTHORIZE_EXTERNAL_MESSAGE":
        raise PermissionError("External message requires explicit Owner authorization")
    _id(notice_id)
    db = _connect(db_path, create=True)
    with closing(db):
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT lead_id,status FROM notices WHERE notice_id=?",
                             (notice_id,)).fetchone()
            if row is None or row["status"] != "PENDING":
                raise MattressError("Notification not pending; no automatic retry")
            changed = db.execute(
                "UPDATE notices SET status='DISPATCHING',updated_at=? "
                "WHERE notice_id=? AND status='PENDING'", (_utc(), notice_id))
            if changed.rowcount != 1:
                raise MattressError("Notification claimed elsewhere")
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"notice_id": notice_id, "status": "DISPATCHING"}


def finish_notice(notice_id, *, confirmed_delivered=False, db_path=None):
    _id(notice_id)
    db = _connect(db_path, create=True)
    with closing(db):
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT lead_id,status FROM notices WHERE notice_id=?",
                             (notice_id,)).fetchone()
            if row is None or row["status"] != "DISPATCHING":
                raise MattressError("Notification is not in dispatch state")
            status = "SENT" if confirmed_delivered is True else "NEEDS_REVIEW"
            db.execute("UPDATE notices SET status=?,updated_at=? WHERE notice_id=?",
                       (status, _utc(), notice_id))
            _event(db, row["lead_id"], "EXTERNAL_DELIVERY_"+status, None, None)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"notice_id": notice_id, "status": status}


def summary(*, db_path=None):
    db = _connect(db_path)
    if db is None:
        return {"total": 0, "statuses": {}, "pending_notices": 0,
                "needs_review_notices": 0, "confirmed_orders": 0}
    with closing(db):
        counts = {r["status"]: r["n"] for r in db.execute(
            "SELECT status,COUNT(*) n FROM leads GROUP BY status")}
        notices = {r["status"]: r["n"] for r in db.execute(
            "SELECT status,COUNT(*) n FROM notices GROUP BY status")}
        return {"total": sum(counts.values()), "statuses": counts,
                "pending_notices": notices.get("PENDING", 0),
                "needs_review_notices": (notices.get("NEEDS_REVIEW", 0)
                                         + notices.get("DISPATCHING", 0)),
                "confirmed_orders": sum(counts.get(key, 0) for key in (
                    "OWNER_CONFIRMED", "DELIVERY_PLANNED", "DELIVERED"))}


def report(*, db_path=None):
    return {"summary": summary(db_path=db_path),
            "leads": list_leads(db_path=db_path),
            "notices": list_notices(db_path=db_path),
            "public_ingress": "NOT_CONNECTED",
            "automatic_messaging": "OPT_IN_ONLY",
            "shipping_coverage_default": "UNKNOWN",
            "production_checkout": False}
