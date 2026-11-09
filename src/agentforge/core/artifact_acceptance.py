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
