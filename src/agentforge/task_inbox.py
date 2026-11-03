"""Local-first review-task inbox for AgentForge Company Brain.

This module manages task metadata only. It never fetches URLs, calls a model,
or grants execution or spending permissions.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "company"
TASK_ID_PATTERN = re.compile(r"[a-f0-9]{32}-[a-z0-9-]{1,64}-review\Z")


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def task_path(task_id: str) -> Path:
    if not isinstance(task_id, str) or not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError("Invalid review task ID")
    return DATA_DIR / "tasks" / f"{task_id.removesuffix('-review')}.json"


def read_task(task_id: str) -> dict:
    path = task_path(task_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("task_id") != task_id:
        raise ValueError("Task ID does not match task file")
    if data.get("kind") != "SOURCE_REVIEW":
        raise ValueError("Unsupported task type")
    if data.get("execution_authorized") is not False:
        raise PermissionError("Task must not authorize execution")
    if data.get("spending_authorized") is not False:
        raise PermissionError("Task must not authorize spending")
    return data


def list_tasks() -> list[dict]:
    directory = DATA_DIR / "tasks"
    if not directory.exists():
        return []
    tasks = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            task_id = raw.get("task_id") if isinstance(raw, dict) else None
            if task_path(task_id) != path:
                raise ValueError("Task filename mismatch")
            tasks.append(read_task(task_id))
        except (ValueError, OSError, KeyError, TypeError, PermissionError) as error:
            raise ValueError(f"Invalid task file {path.name}: {error}") from error
    return tasks


def save_task(task_id: str, payload: dict):
    path = task_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def defer_task(task_id: str, reason: str) -> dict:
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A reason is required")
    task = read_task(task_id)
    if task.get("status") != "PROPOSED":
        raise ValueError("Only PROPOSED tasks can be deferred")
    task["status"] = "DEFERRED"
    task.setdefault("history", []).append({
        "at": now_utc(), "action": "DEFER", "reason": reason.strip()[:500]
    })
    save_task(task_id, task)
    return task


def resume_task(task_id: str) -> dict:
    task = read_task(task_id)
    if task.get("status") != "DEFERRED":
        raise ValueError("Only DEFERRED tasks can be resumed")
    task["status"] = "PROPOSED"
    task.setdefault("history", []).append({
        "at": now_utc(), "action": "RESUME"
    })
    save_task(task_id, task)
    return task


def main():
    parser = argparse.ArgumentParser(description="AgentForge local review-task inbox")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("task_id")
    defer = commands.add_parser("defer")
    defer.add_argument("task_id")
    defer.add_argument("--reason", required=True)
    resume = commands.add_parser("resume")
    resume.add_argument("task_id")
    args = parser.parse_args()

    if args.command == "list":
        tasks = list_tasks()
        print("TASKS:", len(tasks))
        for task in tasks:
            print(task["task_id"], "|", task.get("status"), "|", task.get("opportunity_id"))
        return
    if args.command == "show":
        print(json.dumps(read_task(args.task_id), ensure_ascii=False, indent=2))
        return
    if args.command == "defer":
        task = defer_task(args.task_id, args.reason)
    else:
        task = resume_task(args.task_id)
    print("TASK ID:", task["task_id"])
    print("STATUS:", task["status"])
    print("EXECUTION AUTHORIZED:", task["execution_authorized"])
    print("SPENDING AUTHORIZED:", task["spending_authorized"])


if __name__ == "__main__":
    main()
