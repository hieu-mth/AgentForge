"""Wave 10: SHA-bound local Film Studio release ledger and Owner observations.

No automatic posting, public visibility changes, billing, monetization claims,
cloud API calls or timers. The optional YouTube private-only upload adapter
lives separately and always uses a one-shot, checkpointed Owner action.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from agentforge.features.film_studio import production
from agentforge.paths import COMPANY_DATA_DIR, ensure_local_root

DB = COMPANY_DATA_DIR / "film_publishing.sqlite3"
RELEASE_FORMAT = "agentforge.film.release.v1"
IDENT = re.compile(r"[a-f0-9]{32}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
VIDEO = re.compile(r"[A-Za-z0-9_-]{11}\Z")
STATES = {
    "READY_FOR_MANUAL_HANDOFF", "UPLOAD_ATTEMPT_UNCERTAIN",
    "PRIVATE_UPLOADED_API", "OWNER_REPORTED_PRIVATE",
    "OWNER_REPORTED_UNLISTED", "OWNER_REPORTED_PUBLIC",
    "OWNER_REPORTED_SCHEDULED",
}
MAX_OBSERVATIONS = 120


class PublishingError(ValueError):
    """Owner review/metadata/ledger refusal; never leaks credentials."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _digest(body):
    return _sha(json.dumps(body, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _text(value, label, maximum, *, minimum=1):
    if (not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum
            or any(ord(c) < 32 for c in value)):
        raise PublishingError("Invalid " + label)
    return value.strip()


def _id(value, kind="release ID"):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise PublishingError("Invalid " + kind)
    return value


def _date(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise PublishingError("Invalid planned publication date")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublishingError("Publication time must be ISO8601 with timezone") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise PublishingError("Publication time needs UTC offset")
    utc = dt.astimezone(timezone.utc)
    if not datetime.now(timezone.utc) + timedelta(minutes=10) < utc:
        raise PublishingError("Planned publication must be safely in the future")
    if utc > datetime.now(timezone.utc) + timedelta(days=365):
        raise PublishingError("Publication planning horizon exceeded")
    return utc.isoformat()


def _db(path=DB, *, create=False):
    path = ensure_local_root(Path(path))
    if not create and not path.is_file():
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    if create:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS releases(
          release_id TEXT PRIMARY KEY, film_slug TEXT NOT NULL,
          episode_id TEXT NOT NULL, source_sha TEXT NOT NULL,
          video_sha TEXT NOT NULL, render_sha TEXT NOT NULL,
          payload TEXT NOT NULL, payload_sha TEXT NOT NULL,
          state TEXT NOT NULL, platform_id TEXT, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(film_slug,episode_id));
        CREATE TABLE IF NOT EXISTS observations(
          release_id TEXT NOT NULL REFERENCES releases(release_id),
          observation_date TEXT NOT NULL,
          views INTEGER NOT NULL, likes INTEGER NOT NULL,
          comments INTEGER NOT NULL, watch_minutes INTEGER NOT NULL,
          entered_at TEXT NOT NULL,
          PRIMARY KEY(release_id,observation_date));
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          release_id TEXT NOT NULL, type TEXT NOT NULL,
          note TEXT NOT NULL, recorded_at TEXT NOT NULL);
        """)
        db.commit()
    return db


def _render(film_slug, episode_id, film_root):
    report = production.inspect_render(episode_id, film_slug, film_root=film_root)
    if (report.get("status") != production.READY
            or report.get("video_accepted") is not False
            or report.get("published") is not False):
        raise PublishingError("Expected Wave 9 source-only technical QA receipt")
    return report


def _validated_payload(payload):
    if not isinstance(payload, dict) or set(payload) != {
            "title", "description", "synthetic_media", "made_for_kids",
            "rights_attested", "owner_watched", "planned_utc", "campaign"}:
        raise PublishingError("Invalid release metadata schema")
    title = _text(payload["title"], "YouTube title", 100)
    description = _text(payload["description"], "YouTube description", 4500, minimum=0)
    for field in ("synthetic_media", "made_for_kids", "rights_attested", "owner_watched"):
        if type(payload[field]) is not bool:
            raise PublishingError("Media disclosures/Owner review must be explicit booleans")
    if not payload["rights_attested"] or not payload["owner_watched"]:
        raise PermissionError("Owner must watch film and attest media rights before handoff")
    campaign = payload["campaign"]
    if campaign is not None:
        from agentforge.features.growth import store
        store._identifier(campaign, store.CAMPAIGN, "campaign")
    return {
        "title": title, "description": description,
        "synthetic_media": payload["synthetic_media"],
        "made_for_kids": payload["made_for_kids"],
        "rights_owner_attested": True, "owner_watched_attested": True,
        "planned_utc": _date(payload["planned_utc"]),
        "campaign": campaign,
        "public_approval_given": False,
        "platform_posting_scheduled": False,
        "auto_publication": False,
        "auto_spend_authorized": False,
    }


def prepare(*, film_slug, episode_id, episode_sha, render_sha,
            metadata, confirmed=False, db_path=DB, film_root=production.FILMS,
            growth_db_path=None):
    if confirmed is not True:
        raise PermissionError("Explicit Owner release review required")
    source = production.inspect(episode_id, film_slug, film_root=film_root)
    report = _render(film_slug, episode_id, film_root)
    if (not isinstance(episode_sha, str) or not isinstance(render_sha, str)
            or source["episode_sha256"] != episode_sha
            or report["receipt_sha256"] != render_sha):
        raise PermissionError("Reviewed film source/receipt SHA changed")
    meta = _validated_payload(metadata)
    if meta["campaign"] is not None:
        from agentforge.features.growth import store
        if store.campaign_info(meta["campaign"], db_path=growth_db_path)["synthetic"]:
            # A demo campaign cannot be attached to a supposedly real release.
            raise PublishingError("Synthetic campaign cannot be linked to real upload")
    body = {
        "format": RELEASE_FORMAT, "film_slug": film_slug, "episode_id": episode_id,
        "episode_sha256": episode_sha, "render_receipt_sha256": render_sha,
        "video_sha256": report["video_sha256"],
        "captions_sha256": report["caption_sha256"],
        "source_clip_count": len(report["source_clips"]),
        "source_technical_qa_only": True, "platform": "youtube",
        "initial_privacy": "private", **meta,
    }
    identity = uuid4().hex
    with closing(_db(db_path, create=True)) as db, db:
        try:
            db.execute("""INSERT INTO releases VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (identity, film_slug, episode_id, episode_sha,
                        report["video_sha256"], render_sha,
                        json.dumps(body, ensure_ascii=False, allow_nan=False),
                        _digest(body), "READY_FOR_MANUAL_HANDOFF", None, _now(), _now()))
            db.execute("INSERT INTO events(release_id,type,note,recorded_at) VALUES(?,?,?,?)",
                       (identity, "OWNER_PREPARED", "Offline private-only handoff", _now()))
        except sqlite3.IntegrityError as exc:
            raise FileExistsError("Release already prepared for this film episode") from exc
    return inspect(identity, db_path=db_path, film_root=film_root)


def inspect(release_id, *, db_path=DB, film_root=production.FILMS, verify_source=True):
    ident = _id(release_id)
    conn = _db(db_path)
    if conn is None:
        raise KeyError("Release not found")
    with closing(conn):
        row = conn.execute("SELECT * FROM releases WHERE release_id=?", (ident,)).fetchone()
    if row is None:
        raise KeyError("Release not found")
    item = dict(row)
    try:
        body = json.loads(item["payload"])
        if (not isinstance(body, dict) or _digest(body) != item["payload_sha"]
                or body.get("format") != RELEASE_FORMAT
                or body.get("film_slug") != item["film_slug"]
                or body.get("episode_id") != item["episode_id"]
                or body.get("episode_sha256") != item["source_sha"]
                or body.get("render_receipt_sha256") != item["render_sha"]
                or body.get("video_sha256") != item["video_sha"]
                or body.get("initial_privacy") != "private"
                or body.get("public_approval_given") is not False
                or item["state"] not in STATES):
            raise ValueError("Release ledger invalid")
        if item["platform_id"] is not None and not VIDEO.fullmatch(item["platform_id"]):
            raise ValueError("Invalid video ID")
        if verify_source:
            report = _render(item["film_slug"], item["episode_id"], film_root)
            if report["receipt_sha256"] != item["render_sha"] \
                    or report["video_sha256"] != item["video_sha"]:
                raise PermissionError("Film MP4 source changed since release review")
    except (ValueError, TypeError, AttributeError, UnicodeError) as exc:
        raise PublishingError("Release payload or source invalid") from exc
    return {
        "release_id": ident, **body,
        "release_sha256": item["payload_sha"], "status": item["state"],
        "youtube_video_id": item["platform_id"], "created_at": item["created_at"],
        "updated_at": item["updated_at"],
        "platform_api_connected": item["state"] == "PRIVATE_UPLOADED_API",
        "platform_publication_verified": False, "revenue_verified": False,
        "source_integrity": "REHASH_VERIFIED" if verify_source else "NOT_RECHECKED",
    }


def list_releases(*, db_path=DB, film_root=production.FILMS, limit=30):
    if type(limit) is not int or not 1 <= limit <= 50:
        raise PublishingError("Invalid list limit")
    db = _db(db_path)
    if db is None:
        return []
    with closing(db):
        rows = [r["release_id"] for r in db.execute(
            "SELECT release_id FROM releases ORDER BY created_at DESC LIMIT ?", (limit,))]
    results = []
    for ident in rows:
        try:
            results.append(inspect(ident, db_path=db_path, film_root=film_root,
                                   verify_source=False))
        except (PublishingError, PermissionError, KeyError, OSError):
            results.append({"release_id": ident, "status": "INTEGRITY_REVIEW_REQUIRED",
                            "platform_publication_verified": False})
    return results


def _transition(release_id, source_sha, allowed, state, *, video_id=None,
                note="", db_path=DB):
    _id(release_id)
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        raise PermissionError("Invalid exact release SHA")
    if state not in STATES:
        raise PublishingError("Unknown release status")
    with closing(_db(db_path, create=True)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT payload_sha,state FROM releases WHERE release_id=?",
                         (release_id,)).fetchone()
        if row is None or row["payload_sha"] != source_sha or row["state"] not in allowed:
            raise PermissionError("Release changed or already attempted; reconcile manually")
        updated = db.execute("""UPDATE releases SET state=?,platform_id=?,updated_at=?
                               WHERE release_id=? AND state=? AND payload_sha=?""",
                             (state, video_id, _now(), release_id, row["state"], source_sha))
        if updated.rowcount != 1:
            raise PermissionError("Release changed during transition")
        db.execute("INSERT INTO events(release_id,type,note,recorded_at) VALUES(?,?,?,?)",
                   (release_id, state, note[:140], _now()))


def checkpoint_private_upload(release_id, release_sha, *, confirmed=False,
                              db_path=DB, film_root=production.FILMS):
    if confirmed is not True:
        raise PermissionError("Owner must approve one private-only YouTube API upload")
    item = inspect(release_id, db_path=db_path, film_root=film_root)
    if item["release_sha256"] != release_sha:
        raise PermissionError("Source release fingerprint is stale")
    _transition(release_id, release_sha, {"READY_FOR_MANUAL_HANDOFF"},
                "UPLOAD_ATTEMPT_UNCERTAIN", db_path=db_path)
    return item


def complete_private_upload(release_id, release_sha, video_id, *, db_path=DB):
    if not isinstance(video_id, str) or not VIDEO.fullmatch(video_id):
        raise PublishingError("YouTube API did not return a valid video ID")
    _transition(release_id, release_sha, {"UPLOAD_ATTEMPT_UNCERTAIN"},
                "PRIVATE_UPLOADED_API", video_id=video_id,
                note="Private-only API upload response, not public", db_path=db_path)


def owner_attest(release_id, release_sha, video_id, privacy, *,
                 confirmed=False, db_path=DB, film_root=production.FILMS):
    if confirmed is not True:
        raise PermissionError("Owner must explicitly attest platform state")
    if privacy not in {"private", "unlisted", "public", "scheduled"}:
        raise PublishingError("Only known owner-observed visibility states")
    if not isinstance(video_id, str) or not VIDEO.fullmatch(video_id):
        raise PublishingError("YouTube video ID must have 11 safe characters")
    doc = inspect(release_id, db_path=db_path, film_root=film_root)
    if doc["release_sha256"] != release_sha:
        raise PermissionError("Exact release SHA changed")
    current = doc["status"]
    if current not in {"READY_FOR_MANUAL_HANDOFF", "PRIVATE_UPLOADED_API",
                       "OWNER_REPORTED_PRIVATE", "OWNER_REPORTED_UNLISTED",
                       "OWNER_REPORTED_SCHEDULED", "OWNER_REPORTED_PUBLIC",
                       "UPLOAD_ATTEMPT_UNCERTAIN"}:
        raise PermissionError("Release not ready for manual attestation")
    if doc["youtube_video_id"] is not None and doc["youtube_video_id"] != video_id:
        raise PermissionError("Platform ID changed; refuse unrelated video")
    target = "OWNER_REPORTED_" + privacy.upper()
    _transition(release_id, release_sha, {current}, target, video_id=video_id,
                note="Owner-reported site state only; no API verification",
                db_path=db_path)
    return inspect(release_id, db_path=db_path, film_root=film_root)


def observe(release_id, release_sha, snapshot, *, confirmed=False,
            db_path=DB, film_root=production.FILMS):
    if confirmed is not True:
        raise PermissionError("Explicit Owner observation required")
    item = inspect(release_id, db_path=db_path, film_root=film_root)
    if item["release_sha256"] != release_sha:
        raise PermissionError("Release source SHA changed")
    if item["youtube_video_id"] is None:
        raise PublishingError("Cannot log platform statistics without a video ID")
    if not isinstance(snapshot, dict) or set(snapshot) != {
            "date", "views", "likes", "comments", "watch_minutes"}:
        raise PublishingError("Invalid observation schema")
    try:
        day = date.fromisoformat(snapshot["date"])
    except (ValueError, TypeError) as exc:
        raise PublishingError("Observation date must be YYYY-MM-DD") from exc
    if day > datetime.now(timezone.utc).date():
        raise PublishingError("Cannot report future platform statistics")
    for field in ("views", "likes", "comments", "watch_minutes"):
        value = snapshot[field]
        if type(value) is not int or not 0 <= value <= 10**12:
            raise PublishingError("Observation must be a nonnegative integer")
    with closing(_db(db_path, create=True)) as db, db:
        try:
            count = db.execute("SELECT COUNT(*) FROM observations WHERE release_id=?",
                               (release_id,)).fetchone()[0]
            if count >= MAX_OBSERVATIONS:
                raise PublishingError("Observation limit exceeded")
            db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?)",
                       (release_id, day.isoformat(), snapshot["views"],
                        snapshot["likes"], snapshot["comments"],
                        snapshot["watch_minutes"], _now()))
        except sqlite3.IntegrityError as exc:
            raise PublishingError("Observation already recorded; no overwrite") from exc
    return {"release_id": release_id, "observation_date": day.isoformat(),
            "owner_reported": True, "platform_api_verified": False,
            "monetization_verified": False, "stats": {
                k: snapshot[k] for k in ("views", "likes", "comments", "watch_minutes")}}


def summary(*, db_path=DB, film_root=production.FILMS):
    releases = list_releases(db_path=db_path, film_root=film_root)
    conn = _db(db_path)
    stats = {}
    if conn is not None:
        with closing(conn):
            for row in conn.execute("""SELECT o.release_id,o.observation_date,o.views,
                                   o.likes,o.comments,o.watch_minutes
                                   FROM observations o
                                   WHERE o.observation_date=(
                                       SELECT MAX(p.observation_date) FROM observations p
                                       WHERE p.release_id=o.release_id)"""):
                stats[row["release_id"]] = {
                    "observation_date": row["observation_date"],
                    "views": row["views"], "likes": row["likes"],
                    "comments": row["comments"], "watch_minutes": row["watch_minutes"],
                    "owner_reported": True, "platform_api_verified": False}
    return {"releases": [{**item, "latest_observation": stats.get(item["release_id"])}
                         for item in releases],
            "scheduled_actions_automatic": False, "auto_publish": False,
            "oauth_connected": False, "youtube_analytics_connected": False,
            "verified_net_profit_vnd": None,
            "bookkeeping_note": "Growth ledger remains source of Owner-entered VND; no bank reconciliation.",
            "status": "OWNER_CONTROLLED_UNVERIFIED"}


def handoff(release_id, *, db_path=DB, film_root=production.FILMS):
    """Read-only trusted filenames + bounded metadata for manual YouTube upload."""
    item = inspect(release_id, db_path=db_path, film_root=film_root)
    folder = production._folder(item["film_slug"], item["episode_id"], film_root)
    return {
        "release_id": release_id, "release_sha256": item["release_sha256"],
        "film_slug": item["film_slug"], "episode_id": item["episode_id"],
        "video_file": str(folder / "episode.mp4"), "srt_file": str(folder / "captions.srt"),
        "metadata": {"title": item["title"], "description": item["description"],
                     "synthetic_media": item["synthetic_media"],
                     "made_for_kids": item["made_for_kids"],
                     "privacy": "private", "planned_utc": item["planned_utc"]},
        "video_sha256": item["video_sha256"],
        "automatic_upload": False, "automatic_publication": False,
        "owner_must_use_youtube_studio": True,
    }
