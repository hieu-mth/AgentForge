"""AgentForge local-only operations doctor.

Read-only checks: installed registries, SQLite integrity, abandoned RUNNING
tasks/goals, scheduler heartbeat and backup inventory. No network, model,
automatic recovery, data mutations, service installation or publishing.
"""
import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from agentforge import analytics_store, brain_store, growth_store
from agentforge import skill_registry, task_history
from agentforge import ops_backup, ops_daemon

ROOT = brain_store.ROOT
SQLITE_DEFAULTS = {
    "S1 tasks": task_history.DEFAULT_DB,
    "S3 analytics": analytics_store.DB,
    "S4 goals": brain_store.DB,
    "S5 growth": growth_store.DB,
}


def _integrity(path):
    ops_backup._safe(path)
    if not path.exists():
        return {"status": "NOT_CREATED", "size_bytes": 0}
    if not path.is_file():
        return {"status": "INVALID_PATH", "size_bytes": None}
    try:
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro",
                                     uri=True, timeout=2)) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()
            status = "PASS" if result and result[0] == "ok" else "FAIL"
        return {"status": status, "size_bytes": path.stat().st_size}
    except (sqlite3.DatabaseError, OSError, ValueError):
        return {"status": "FAIL", "size_bytes": None}


def inspect(*, paths=None, backup_dir=None, task_db=None, brain_db=None,
            heartbeat_path=None):
    """No side effects. Detailed findings do not expose prompts/PII."""
    dbs = paths if paths is not None else SQLITE_DEFAULTS
    status = {name: _integrity(Path(p)) for name, p in dbs.items()}
    findings = []
    for name, value in status.items():
        if value["status"] in {"FAIL", "INVALID_PATH"}:
            findings.append({"severity": "FAIL", "rule": "sqlite_integrity",
                             "name": name})
        elif value["status"] == "NOT_CREATED":
            findings.append({"severity": "INFO", "rule": "database_not_initialized",
                             "name": name})
    try:
        registry = skill_registry.load_registry()
        registry_valid = bool(registry)
    except (ValueError, PermissionError, OSError, KeyError, TypeError):
        registry_valid = False
    if not registry_valid:
        findings.append({"severity": "FAIL", "rule": "skill_registry_invalid"})
    tasks = task_history.list_tasks(db_path=task_db, limit=200) if (
        (Path(task_db) if task_db else task_history.DEFAULT_DB).exists()) else []
    goals = brain_store.list_goals(db_path=brain_db, limit=100)
    running_tasks = sum(x["status"] == "RUNNING" for x in tasks)
    running_goals = sum(x["status"] == "RUNNING" for x in goals)
    if running_tasks or running_goals:
        findings.append({"severity": "WARN", "rule": "inflight_tasks_manual_review",
                         "tasks": running_tasks, "goals": running_goals})
    heartbeat = ops_daemon.read_heartbeat(path=heartbeat_path)
    if heartbeat.get("status") == "ERROR":
        findings.append({"severity": "WARN", "rule": "scheduler_last_tick_error"})
    backup_root = Path(backup_dir) if backup_dir is not None else ops_backup.OUT
    ops_backup._safe(backup_root)
    archives = (sorted(backup_root.glob("agentforge-*.zip"), reverse=True)
                if backup_root.is_dir() else [])
    latest = archives[0].name if archives else None
    if not archives:
        findings.append({"severity": "WARN", "rule": "no_local_backups"})
    return {
        "status": "FAIL" if any(f["severity"] == "FAIL" for f in findings)
        else "REVIEW_REQUIRED" if any(f["severity"] == "WARN" for f in findings)
        else "PASS",
        "local_only": True,
        "registry_valid": registry_valid,
        "databases": status,
        "running_tasks": running_tasks,
        "running_goals": running_goals,
        "scheduler": {"status": heartbeat.get("status", "NOT_RUNNING"),
                      "fresh": heartbeat.get("fresh", False)},
        "backup_count": len(archives),
        "latest_backup_name": latest,
        "findings": findings,
        "external_accounts_connected": False,
        "verified_revenue": False,
        "automatic_recovery_performed": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only AgentForge local health doctor")
    parser.add_argument("--strict", action="store_true",
                        help="Exit nonzero for warnings as well as failures")
    args = parser.parse_args()
    result = inspect()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] == "FAIL" or (
            args.strict and result["status"] != "PASS"):
        parser.exit(2)


if __name__ == "__main__":
    main()
