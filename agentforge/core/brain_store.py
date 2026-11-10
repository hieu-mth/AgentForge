"""S4 durable local company goals, immutable plans, step state and audit.

This is a single-owner SQLite coordination store, not an identity/security
boundary or financial ledger. It never runs tools or background processes.
"""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from agentforge.paths import REPOSITORY_ROOT
from uuid import uuid4

ROOT = REPOSITORY_ROOT
DB = ROOT / "data" / "company" / "s4_brain.sqlite3"
ID = re.compile(r"[a-f0-9]{32}\Z")
KEY = re.compile(r"[a-z][a-z0-9_.-]{2,63}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
STATES = {"PLANNED", "APPROVED", "RUNNING", "WAITING_APPROVAL",
          "SUCCEEDED", "FAILED", "INTERRUPTED"}
TRANSITIONS = {
    "PLANNED": {"APPROVED"},
    "APPROVED": {"RUNNING", "INTERRUPTED"},
    "RUNNING": {"WAITING_APPROVAL", "SUCCEEDED", "FAILED", "INTERRUPTED"},
    "WAITING_APPROVAL": {"RUNNING", "INTERRUPTED"},
    "SUCCEEDED": set(), "FAILED": set(), "INTERRUPTED": set(),
}
STEP_STATES = {"DISPATCHING", "WAITING_APPROVAL", "SUCCEEDED", "FAILED"}
MAX_PLAN_BYTES = 8192


class BrainError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise BrainError("Invalid goal ID")
    return value


def _safe(path):
    for node in (path, *path.parents):
        if node.is_symlink() or (hasattr(node, "is_junction") and node.is_junction()):
            raise PermissionError("Brain SQLite symlink or junction rejected")


def _json(value, limit=MAX_PLAN_BYTES):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                     sort_keys=True, allow_nan=False)
    if len(raw.encode("utf-8")) > limit:
        raise BrainError("Plan/record exceeds size limit")
    return raw


def _connect(db_path=None, *, create=False):
    path = Path(db_path) if db_path is not None else DB
    _safe(path)
    if not create and not path.is_file():
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    # Queries must not create a database, journal or schema. Only explicit
    # mutating entry points may open a read/write connection.
    conn = (sqlite3.connect(path, timeout=10) if create else
            sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                            uri=True, timeout=10))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if create:
        conn.executescript("""
          CREATE TABLE IF NOT EXISTS goals(
            goal_id TEXT PRIMARY KEY, title TEXT NOT NULL,
            template TEXT NOT NULL, inputs_json TEXT NOT NULL,
            plan_json TEXT NOT NULL, plan_sha256 TEXT NOT NULL,
            status TEXT NOT NULL, current_step INTEGER NOT NULL,
            parent_task_id TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, error TEXT,
            source_schedule_id TEXT, source_slot TEXT);
          CREATE TABLE IF NOT EXISTS step_runs(
            goal_id TEXT NOT NULL REFERENCES goals(goal_id),
            step_index INTEGER NOT NULL, skill_id TEXT NOT NULL,
            status TEXT NOT NULL, child_task_id TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(goal_id,step_index));
          CREATE TABLE IF NOT EXISTS goal_events(
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id TEXT NOT NULL REFERENCES goals(goal_id),
            at TEXT NOT NULL, name TEXT NOT NULL, detail_json TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS schedules(
            schedule_id TEXT PRIMARY KEY, title TEXT NOT NULL,
            template TEXT NOT NULL, inputs_json TEXT NOT NULL,
            plan_sha256 TEXT NOT NULL,
            frequency_minutes INTEGER NOT NULL, next_due_utc TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS slots(
            schedule_id TEXT NOT NULL REFERENCES schedules(schedule_id),
            due_utc TEXT NOT NULL, goal_id TEXT NOT NULL REFERENCES goals(goal_id),
            PRIMARY KEY(schedule_id,due_utc));
          CREATE TABLE IF NOT EXISTS owner_memory(
            key TEXT PRIMARY KEY, note TEXT NOT NULL,
            evidence_ref TEXT NOT NULL, updated_at TEXT NOT NULL,
            revision INTEGER NOT NULL);
          CREATE INDEX IF NOT EXISTS ix_goals_updated ON goals(updated_at DESC);
          CREATE INDEX IF NOT EXISTS ix_schedules_due ON schedules(status,next_due_utc);
        """)
        conn.commit()
    return conn


def create_goal(title, template, inputs, plan, *, db_path=None,
                source_schedule_id=None, source_slot=None, conn=None):
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 160:
        raise BrainError("Goal title must be 3-160 characters")
    if not isinstance(template, str) or not KEY.fullmatch(template):
        raise BrainError("Invalid goal template")
    if not isinstance(inputs, dict) or not isinstance(plan, list) or not 1 <= len(plan) <= 6:
        raise BrainError("Invalid goal inputs/plan")
    raw_inputs = _json(inputs)
    raw_plan = _json(plan)
    digest = hashlib.sha256(raw_plan.encode("utf-8")).hexdigest()
    now, goal_id = _now(), uuid4().hex
    values = (goal_id, title.strip(), template, raw_inputs, raw_plan, digest,
              "PLANNED", 0, None, now, now, None, source_schedule_id, source_slot)

    def insert(db):
        db.execute("INSERT INTO goals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
        db.execute("INSERT INTO goal_events(goal_id,at,name,detail_json)"
                   " VALUES(?,?,?,?)", (goal_id, now, "PLANNED", "{}"))
    if conn is not None:
        insert(conn)
    else:
        with closing(_connect(db_path, create=True)) as db, db:
            insert(db)
    return {"goal_id": goal_id, "status": "PLANNED", "plan_sha256": digest,
            "step_count": len(plan), "template": template, "title": title.strip()}


def get_goal(goal_id, *, db_path=None):
    _id(goal_id)
    db = _connect(db_path)
    if db is None:
        raise KeyError("Unknown goal")
    with closing(db):
        row = db.execute("SELECT * FROM goals WHERE goal_id=?", (goal_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown goal")
        result = dict(row)
        result["inputs"] = json.loads(result.pop("inputs_json"))
        result["plan"] = json.loads(result.pop("plan_json"))
        result["steps"] = [dict(x) for x in db.execute(
            "SELECT * FROM step_runs WHERE goal_id=? ORDER BY step_index",
            (goal_id,))]
        result["events"] = [
            {"at": e["at"], "name": e["name"], "detail": json.loads(e["detail_json"])}
            for e in db.execute("SELECT at,name,detail_json FROM goal_events "
                                "WHERE goal_id=? ORDER BY event_id", (goal_id,))
        ]
        return result


def list_goals(*, db_path=None, limit=30):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise BrainError("Invalid goal limit")
    db = _connect(db_path)
    if db is None:
        return []
    with closing(db):
        return [dict(row) for row in db.execute(
            "SELECT goal_id,title,template,status,current_step,plan_sha256,"
            "created_at,updated_at,error,source_schedule_id FROM goals "
            "ORDER BY updated_at DESC,rowid DESC LIMIT ?", (limit,))]


def change_state(goal_id, status, *, expected, error=None,
                 parent_task_id=None, db_path=None):
    _id(goal_id)
    if status not in STATES or expected not in STATES or status not in TRANSITIONS[expected]:
        raise BrainError("Forbidden goal transition")
    if error is not None and not isinstance(error, str):
        raise BrainError("Invalid error")
    now = _now()
    with closing(_connect(db_path, create=True)) as db, db:
        updated = db.execute(
            "UPDATE goals SET status=?,updated_at=?,"
            "error=?,parent_task_id=COALESCE(?,parent_task_id) "
            "WHERE goal_id=? AND status=?",
            (status, now, error[:160] if error else None, parent_task_id, goal_id, expected))
        if updated.rowcount != 1:
            raise BrainError("Goal state changed concurrently or is not eligible")
        db.execute("INSERT INTO goal_events(goal_id,at,name,detail_json)"
                   " VALUES(?,?,?,?)", (goal_id, now, status, "{}"))


def approve_goal(goal_id, sha256, *, db_path=None):
    if not isinstance(sha256, str) or not SHA.fullmatch(sha256):
        raise BrainError("Invalid SHA-256 confirmation")
    goal = get_goal(goal_id, db_path=db_path)
    if goal["plan_sha256"] != sha256:
        raise BrainError("Plan digest mismatch: review new plan before approval")
    change_state(goal_id, "APPROVED", expected="PLANNED", db_path=db_path)
    return {"goal_id": goal_id, "status": "APPROVED",
            "plan_sha256": sha256, "execution_authorized": False}


def claim_step(goal_id, index, skill_id, *, db_path=None):
    """Persist a no-retry dispatch marker before tool invocation."""
    _id(goal_id)
    if type(index) is not int or not 0 <= index <= 5:
        raise BrainError("Invalid step index")
    with closing(_connect(db_path, create=True)) as db, db:
        row = db.execute("SELECT status,current_step,plan_json FROM goals "
                         "WHERE goal_id=?", (goal_id,)).fetchone()
        if row is None or row["status"] != "RUNNING" or row["current_step"] != index:
            raise BrainError("Goal is not running at the requested step")
        plan = json.loads(row["plan_json"])
        if index >= len(plan) or plan[index]["skill_id"] != skill_id:
            raise BrainError("Step differs from immutable plan")
        current = db.execute("SELECT 1 FROM step_runs WHERE goal_id=? AND step_index=?",
                             (goal_id, index)).fetchone()
        if current is not None:
            raise BrainError("Step already dispatched; never replay it")
        now = _now()
        db.execute("INSERT INTO step_runs VALUES(?,?,?,?,?,?,?)",
                   (goal_id, index, skill_id, "DISPATCHING", None, now, now))
        db.execute("INSERT INTO goal_events(goal_id,at,name,detail_json)"
                   " VALUES(?,?,?,?)", (goal_id, now, "STEP_DISPATCHING",
                                        _json({"index": index, "skill_id": skill_id})))


def finish_step(goal_id, index, child_task_id, result_state, *, db_path=None):
    _id(goal_id)
    if result_state not in {"WAITING_APPROVAL", "SUCCEEDED", "FAILED"}:
        raise BrainError("Invalid step result")
    if not isinstance(child_task_id, str) or not ID.fullmatch(child_task_id):
        raise BrainError("Invalid S1 child task ID")
    with closing(_connect(db_path, create=True)) as db, db:
        row = db.execute(
            "SELECT status FROM step_runs WHERE goal_id=? AND step_index=?",
            (goal_id, index)).fetchone()
        if row is None or row["status"] != "DISPATCHING":
            raise BrainError("Step not in dispatch state")
        now = _now()
        db.execute("UPDATE step_runs SET child_task_id=?, status=?,updated_at=? "
                   "WHERE goal_id=? AND step_index=?",
                   (child_task_id, result_state, now, goal_id, index))
        if result_state == "SUCCEEDED":
            db.execute("UPDATE goals SET current_step=current_step+1,updated_at=? "
                       "WHERE goal_id=? AND status='RUNNING' AND current_step=?",
                       (now, goal_id, index))
        db.execute("INSERT INTO goal_events(goal_id,at,name,detail_json)"
                   " VALUES(?,?,?,?)",
                   (goal_id, now, "STEP_" + result_state,
                    _json({"index": index, "skill_id": ""})))  # do not log outputs


def resume_step(goal_id, index, result_state, *, db_path=None):
    _id(goal_id)
    if result_state not in {"WAITING_APPROVAL", "SUCCEEDED", "FAILED"}:
        raise BrainError("Invalid resumed result state")
    with closing(_connect(db_path, create=True)) as db, db:
        row = db.execute("SELECT status,child_task_id FROM step_runs "
                         "WHERE goal_id=? AND step_index=?", (goal_id, index)).fetchone()
        if row is None or row["status"] != "WAITING_APPROVAL" or not row["child_task_id"]:
            raise BrainError("Only waiting step with a S1 task may resume")
        now = _now()
        db.execute("UPDATE step_runs SET status=?,updated_at=? "
                   "WHERE goal_id=? AND step_index=?",
                   (result_state, now, goal_id, index))
        if result_state == "SUCCEEDED":
            db.execute("UPDATE goals SET current_step=current_step+1,updated_at=? "
                       "WHERE goal_id=? AND current_step=?", (now, goal_id, index))
        db.execute("INSERT INTO goal_events(goal_id,at,name,detail_json)"
                   " VALUES(?,?,?,?)",
                   (goal_id, now, "STEP_" + result_state, _json({"index": index})))



def rearm_failed_step(goal_id, step_index, child_task_id, *, db_path=None):
    """Owner-authorized retry of a *definitively failed* step.

    Keep the signed plan and successful prior step receipts. The replaced
    failed child remains in task_history and is referenced by an audit event.
    Ambiguous DISPATCHING/INTERRUPTED and successful quality reports cannot
    be replayed via this path.
    """
    _id(goal_id)
    _id(child_task_id)
    if type(step_index) is not int or not 0 <= step_index <= 5:
        raise BrainError("Invalid retry step")
    with closing(_connect(db_path, create=True)) as db, db:
        row = db.execute(
            "SELECT template,status,current_step,plan_json FROM goals WHERE goal_id=?",
            (goal_id,)).fetchone()
        if (row is None or row["template"] not in {"webapp.company", "creative.storyboard"}
                or row["status"] != "FAILED" or row["current_step"] != step_index):
            raise BrainError("Only allowlisted failed steps can be retried")
        plan = json.loads(row["plan_json"])
        # A storyboard draft uses one AI step and has no renderer or external
        # process. Do not broaden retry to media.compose/video_render: a
        # previous execution may have created local artifacts already.
        if row["template"] == "creative.storyboard" and not (
                step_index == 0 and len(plan) == 1
                and plan[0]["skill_id"] == "media.copy_draft"):
            raise BrainError("Only a failed storyboard model draft can be retried")
        failed = db.execute(
            "SELECT skill_id,status,child_task_id FROM step_runs "
            "WHERE goal_id=? AND step_index=?", (goal_id, step_index)).fetchone()
        if (failed is None or failed["status"] != "FAILED"
                or failed["child_task_id"] != child_task_id
                or failed["skill_id"] != plan[step_index]["skill_id"]):
            raise BrainError("Retry requires exact failed child task")
        if db.execute(
            "SELECT 1 FROM step_runs WHERE goal_id=? AND step_index>?",
            (goal_id, step_index)).fetchone() is not None:
            raise BrainError("Later steps exist; retry cannot overwrite history")
        now = _now()
        result = db.execute(
            "UPDATE goals SET status='APPROVED', parent_task_id=NULL, "
            "error=NULL, updated_at=? WHERE goal_id=? AND status='FAILED' "
            "AND current_step=?", (now, goal_id, step_index))
        if result.rowcount != 1:
            raise BrainError("Concurrent retry conflict")
        db.execute("DELETE FROM step_runs WHERE goal_id=? AND step_index=?",
                   (goal_id, step_index))
        db.execute(
            "INSERT INTO goal_events(goal_id,at,name,detail_json) VALUES(?,?,?,?)",
            (goal_id, now, "STEP_RETRY_ARMED",
             _json({"index": step_index, "skill_id": failed["skill_id"],
                    "previous_task_id": child_task_id})))
    return {"goal_id": goal_id, "status": "APPROVED",
            "retry_step": step_index, "previous_task_id": child_task_id,
            "automatic_replay": False, "model_invoked": False}


def count_status(status, *, db_path=None):
    """Exact global status count; never page recent goals or initialize schema."""
    if status not in STATES:
        raise BrainError("Invalid goal state")
    db = _connect(db_path)
    if db is None:
        return 0
    with closing(db):
        return db.execute("SELECT COUNT(*) FROM goals WHERE status=?",
                          (status,)).fetchone()[0]


def recover(*, db_path=None, return_ids=False):
    """Atomically interrupt every RUNNING goal; no replay or bounded listing.

    Default return is the historical integer. An explicit caller may request
    the exact changed IDs to reconcile corresponding S1 task state.
    """
    if type(return_ids) is not bool:
        raise BrainError("Invalid recovery result mode")
    source = Path(db_path) if db_path is not None else DB
    _safe(source)
    if not source.is_file():
        return [] if return_ids else 0
    changed_ids = []
    with closing(_connect(db_path, create=True)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("SELECT goal_id FROM goals WHERE status='RUNNING'").fetchall()
        for row in rows:
            now = _now()
            updated = db.execute(
                "UPDATE goals SET status='INTERRUPTED',updated_at=?,"
                "error='manual recovery: inspect possible side effects' "
                "WHERE goal_id=? AND status='RUNNING'", (now, row["goal_id"]))
            if updated.rowcount == 1:
                changed_ids.append(row["goal_id"])
                db.execute("INSERT INTO goal_events(goal_id,at,name,detail_json)"
                           " VALUES(?,?,?,?)",
                           (row["goal_id"], now, "INTERRUPTED", "{}"))
    return changed_ids if return_ids else len(changed_ids)



def interrupted_task_ids(*, db_path=None):
    """Idempotent S1 reconciliation targets for already INTERRUPTED S4 goals.

    Recovering S4 and S1 uses separate SQLite databases. If a process dies
    between them, a later explicit recovery must still find the linked S1
    tasks without replaying a dispatched step or paging recent history.
    """
    db = _connect(db_path)
    if db is None:
        return []
    with closing(db):
        return [row[0] for row in db.execute("""
            SELECT task_id FROM (
                SELECT parent_task_id AS task_id FROM goals
                 WHERE status='INTERRUPTED'
                UNION
                SELECT step_runs.child_task_id AS task_id FROM step_runs
                 JOIN goals ON goals.goal_id=step_runs.goal_id
                 WHERE goals.status='INTERRUPTED'
            ) WHERE task_id IS NOT NULL ORDER BY task_id
        """)]



def set_memory(key, note, evidence_ref, *, confirm_write=False, db_path=None):
    """Owner-managed notes, not autonomous fact learning or hidden prompts."""
    if confirm_write is not True:
        raise PermissionError("Owner confirmation required for memory writes")
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise BrainError("Invalid memory key")
    if not isinstance(note, str) or not 1 <= len(note) <= 600:
        raise BrainError("Invalid memory note")
    if not isinstance(evidence_ref, str) or not 3 <= len(evidence_ref) <= 160:
        raise BrainError("Evidence reference required")
    now = _now()
    with closing(_connect(db_path, create=True)) as db, db:
        db.execute("INSERT INTO owner_memory VALUES (?,?,?,?,1) "
                   "ON CONFLICT(key) DO UPDATE SET note=excluded.note,"
                   "evidence_ref=excluded.evidence_ref,"
                   "updated_at=excluded.updated_at,revision=owner_memory.revision+1",
                   (key, note, evidence_ref, now))
        row = db.execute("SELECT key,revision FROM owner_memory WHERE key=?",
                         (key,)).fetchone()
    return {"key": row["key"], "revision": row["revision"], "owner_recorded": True}


def list_memory(*, db_path=None):
    db = _connect(db_path)
    if db is None:
        return []
    with closing(db):
        return [dict(x) for x in db.execute("SELECT key,note,evidence_ref,"
                                           "revision,updated_at FROM owner_memory "
                                           "ORDER BY key LIMIT 100")]
