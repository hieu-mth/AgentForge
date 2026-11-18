"""Read-only Owner bootstrap and artifact presentation."""
from agentforge import analytics_store, brain_scheduler, brain_store
from agentforge import skill_registry, task_history, result_view, ops_control
from agentforge.core import artifact_acceptance
from agentforge.core.public_serialization import _artifact_names, _task_public


def _public_task(task, *, db_path=None):
    output = _task_public(task)
    output["artifact_acceptance"] = artifact_acceptance.for_task(task, db_path=db_path)
    output["artifacts"] = _artifact_names(task.get("result"))
    output["report"] = result_view.present(task.get("skill_id"), task.get("result")) if (
        task.get("status") == "SUCCEEDED" or
        (task.get("skill_id") == "terminal.check" and task.get("status") == "FAILED")) else None
    return output


def _owner_attention(goals, tasks, schedules, daemon):
    """Deterministic, local and read-only owner inbox with bounded summaries."""
    items = []
    for goal in goals[:40]:
        status = goal["status"]
        if status not in {"WAITING_APPROVAL", "FAILED", "INTERRUPTED"}:
            continue
        items.append({
            "kind": "goal", "id": goal["goal_id"], "status": status,
            "title": goal["title"][:160],
            "priority": "HIGH" if status == "WAITING_APPROVAL" else "REVIEW",
        })
        if len(items) >= 8:
            break
    if len(items) < 8:
        for task in tasks[:40]:
            if task["status"] != "INTERRUPTED" or task["kind"] != "skill":
                continue
            items.append({"kind": "task", "id": task["task_id"],
                          "status": "INTERRUPTED", "title": task["skill_id"][:80],
                          "priority": "REVIEW"})
            if len(items) >= 8:
                break
    if any(x["status"] == "ACTIVE" for x in schedules) and not daemon.get("fresh"):
        items.append({"kind": "schedules", "id": "",
                      "status": "NOT_RUNNING", "title": "Lịch ACTIVE nhưng daemon không hoạt động",
                      "priority": "HIGH"})
    return items[:10]


def _summary(server):
    tasks = task_history.list_tasks(db_path=server.task_db_path, limit=100)
    goals = brain_store.list_goals(db_path=server.brain_db_path, limit=60)
    goals = [{**g, "artifact_acceptance": artifact_acceptance.for_goal(
        brain_store.get_goal(g["goal_id"], db_path=server.brain_db_path),
        task_db_path=server.task_db_path)} for g in goals]
    schedules = brain_scheduler.list_schedules(db_path=server.brain_db_path)
    datasets = analytics_store.list_datasets(db_path=server.analytics_db_path)
    health = {"status": "NOT_RUNNING", "fresh": False}
    try:
        from agentforge.ops_daemon import read_heartbeat
        health = read_heartbeat()
    except (OSError, ValueError):
        health = {"status": "UNKNOWN", "fresh": False}
    states = ("SUCCEEDED", "RUNNING", "WAITING_APPROVAL", "FAILED", "INTERRUPTED")
    return {
        "version": "v1", "local_only": True, "authenticated": True,
        "external_actions_enabled": server.allow_external_actions,
        "stats": {"tasks": len(tasks), "skills": len(skill_registry.load_registry()),
                  "goals": len(goals),
                  **{x.lower(): sum(t["status"] == x for t in tasks) for x in states}},
        "tasks": [_public_task(t, db_path=server.task_db_path) for t in tasks[:40]],
        "goals": goals, "schedules": schedules,
        "skills": [{"id": k, "worker": v["worker_id"],
                    "mode": v["execution_mode"]}
                   for k, v in skill_registry.load_registry().items()],
        "datasets": [{"dataset": x["dataset"], "synthetic": bool(x["synthetic"]),
                      "performance_rows": x["performance_rows"],
                      "ledger_rows": x["ledger_rows"]} for x in datasets[:30]],
        "daemon": health,
        "operations": ops_control.read(),
        "attention": _owner_attention(goals, tasks, schedules, health),
        "connectors": [
            {"name": "YouTube", "status": "MANUAL_HANDOFF_ONLY",
             "authenticated": False, "automated_upload": False},
            {"name": "TikTok", "status": "MANUAL_HANDOFF_ONLY",
             "authenticated": False, "automated_upload": False},
        ],
    }
