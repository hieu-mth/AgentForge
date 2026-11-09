"""Additive, source-bound artifact acceptance; never changes execution history.

Only trusted producers record evidence. HTTP accepts Owner decisions, not QA
claims. Generated JS is never executed here. Legacy reads do not create tables.
"""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from agentforge import task_history

STATES = frozenset({"DRAFT", "NEEDS_VALIDATION", "NEEDS_REVISION",
                    "READY_FOR_REVIEW", "ACCEPTED", "REJECTED"})
POLICIES = {
    "static_website": ("CONTRACT_VALID",),
    "interactive_website": ("CONTRACT_VALID", "SYNTAX_VALID", "BROWSER_VALID"),
    "react_template": ("CONTRACT_VALID", "TOOLCHAIN_CURRENT", "SYNTAX_VALID", "BUILD_VALID", "BROWSER_VALID"),
    "react_ai": ("CONTRACT_VALID", "TOOLCHAIN_CURRENT", "SYNTAX_VALID", "BUILD_VALID", "BROWSER_VALID"),
}
CHECKS = frozenset({"CONTRACT_VALID", "TOOLCHAIN_CURRENT", "SYNTAX_VALID", "BUILD_VALID", "BROWSER_VALID", "REVIEW"})


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sha(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _identity(proposal_id, source_sha):
    import re
    if (not isinstance(proposal_id, str) or not re.fullmatch(r"[a-f0-9]{32}", proposal_id)
            or not isinstance(source_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", source_sha)):
        raise ValueError("ACCEPTANCE_INVALID_SOURCE")


def _connect(db_path, *, write=False):
    path = task_history._path(db_path)
    if not write and not path.is_file():
        return None
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    if write:
        db.executescript("""
          CREATE TABLE IF NOT EXISTS artifact_acceptance(
            proposal_id TEXT NOT NULL, source_sha TEXT NOT NULL, artifact_type TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0, decision TEXT, decision_evidence TEXT,
            PRIMARY KEY(proposal_id,source_sha));
          CREATE TABLE IF NOT EXISTS artifact_validations(
            seq INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL,
            source_sha TEXT NOT NULL, kind TEXT NOT NULL, outcome TEXT NOT NULL,
            evidence_id TEXT NOT NULL, at TEXT NOT NULL,
            UNIQUE(proposal_id,source_sha,kind,evidence_id));
          CREATE TABLE IF NOT EXISTS artifact_decisions(
            seq INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL,
            source_sha TEXT NOT NULL, decision TEXT NOT NULL, evidence_sha TEXT NOT NULL,
            revision INTEGER NOT NULL, at TEXT NOT NULL);
        """)
    elif db.execute("SELECT 1 FROM sqlite_master WHERE name='artifact_acceptance'").fetchone() is None:
        db.close()
        return None
    return db


def _register(db, pid, sha, artifact_type):
    if artifact_type not in POLICIES:
        raise ValueError("ACCEPTANCE_UNKNOWN_ARTIFACT_TYPE")
    db.execute("INSERT OR IGNORE INTO artifact_acceptance(proposal_id,source_sha,artifact_type) VALUES(?,?,?)",
               (pid, sha, artifact_type))
    row = db.execute("SELECT artifact_type FROM artifact_acceptance WHERE proposal_id=? AND source_sha=?",
                     (pid, sha)).fetchone()
    if row[0] != artifact_type:
        raise ValueError("ACCEPTANCE_TYPE_MISMATCH")


def record_validation(pid, sha, artifact_type, kind, outcome, evidence_id, *, db_path=None):
    """Internal trusted-producer interface, deliberately not exposed as HTTP input."""
    _identity(pid, sha)
    doc, actual_type = source(pid, sha, "proposals" if artifact_type.endswith("website") else "webapps")
    if actual_type != artifact_type:
        raise ValueError("ACCEPTANCE_TYPE_MISMATCH")
    if kind == "TOOLCHAIN_CURRENT" and outcome == "PASS":
        from agentforge.domains.webapps.toolchain import require_current
        require_current(doc["files"])
    if (kind not in CHECKS or outcome not in ({"REVISE", "MANUAL_REVIEW"} if kind == "REVIEW" else {"PASS", "FAIL"})
            or not isinstance(evidence_id, str) or not 1 <= len(evidence_id) <= 128):
        raise ValueError("ACCEPTANCE_INVALID_EVIDENCE")
    with closing(_connect(db_path, write=True)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _register(db, pid, sha, artifact_type)
        inserted = db.execute("INSERT OR IGNORE INTO artifact_validations"
                              "(proposal_id,source_sha,kind,outcome,evidence_id,at) VALUES(?,?,?,?,?,?)",
                              (pid, sha, kind, outcome, evidence_id, datetime.now(timezone.utc).isoformat()))
        if inserted.rowcount:
            db.execute("UPDATE artifact_acceptance SET revision=revision+1 WHERE proposal_id=? AND source_sha=?",
                       (pid, sha))
        else:
            prior = db.execute("SELECT outcome FROM artifact_validations WHERE proposal_id=? AND source_sha=? "
                               "AND kind=? AND evidence_id=?", (pid, sha, kind, evidence_id)).fetchone()
            if prior[0] != outcome:
                raise ValueError("ACCEPTANCE_EVIDENCE_CONFLICT")


def _view(db, pid, sha, artifact_type):
    row = None if db is None else db.execute(
        "SELECT * FROM artifact_acceptance WHERE proposal_id=? AND source_sha=?", (pid, sha)).fetchone()
    if row is not None and row["artifact_type"] != artifact_type:
        raise ValueError("ACCEPTANCE_TYPE_MISMATCH")
    reports = [] if db is None else [dict(r) for r in db.execute(
        "SELECT kind,outcome,evidence_id FROM artifact_validations WHERE proposal_id=? AND source_sha=? ORDER BY seq",
        (pid, sha))]
    latest = {report["kind"]: report for report in reports}
    # Failed build tasks from the trusted runner also invalidate earlier evidence.
    # A successful later build replaces that failure only when recorded explicitly.
    failed_build = None
    if db is not None and db.execute("SELECT 1 FROM sqlite_master WHERE name='tasks'").fetchone():
        for task in db.execute("SELECT task_id,status,request_json FROM tasks WHERE skill_id='webapp.sandbox_test' "
                               "AND status IN ('SUCCEEDED','FAILED') ORDER BY rowid"):
            request = json.loads(task["request_json"])
            if request.get("proposal_id") == pid and request.get("sha256") == sha:
                failed_build = task["task_id"] if task["status"] == "FAILED" else None
    if failed_build:
        latest["BUILD_VALID"] = {"kind": "BUILD_VALID", "outcome": "FAIL", "evidence_id": failed_build}
    required = list(POLICIES[artifact_type])
    missing = [check for check in required if latest.get(check, {}).get("outcome") != "PASS"]
    evidence_sha = _sha({"source_sha": sha, "artifact_type": artifact_type, "reports": latest})
    if row is not None and row["decision"] == "REJECTED":
        status = "REJECTED"
    elif (any(r["outcome"] == "FAIL" for r in latest.values())
          or latest.get("REVIEW", {}).get("outcome") == "REVISE"):
        status = "NEEDS_REVISION"
    elif missing:
        status = "NEEDS_VALIDATION"
    elif row is not None and row["decision"] == "ACCEPTED" and row["decision_evidence"] == evidence_sha:
        status = "ACCEPTED"
    else:
        status = "READY_FOR_REVIEW"
    return {"proposal_id": pid, "source_sha": sha, "artifact_type": artifact_type,
            "status": status, "required_checks": required, "missing_checks": missing,
            "checks": latest, "revision": row["revision"] if row else 0,
            "evidence_sha": evidence_sha, "owner_accepted": status == "ACCEPTED",
            "interactive_preview_enabled": False}


def source(pid, sha, namespace):
    _identity(pid, sha)
    if namespace == "webapps":
        from agentforge import webapp_developer as dev
        provider = dev.provider(pid)
        doc, _ = provider._read_proposal(pid)
        artifact_type = "react_template" if provider is dev.base else "react_ai"
    elif namespace == "proposals":
        from agentforge import product_builder
        doc, _ = product_builder._read_proposal(pid)
        artifact_type = "interactive_website" if any(
            f["path"].endswith(".js") or (f["path"].endswith(".html") and "<script" in f["content"].lower())
            for f in doc["files"]) else "static_website"
        product_builder._require_static_quality(next(f["content"] for f in doc["files"] if f["path"] == "index.html"))
    else:
        raise ValueError("ACCEPTANCE_UNKNOWN_NAMESPACE")
    if doc["sha256"] != sha:
        raise PermissionError("ACCEPTANCE_SOURCE_STALE")
    return doc, artifact_type


def inspect(pid, sha, namespace="webapps", *, db_path=None):
    _, artifact_type = source(pid, sha, namespace)
    db = _connect(db_path)
    try:
        return _view(db, pid, sha, artifact_type)
    finally:
        if db is not None:
            db.close()


def decide(pid, sha, namespace, decision, *, expected_revision, evidence_sha, confirm=False, db_path=None):
    if confirm is not True or decision not in {"ACCEPTED", "REJECTED"}:
        raise PermissionError("ACCEPTANCE_OWNER_CONFIRMATION_REQUIRED")
    _, artifact_type = source(pid, sha, namespace)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("ACCEPTANCE_INVALID_REVISION")
    with closing(_connect(db_path, write=True)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _register(db, pid, sha, artifact_type)
        current = _view(db, pid, sha, artifact_type)
        if current["revision"] != expected_revision or current["evidence_sha"] != evidence_sha:
            raise PermissionError("ACCEPTANCE_REVIEW_STALE")
        if current["status"] in {"ACCEPTED", "REJECTED"}:
            raise PermissionError("ACCEPTANCE_DECISION_FINAL")
        if decision == "ACCEPTED" and current["status"] != "READY_FOR_REVIEW":
            raise PermissionError("ACCEPTANCE_VALIDATION_REQUIRED")
        db.execute("UPDATE artifact_acceptance SET decision=?,decision_evidence=?,revision=revision+1 "
                   "WHERE proposal_id=? AND source_sha=? AND revision=?",
                   (decision, evidence_sha, pid, sha, expected_revision))
        db.execute("INSERT INTO artifact_decisions(proposal_id,source_sha,decision,evidence_sha,revision,at) "
                   "VALUES(?,?,?,?,?,?)", (pid, sha, decision, evidence_sha, expected_revision + 1,
                                          datetime.now(timezone.utc).isoformat()))
        return _view(db, pid, sha, artifact_type)


def observe(skill_id, result, *, db_path=None):
    """Record a result only after the existing trusted skill output contract passes."""
    if not isinstance(result, dict) or not result.get("proposal_id") or not result.get("sha256"):
        return
    pid, sha = result["proposal_id"], result["sha256"]
    if skill_id in {"web.create", "webapp.create", "webapp.develop"}:
        namespace = "proposals" if skill_id == "web.create" else "webapps"
        _, kind = source(pid, sha, namespace)
        record_validation(pid, sha, kind, "CONTRACT_VALID", "PASS", "proposal:" + sha, db_path=db_path)
        if namespace == "webapps":
            record_validation(pid, sha, kind, "TOOLCHAIN_CURRENT", "PASS", "toolchain:" + sha, db_path=db_path)
    elif skill_id in {"webapp.audit", "webapp.review", "webapp.sandbox_test"}:
        _, kind = source(pid, sha, "webapps")
        if skill_id == "webapp.review":
            from agentforge.domains.webapps import reviewer
            report = reviewer.read(result["review_id"], result["review_sha"])
            record_validation(pid, sha, kind, "REVIEW", report["assessment"]["recommendation"],
                              result["review_sha"], db_path=db_path)
        elif skill_id == "webapp.audit":
            from agentforge.domains.webapps import static_qa
            report = static_qa.read(result["qa_report_id"], result["qa_report_sha"])
            if "syntax" in report:
                record_validation(pid, sha, kind, "SYNTAX_VALID", report["syntax"]["status"],
                                  result["qa_report_sha"], db_path=db_path)
        elif (result.get("status") == "PASS" and result.get("runtime") == "docker-local-linux"
              and result.get("network") == "none" and result.get("source_mount") == "read_only"):
            record_validation(pid, sha, kind, "BUILD_VALID", "PASS", _sha(result), db_path=db_path)


def for_task(task, *, db_path=None):
    result = task.get("result")
    if not isinstance(result, dict) or not result.get("proposal_id") or not result.get("sha256"):
        return None
    namespace = "proposals" if task.get("skill_id") == "web.create" else "webapps"
    try:
        return inspect(result["proposal_id"], result["sha256"], namespace, db_path=db_path)
    except (ValueError, KeyError, OSError, PermissionError):
        return {"status": "NEEDS_VALIDATION", "owner_accepted": False, "reason": "SOURCE_UNAVAILABLE_OR_STALE"}


def for_goal(goal, *, task_db_path=None):
    for step in reversed(goal.get("steps", [])):
        if step.get("child_task_id"):
            try:
                found = for_task(task_history.get_task(step["child_task_id"], db_path=task_db_path), db_path=task_db_path)
                if found is not None:
                    return found
            except (KeyError, ValueError, OSError):
                continue
    return None
