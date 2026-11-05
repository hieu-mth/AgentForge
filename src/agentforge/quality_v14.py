"""V1.4 owner-defined business context, conservative deterministic QA and review inbox.

Never execute model output. All decisions and findings are local metadata; no
automatic publishing, source application, retries or extra model calls.
"""
import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from agentforge import brain_store

SCHEMA = """
CREATE TABLE IF NOT EXISTS business_profile (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  profile_json TEXT NOT NULL, profile_sha TEXT NOT NULL,
  updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS job_context (
  job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
  profile_json TEXT NOT NULL, profile_sha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS content_reviews (
  job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
  task_id TEXT NOT NULL, skill_id TEXT NOT NULL,
  output_sha TEXT NOT NULL,
  profile_sha TEXT,
  quality TEXT NOT NULL,
  reasons_json TEXT NOT NULL,
  decision TEXT NOT NULL,
  decided_at TEXT, created_at TEXT NOT NULL);
"""
MAX_RESULT_BYTES = 65000


def ensure(db):
    # Called by the owning autopilot SQLite connection creation.
    db.executescript(SCHEMA)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _sha(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value, label, limit):
    if (not isinstance(value, str) or not 2 <= len(value.strip()) <= limit
            or any(ord(c) < 32 for c in value)):
        raise ValueError("Invalid " + label)
    return unicodedata.normalize("NFC", value.strip())


def validate_profile(profile):
    if not isinstance(profile, dict) or set(profile) != {
            "business", "industry", "focus_phrases", "blocked_phrases"}:
        raise ValueError("Profile fields must be explicitly defined")
    cleaned = {"business": _text(profile["business"], "business", 100),
               "industry": _text(profile["industry"], "industry", 100)}
    for key in ("focus_phrases", "blocked_phrases"):
        terms = profile[key]
        if (not isinstance(terms, list) or not 1 <= len(terms) <= 12
                or any(not isinstance(t, str) for t in terms)):
            raise ValueError("Invalid " + key)
        normalized = [_text(t, key, 60) for t in terms]
        if len({t.casefold() for t in normalized}) != len(normalized):
            raise ValueError("Duplicate profile phrase")
        cleaned[key] = normalized
    if len(_canonical(cleaned).encode("utf-8")) > 2400:
        raise ValueError("Profile too large")
    return cleaned


def set_profile(profile, *, confirm=False, db_path=None):
    if confirm is not True:
        raise PermissionError("Explicit owner business context approval required")
    clean = validate_profile(profile)
    from agentforge.autopilot_v13 import _connect
    with _connect(db_path, create=True) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("""INSERT INTO business_profile VALUES(1,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                profile_json=excluded.profile_json,profile_sha=excluded.profile_sha,
                updated_at=excluded.updated_at""",
                (_canonical(clean), _sha(clean), datetime.now(timezone.utc).isoformat()))
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return {"business": clean["business"], "industry": clean["industry"],
            "profile_sha": _sha(clean), "owner_confirmed": True,
            "automatic_model_approval": False}


def current_profile(db):
    row = db.execute("SELECT profile_json,profile_sha FROM business_profile WHERE singleton=1").fetchone()
    if row is None:
        return None
    data = json.loads(row["profile_json"])
    clean = validate_profile(data)
    if _sha(clean) != row["profile_sha"]:
        raise PermissionError("Business context integrity mismatch")
    return clean


def snapshot_job(db, job_id):
    """Freeze the owner's current business context along with queued job."""
    profile = current_profile(db)
    if profile is None:
        return
    db.execute("INSERT INTO job_context VALUES(?,?,?)",
               (job_id, _canonical(profile), _sha(profile)))


def _job_profile(db, job_id):
    row = db.execute("SELECT profile_json,profile_sha FROM job_context WHERE job_id=?",
                     (job_id,)).fetchone()
    if row is None:
        return None, None
    profile = validate_profile(json.loads(row["profile_json"]))
    if _sha(profile) != row["profile_sha"]:
        raise PermissionError("Queued business context changed")
    return profile, row["profile_sha"]



def preflight_payload(db, skill_id, payload):
    """Conservative business fit check BEFORE enqueue or paid model reserve."""
    profile = current_profile(db)
    if profile is None:
        return {"status": "NO_CONTEXT_LEGACY_REVIEW_REQUIRED"}
    if skill_id == "media.copy_draft":
        text = "\n".join(payload.get(k, "") for k in ("topic", "audience", "goal"))
    elif skill_id == "web.create":
        text = payload.get("brief", "")
    else:
        raise PermissionError("Business context cannot authorize this skill")
    if not any(_has_phrase(text, t) for t in profile["focus_phrases"]):
        raise ValueError("BUSINESS_CONTEXT_MISMATCH: input must name the business explicitly")
    if any(_has_phrase(text, t) for t in profile["blocked_phrases"]):
        raise ValueError("BLOCKED_BUSINESS_TERMS: rewrite owner brief")
    return {"status": "CONTEXT_MATCH"}


def verify_queued_context(db, job_id, skill_id, payload):
    """Existing jobs must not silently inherit new owner context."""
    profile, profile_sha = _job_profile(db, job_id)
    active = current_profile(db)
    if active is not None and profile is None:
        raise PermissionError("Legacy queued job missing owner business context; review manually")
    if profile is not None:
        if active is None or _sha(active) != profile_sha:
            raise PermissionError("Owner business profile changed; requeue with new snapshot")
        # Validate against saved input before model-call reservation.
        if skill_id == "media.copy_draft":
            text = "\n".join(payload.get(k, "") for k in ("topic", "audience", "goal"))
        elif skill_id == "web.create":
            text = payload.get("brief", "")
        else:
            raise PermissionError("Unsupported supervised skill")
        if not any(_has_phrase(text, t) for t in profile["focus_phrases"]):
            raise PermissionError("Queued brief does not match business context")
        if any(_has_phrase(text, t) for t in profile["blocked_phrases"]):
            raise PermissionError("Queued brief contains blocked terms")
    return True


def pause_schedule(schedule_id, *, confirm=False, db_path=None):
    """Pause recurring intake, including stale pre-V1.4 schedules."""
    if confirm is not True:
        raise PermissionError("Owner schedule pause confirmation required")
    brain_store._id(schedule_id)
    from agentforge.autopilot_v13 import _connect
    with _connect(db_path, create=True) as db:
        with db:
            row = db.execute("UPDATE schedules SET enabled=0 WHERE schedule_id=?",
                             (schedule_id,))
            if row.rowcount != 1:
                raise KeyError("Schedule not found")
    return {"schedule_id": schedule_id, "status": "PAUSED",
            "queued_jobs_cancelled": False}


def _has_phrase(source, phrase):
    # Accent-sensitive and word-boundary aware: 'nem' is NOT the same as 'nệm'.
    source = unicodedata.normalize("NFC", source).casefold()
    phrase = unicodedata.normalize("NFC", phrase).casefold()
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", source, re.UNICODE) is not None


def assess(skill_id, result, profile):
    """Rule based *signal* only, never a claim of factual/semantic correctness."""
    if not isinstance(result, dict):
        return {"quality": "UNASSESSED", "reasons": ["RESULT_NOT_OBJECT"]}
    if profile is None:
        return {"quality": "UNASSESSED", "reasons": ["BUSINESS_CONTEXT_MISSING"]}
    if skill_id != "media.copy_draft":
        # Website proposal receipt has no full HTML body. Existing authenticated
        # source SHA inspection remains the ONLY path to owner apply.
        return {"quality": "UNASSESSED", "reasons": ["SOURCE_REVIEW_REQUIRED"]}
    scenes = result.get("scenes")
    if not isinstance(scenes, list) or not 2 <= len(scenes) <= 5:
        return {"quality": "BLOCKED", "reasons": ["INVALID_STORYBOARD"]}
    try:
        chunks = [_text(result.get("title"), "title", 200)]
        for scene in scenes:
            if not isinstance(scene, dict):
                raise ValueError("Invalid scene")
            chunks.append(_text(scene.get("headline"), "headline", 150))
            chunks.append(_text(scene.get("caption"), "caption", 300))
        body = "\n".join(chunks)
    except ValueError:
        return {"quality": "BLOCKED", "reasons": ["INVALID_STORYBOARD"]}
    reasons = []
    if any(_has_phrase(body, term) for term in profile["blocked_phrases"]):
        reasons.append("BLOCKED_BUSINESS_TERMS")
    if not any(_has_phrase(body, term) for term in profile["focus_phrases"]):
        reasons.append("NO_BUSINESS_FOCUS_EVIDENCE")
    if result.get("verified_claims") is not False or result.get("review_required") is not True:
        reasons.append("MISSING_UNVERIFIED_DRAFT_MARKERS")
    return {"quality": "BLOCKED" if reasons else "PASS_HEURISTIC",
            "reasons": reasons or ["HEURISTIC_ONLY_OWNER_REVIEW_REQUIRED"]}


def record_success(db, job_id, task_id, skill_id, result):
    """Write immutable review with model job result digest, never prompt or output."""
    profile, profile_sha = _job_profile(db, job_id)
    evaluation = assess(skill_id, result, profile)
    try:
        raw = _canonical(result)
        if len(raw.encode("utf-8")) > MAX_RESULT_BYTES:
            raise ValueError("Result too large")
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, OverflowError):
        evaluation = {"quality": "UNASSESSED", "reasons": ["INVALID_RESULT_DIGEST"]}
        digest = "0" * 64
    db.execute("""INSERT INTO content_reviews VALUES (?,?,?,?,?,?,?,?,?,?)""",
               (job_id, task_id or "", skill_id, digest, profile_sha,
                evaluation["quality"], _canonical(evaluation["reasons"]),
                "PENDING", None, datetime.now(timezone.utc).isoformat()))
    return {"quality": evaluation["quality"],
            "reasons": evaluation["reasons"], "output_sha": digest,
            "review_status": "PENDING"}


def inbox(*, db_path=None):
    from agentforge.autopilot_v13 import _connect
    db = _connect(db_path)
    if db is None:
        return {"business_context": None, "reviews": []}
    with db:
        profile = current_profile(db)
        rows = db.execute("""SELECT job_id,task_id,skill_id,output_sha,profile_sha,
            quality,reasons_json,decision,created_at,decided_at FROM content_reviews
            ORDER BY created_at DESC,job_id DESC LIMIT 100""").fetchall()
    db.close()
    return {"business_context": None if profile is None else {
        "business": profile["business"], "industry": profile["industry"],
        "profile_sha": _sha(profile)},
        "reviews": [{**dict(row), "reasons": json.loads(row["reasons_json"])}
                    for row in rows]}


def decide(job_id, decision, sha, *, confirm=False, db_path=None):
    """Explicit once-only decision bound to immutable output SHA."""
    if confirm is not True or decision not in {"APPROVE", "REJECT"}:
        raise PermissionError("Explicit owner review confirmation required")
    brain_store._id(job_id)
    if not isinstance(sha, str) or not brain_store.SHA.fullmatch(sha):
        raise ValueError("Output SHA required")
    from agentforge.autopilot_v13 import _connect
    with _connect(db_path, create=True) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT * FROM content_reviews WHERE job_id=?",
                             (job_id,)).fetchone()
            if row is None:
                raise KeyError("Review not found")
            if row["decision"] != "PENDING" or row["output_sha"] != sha:
                raise PermissionError("Review already decided or output SHA mismatch")
            if decision == "APPROVE" and row["quality"] != "PASS_HEURISTIC":
                raise PermissionError("Cannot approve blocked or unassessed draft")
            updated = db.execute("""UPDATE content_reviews
                SET decision=?,decided_at=? WHERE job_id=? AND decision='PENDING'""",
                (("APPROVED" if decision == "APPROVE" else "REJECTED"),
                 datetime.now(timezone.utc).isoformat(), job_id))
            if updated.rowcount != 1:
                raise PermissionError("Review decision changed concurrently")
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return {"job_id": job_id, "decision": "APPROVED" if decision == "APPROVE" else "REJECTED",
            "output_sha": sha, "published": False, "applied": False,
            "auto_next_step": False}


def main():
    parser = argparse.ArgumentParser(description="V1.4 local business context + draft review")
    subs = parser.add_subparsers(dest="action", required=True)
    p = subs.add_parser("set-context")
    p.add_argument("--input-file", required=True)
    p.add_argument("--confirm-context", action="store_true")
    subs.add_parser("inbox")
    pause = subs.add_parser("pause-schedule")
    pause.add_argument("schedule_id")
    pause.add_argument("--confirm-pause", action="store_true")
    r = subs.add_parser("decide")
    r.add_argument("job_id")
    r.add_argument("decision", choices=("APPROVE", "REJECT"))
    r.add_argument("--output-sha", required=True)
    r.add_argument("--confirm-review", action="store_true")
    args = parser.parse_args()
    if args.action == "set-context":
        path = Path(args.input_file)
        brain_store._safe(path)
        if path.stat().st_size > 2400:
            parser.error("Business context file too large")
        result = set_profile(json.loads(path.read_text(encoding="utf-8-sig")),
                             confirm=args.confirm_context)
    elif args.action == "inbox":
        result = inbox()
    elif args.action == "pause-schedule":
        result = pause_schedule(args.schedule_id, confirm=args.confirm_pause)
    else:
        result = decide(args.job_id, args.decision, args.output_sha,
                        confirm=args.confirm_review)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
