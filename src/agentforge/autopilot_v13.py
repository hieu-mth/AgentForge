"""V1.3 supervised local draft queue. Explicit standing delegation, never blanket tool grants.

Only built-in single-model draft skills are eligible. A reservation is durable
BEFORE a model invocation, and ambiguous dispatches are NEVER replayed.
This is a call-count ceiling, not a provider-enforced currency/token limit.
"""
import argparse
import json
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentforge import brain_store, ops_control, skill_registry, skill_runner

DB = brain_store.ROOT / "data" / "company" / "autopilot_v13.sqlite3"
# Do not add network, browser, process, publishing, finance or customer access.
DELEGATED = {
    "media.copy_draft": frozenset({"model.invoke", "workspace.propose"}),
    "web.create": frozenset({"model.invoke", "workspace.propose"}),
}
MAX_DAILY = 10
MAX_PENDING = 25


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path=None, *, create=False):
    path = Path(db_path) if db_path is not None else DB
    brain_store._safe(path)
    if not create and not path.is_file():
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
        brain_store._safe(path.parent)
    db = sqlite3.connect(path, timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=20000")
    if create:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS policy (
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          enabled INTEGER NOT NULL CHECK(enabled IN(0,1)),
          daily_cap INTEGER NOT NULL, updated_utc TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
          job_id TEXT PRIMARY KEY, skill_id TEXT NOT NULL,
          payload_json TEXT NOT NULL, status TEXT NOT NULL,
          estimated_calls INTEGER NOT NULL,
          reserved_day TEXT, task_id TEXT, created_utc TEXT NOT NULL,
          updated_utc TEXT NOT NULL, error_code TEXT);
        CREATE INDEX IF NOT EXISTS ix_autopilot_queue ON jobs(status,created_utc);
        CREATE INDEX IF NOT EXISTS ix_autopilot_budget ON jobs(reserved_day);
        """)
    return db


def configure(*, daily_cap=0, enabled=False, confirm=False, db_path=None):
    """Standing owner delegation: maximum estimated calls per UTC day."""
    if confirm is not True or type(enabled) is not bool:
        raise PermissionError("Owner confirmation required")
    if type(daily_cap) is not int or not 0 <= daily_cap <= MAX_DAILY:
        raise ValueError("Invalid daily call cap")
    if enabled and daily_cap < 1:
        raise ValueError("Enabled delegation requires a positive cap")
    with closing(_connect(db_path, create=True)) as db:
        with db:
            db.execute("""INSERT INTO policy VALUES(1,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                enabled=excluded.enabled,daily_cap=excluded.daily_cap,
                updated_utc=excluded.updated_utc""",
                (int(enabled), daily_cap, _utc()))
    return policy(db_path=db_path)


def policy(*, db_path=None):
    db = _connect(db_path)
    if db is None:
        return {"enabled": False, "daily_cap": 0}
    with closing(db):
        row = db.execute("SELECT enabled,daily_cap FROM policy WHERE singleton=1").fetchone()
        if row is None:
            return {"enabled": False, "daily_cap": 0}
        cap = row["daily_cap"]
        if row["enabled"] not in (0, 1) or type(cap) is not int or not 0 <= cap <= MAX_DAILY:
            raise PermissionError("Invalid delegated policy: fail closed")
        return {"enabled": bool(row["enabled"]), "daily_cap": cap}


def _validated(skill_id, payload):
    if skill_id not in DELEGATED:
        raise PermissionError("Skill is not eligible for delegated model execution")
    contract, required = skill_runner._contract(skill_id)
    if frozenset(required) != DELEGATED[skill_id]:
        raise PermissionError("Trusted skill permissions changed")
    calls = contract["limits"]["estimated_model_calls"]
    if type(calls) is not int or calls != 1:
        raise PermissionError("Only exactly one estimated model call is supported")
    skill_registry.validate_payload(contract, payload)
    if not isinstance(payload, dict) or len(json.dumps(payload, ensure_ascii=False).encode()) > 4096:
        raise ValueError("Draft input too large")
    # Validate deeper than the shallow skill schema before persistence.
    if skill_id == "web.create":
        from agentforge.product_builder import _check_slug, _bounded_text
        if set(payload) != {"slug", "brief"}:
            raise ValueError("Unexpected website fields")
        _check_slug(payload["slug"])
        _bounded_text(payload["brief"], "brief", 20, 600)
    else:
        from agentforge.media_assets import _text
        if set(payload) != {"topic", "audience", "goal"}:
            raise ValueError("Unexpected creative fields")
        for key in ("topic", "audience", "goal"):
            _text(payload[key], key, 240)
    return calls


def submit(skill_id, payload, *, db_path=None):
    """Queue proposal-only work; no model call and no external side effect."""
    calls = _validated(skill_id, payload)
    now, job_id = _utc(), uuid4().hex
    with closing(_connect(db_path, create=True)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            if db.execute("SELECT COUNT(*) FROM jobs WHERE status='QUEUED'").fetchone()[0] >= MAX_PENDING:
                raise ValueError("Delegated queue is full")
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (job_id, skill_id, json.dumps(payload, ensure_ascii=False,
                        sort_keys=True, separators=(",", ":")), "QUEUED",
                        calls, None, None, now, now, None))
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return {"job_id": job_id, "status": "QUEUED", "estimated_model_calls": calls,
            "requires_owner_review_of_output": True}


def _claim(*, db_path=None, now=None):
    """Atomically reserve daily quota and one job, across competing workers."""
    ops_control.require_active()
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date().isoformat()
    with closing(_connect(db_path, create=True)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute("SELECT enabled,daily_cap FROM policy WHERE singleton=1").fetchone()
            if row is None or row["enabled"] != 1 or type(row["daily_cap"]) is not int or not 1 <= row["daily_cap"] <= MAX_DAILY:
                raise PermissionError("Delegated model policy is disabled or invalid")
            used = db.execute("SELECT COALESCE(SUM(estimated_calls),0) FROM jobs WHERE reserved_day=?",
                              (today,)).fetchone()[0]
            job = db.execute("SELECT * FROM jobs WHERE status='QUEUED' ORDER BY created_utc,job_id LIMIT 1").fetchone()
            if job is None:
                db.commit()
                return None
            if job["estimated_calls"] != 1 or used + job["estimated_calls"] > row["daily_cap"]:
                db.commit()
                return {"status": "DAILY_QUOTA_REACHED", "used": used, "cap": row["daily_cap"]}
            # Recheck all policy and payload before the irreversible no-retry claim.
            payload = json.loads(job["payload_json"])
            _validated(job["skill_id"], payload)
            ops_control.require_active()
            db.execute("""UPDATE jobs SET status='DISPATCHING',
                reserved_day=?, updated_utc=? WHERE job_id=? AND status='QUEUED'""",
                (today, _utc(), job["job_id"]))
            db.commit()
            return {"job_id": job["job_id"], "skill_id": job["skill_id"],
                    "payload": payload, "reserved_day": today}
        except BaseException:
            db.rollback()
            raise


def _finish(job_id, status, task_id=None, error_code=None, *, db_path=None):
    if status not in ("SUCCEEDED", "FAILED", "WAITING_OWNER_REVIEW"):
        raise ValueError("Invalid dispatch completion")
    if task_id is not None and (not isinstance(task_id, str) or not brain_store.ID.fullmatch(task_id)):
        task_id = None
    with closing(_connect(db_path, create=True)) as db:
        with db:
            changed = db.execute("""UPDATE jobs SET status=?,task_id=?,error_code=?,updated_utc=?
                WHERE job_id=? AND status='DISPATCHING'""",
                (status, task_id, error_code, _utc(), job_id))
            if changed.rowcount != 1:
                raise RuntimeError("Dispatch receipt cannot be recorded")


def tick(*, allow_model=False, db_path=None, task_db_path=None):
    """One delegated model draft, only with explicit process-level opt-in."""
    if allow_model is not True:
        raise PermissionError("Explicit --allow-model required")
    job = _claim(db_path=db_path)
    if job is None:
        return {"status": "QUEUE_EMPTY"}
    if "job_id" not in job:
        return job
    try:
        # Recheck revocation after quota reservation and before S1 entry.
        # Reservation stays consumed if owner revoked mid-flight: never replay.
        if not policy(db_path=db_path)["enabled"]:
            return {"job_id": job["job_id"], "status": "INTERRUPTED_REVIEW_REQUIRED",
                    "reason": "DELEGATION_REVOKED", "automatic_retry": False}
        ops_control.require_active()
        # Owner delegated precisely these grants at configure time.
        receipt = skill_runner.invoke(
            job["skill_id"], job["payload"],
            grants=tuple(sorted(DELEGATED[job["skill_id"]])),
            confirm_model_call=True, db_path=task_db_path)
        state = receipt.get("status")
        if state == "SUCCEEDED":
            result_status = "SUCCEEDED"
        elif state == "WAITING_APPROVAL":
            result_status = "WAITING_OWNER_REVIEW"
        else:
            result_status = "FAILED"
        _finish(job["job_id"], result_status, receipt.get("task_id"),
                None if result_status == "SUCCEEDED" else "SKILL_NOT_SUCCEEDED",
                db_path=db_path)
        return {"job_id": job["job_id"], "status": result_status,
                "task_id": receipt.get("task_id"), "requires_owner_review_of_output": True}
    except Exception as exc:
        # Exception may follow a successful provider request. Consumed quota and
        # DISPATCHING marker deliberately remain; owner must investigate.
        return {"job_id": job["job_id"], "status": "INTERRUPTED_REVIEW_REQUIRED",
                "error_type": type(exc).__name__, "automatic_retry": False}


def report(*, db_path=None):
    """Redacted operational report: no prompts, proposals or model responses."""
    db = _connect(db_path)
    if db is None:
        return {"policy": policy(db_path=db_path), "used_today": 0, "jobs": []}
    today = datetime.now(timezone.utc).date().isoformat()
    with closing(db):
        used = db.execute("SELECT COALESCE(SUM(estimated_calls),0) FROM jobs WHERE reserved_day=?",
                          (today,)).fetchone()[0]
        jobs = [dict(row) for row in db.execute(
            "SELECT job_id,skill_id,status,estimated_calls,reserved_day,task_id,created_utc,updated_utc,error_code "
            "FROM jobs ORDER BY created_utc DESC,job_id DESC LIMIT 50")]
    return {"policy": policy(db_path=db_path), "used_today": used,
            "day_utc": today, "jobs": jobs,
            "verified_provider_cost": False, "automatic_retry": False,
            "model_outputs_need_owner_review": True}


def run_loop(*, allow_model=False, interval=60):
    if allow_model is not True or type(interval) is not int or not 30 <= interval <= 3600:
        raise PermissionError("Explicit --allow-model and interval 30-3600 required")
    # Foreground only; Windows shutdown/hibernate stops execution.
    while True:
        result = tick(allow_model=True)
        print(json.dumps({k: v for k, v in result.items() if k != "payload"}), flush=True)
        time.sleep(interval)


def main():
    cli = argparse.ArgumentParser(description="V1.3 local supervised proposal-only autopilot")
    sub = cli.add_subparsers(dest="cmd", required=True)
    config = sub.add_parser("configure")
    config.add_argument("--daily-model-calls", type=int, required=True)
    config.add_argument("--enable", action="store_true")
    config.add_argument("--confirm-delegation", action="store_true")
    enqueue = sub.add_parser("submit")
    enqueue.add_argument("skill_id", choices=sorted(DELEGATED))
    enqueue.add_argument("--input-file", required=True)
    once = sub.add_parser("once")
    once.add_argument("--allow-model", action="store_true")
    loop = sub.add_parser("run")
    loop.add_argument("--allow-model", action="store_true")
    loop.add_argument("--interval", type=int, default=60)
    sub.add_parser("report")
    args = cli.parse_args()
    if args.cmd == "configure":
        result = configure(daily_cap=args.daily_model_calls, enabled=args.enable,
                           confirm=args.confirm_delegation)
    elif args.cmd == "submit":
        path = Path(args.input_file)
        brain_store._safe(path)
        if path.stat().st_size > 4096:
            cli.error("Draft input exceeds 4KB")
        result = submit(args.skill_id, json.loads(path.read_text(encoding="utf-8-sig")))
    elif args.cmd == "once":
        result = tick(allow_model=args.allow_model)
    elif args.cmd == "run":
        try:
            run_loop(allow_model=args.allow_model, interval=args.interval)
        except KeyboardInterrupt:
            result = {"status": "STOPPED"}
    else:
        result = report()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
