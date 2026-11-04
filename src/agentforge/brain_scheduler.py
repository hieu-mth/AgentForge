"""S4 local scheduler: opt-in due-tick for read-only, preapproved templates.

No timers, daemon, background work, account access, cost-bearing jobs,
or silent authorization. A schedule slot is recorded before execution,
so crashes cannot cause automatic repeat of the same due event.
"""
import json
from contextlib import closing
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from agentforge import brain_planner as planner
from agentforge import brain_store as store
from agentforge import brain_runner

UTC = timezone.utc


def _time(value):
    if not isinstance(value, str):
        raise store.BrainError("Datetime must be ISO-8601 with timezone")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise store.BrainError("Invalid ISO datetime") from exc
    if dt.tzinfo is None:
        raise store.BrainError("Scheduling requires UTC or explicit timezone")
    return dt.astimezone(UTC)


def create_schedule(title, template, inputs, next_due,
                    frequency_minutes, *, confirm_schedule=False,
                    db_path=None, now=None):
    if confirm_schedule is not True:
        raise PermissionError("Owner must explicitly authorize recurring schedule")
    if type(frequency_minutes) is not int or not 60 <= frequency_minutes <= 10080:
        raise store.BrainError("Schedule interval must be 60-10080 minutes")
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 160:
        raise store.BrainError("Invalid scheduled goal title")
    if not planner.read_only_plan(template, inputs):
        raise PermissionError("Only 100% read-only no-model plans may be scheduled")
    due = _time(next_due)
    current = now or datetime.now(UTC)
    if due <= current or due > current + timedelta(days=365):
        raise store.BrainError("First due must be future and within one year")
    schedule_id = uuid4().hex
    with closing(store._connect(db_path, create=True)) as conn, conn:
        conn.execute("INSERT INTO schedules VALUES (?,?,?,?,?,?,?,?)",
                     (schedule_id, title.strip(), template, store._json(inputs),
                      frequency_minutes, due.isoformat(),
                      "ACTIVE", store._now()))
    return {"schedule_id": schedule_id, "status": "ACTIVE",
            "next_due_utc": due.isoformat(), "frequency_minutes": frequency_minutes,
            "read_only_only": True, "owner_approved": True,
            "background_execution_enabled": False}


def list_schedules(*, db_path=None):
    conn = store._connect(db_path)
    if conn is None:
        return []
    with closing(conn):
        return [dict(x) for x in conn.execute(
            "SELECT schedule_id,title,template,frequency_minutes,next_due_utc,status "
            "FROM schedules ORDER BY next_due_utc,schedule_id LIMIT 100")]


def set_schedule_status(schedule_id, status, *, confirm_write=False, db_path=None):
    store._id(schedule_id)
    if confirm_write is not True:
        raise PermissionError("Owner confirmation required")
    if status not in {"ACTIVE", "PAUSED"}:
        raise store.BrainError("Invalid schedule status")
    with closing(store._connect(db_path, create=True)) as conn, conn:
        changed = conn.execute("UPDATE schedules SET status=? WHERE schedule_id=?",
                               (status, schedule_id))
        if changed.rowcount != 1:
            raise KeyError("Schedule not found")
    return {"schedule_id": schedule_id, "status": status}


def tick(*, confirm_tick=False, db_path=None, task_db_path=None,
         now=None, max_due=3):
    """Check at most 3 due schedules; once-only durable slot claim."""
    if confirm_tick is not True:
        raise PermissionError("Owner must explicitly authorize local scheduler tick")
    if type(max_due) is not int or not 1 <= max_due <= 3:
        raise store.BrainError("Tick limit must be 1-3")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise store.BrainError("Tick time must be timezone-aware")
    current = current.astimezone(UTC)
    claimed = []
    conn = store._connect(db_path)
    if conn is None:
        return {"status": "NO_DUE_SCHEDULES", "claimed": [], "executions": [],
                "background_execution_enabled": False}
    conn.close()
    with closing(store._connect(db_path, create=True)) as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM schedules WHERE status='ACTIVE' AND next_due_utc<=? "
                "ORDER BY next_due_utc,schedule_id LIMIT ?",
                (current.isoformat(), max_due)).fetchall()
            for row in rows:
                # Revalidate trusted code-level plan, not just stored template.
                inputs = json.loads(row["inputs_json"])
                if not planner.read_only_plan(row["template"], inputs):
                    raise PermissionError("Schedule template gained side effects")
                plan = planner.make_plan(row["template"], inputs)
                recorded_inputs = {**inputs, "_limits": {
                    "max_model_calls": 0, "max_external_runs": 0}}
                goal = store.create_goal(
                    row["title"], row["template"], recorded_inputs, plan,
                    db_path=db_path, source_schedule_id=row["schedule_id"],
                    source_slot=row["next_due_utc"], conn=db)
                # Standing approval is only for this strictly read-only plan.
                db.execute("UPDATE goals SET status='APPROVED' WHERE goal_id=? "
                           "AND status='PLANNED'", (goal["goal_id"],))
                db.execute("INSERT INTO goal_events(goal_id,at,name,detail_json) "
                           "VALUES(?,?,?,?)", (goal["goal_id"], store._now(),
                                              "SCHEDULE_READ_ONLY_APPROVED", "{}"))
                db.execute("INSERT INTO slots VALUES(?,?,?)",
                           (row["schedule_id"], row["next_due_utc"], goal["goal_id"]))
                next_due = _time(row["next_due_utc"])
                frequency = timedelta(minutes=row["frequency_minutes"])
                # Skip missed intervals instead of replaying historical backlog.
                while next_due <= current:
                    next_due += frequency
                db.execute("UPDATE schedules SET next_due_utc=? WHERE schedule_id=?",
                           (next_due.isoformat(), row["schedule_id"]))
                claimed.append({"schedule_id": row["schedule_id"],
                                "goal_id": goal["goal_id"],
                                "slot": row["next_due_utc"],
                                "next_due_utc": next_due.isoformat()})
    executions = []
    for item in claimed:
        # No grants are passed. Only trusted read-only templates may run here.
        try:
            result = brain_runner.execute(
                item["goal_id"], brain_db_path=db_path, task_db_path=task_db_path)
        except Exception as exc:
            result = {"goal_id": item["goal_id"],
                      "status": "MANUAL_REVIEW_REQUIRED",
                      "error_type": type(exc).__name__}
        executions.append(result)
    return {"status": "TICK_COMPLETED", "claimed": claimed,
            "executions": executions, "background_execution_enabled": False,
            "missed_intervals_replayed": False}
