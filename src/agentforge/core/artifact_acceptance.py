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
