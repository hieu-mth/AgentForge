"""Read-only dependency projection over the existing worker and skill manifests."""
from agentforge.ai import model_hub, worker_registry
from agentforge.core import brain_store, skill_registry, task_history
from agentforge.core.skill_adapters import POLICY

TOOL_DEPENDENCIES = {
    "filesystem": ["workspace"],
    "sqlite": ["python.sqlite3"],
    "model": ["configured model provider"],
    "search": ["network", "DDGS"],
    "https_reader": ["network", "HTTPS"],
    "browser": ["Playwright", "local browser or Docker QA image"],
    "raster": ["Pillow"],
    "audio": ["Python audio runtime"],
    "ffmpeg": ["FFmpeg"],
    "tts_engine": ["configured local TTS engine"],
}


def inspect(*, brain_db_path=None, task_db_path=None):
    registry = skill_registry.load_registry()
    hub = model_hub.catalog()
    model_refs = {p["id"]: p for p in hub["profiles"]}
    recent = task_history.list_tasks(db_path=task_db_path, limit=60)
    recent_templates = brain_store.recent_skill_templates(db_path=brain_db_path)
    agents, skills = [], []
    for worker_id in sorted({skill["worker_id"] for skill in registry.values()}):
        worker = worker_registry.load_worker(worker_id)
        assigned = [skill for skill in registry.values() if skill["worker_id"] == worker_id]
        routes = [route for route in hub["routes"] if route.get("worker") == worker_id]
        consumes_model = any("model.invoke" in s["required_permissions"] for s in assigned)
        active = next((route for route in routes if route["runtime_wired"]), None)
        model_ref = ((active["model_ref"] if active else worker["model_ref"])
                     if consumes_model else None)
        model = model_refs.get(model_ref)
        skill_ids = {skill["id"] for skill in assigned}
        agents.append({
            "id": worker_id, "manifest": f"workers/{worker_id}/worker.toml",
            "instructions_path": f"workers/{worker_id}/instructions.md",
            "runtime": worker["runtime"], "capabilities": worker["capabilities"],
            "model_ref": model_ref,
            "model": {k: model[k] for k in ("id", "provider", "model", "enabled")} if model else None,
            "model_readiness": "UNKNOWN" if model_ref else "NOT_REQUIRED",
            "routes": [{"id": route["id"], "status": route["status"]} for route in routes],
            "skills": sorted(skill_ids),
            "permissions": sorted({p for s in assigned for p in s["required_permissions"]}),
            "tools": sorted({t for s in assigned for t in s["required_tools"]}),
            "recent_executions": [{key: row[key] for key in (
                "task_id", "skill_id", "status", "updated_at")}
                for row in recent if row["skill_id"] in skill_ids][:5],
        })
        for skill in assigned:
            skill_id = skill["id"]
            trusted = POLICY.get(skill_id)
            matches = trusted == (worker_id, skill["execution_mode"],
                                  frozenset(skill["required_permissions"]))
            skills.append({**skill, "manifest": f"skills/{skill_id}/skill.toml",
                           "adapter_status": "REGISTERED" if matches else "POLICY_MISMATCH",
                           "model_ref": model_ref if "model.invoke" in skill["required_permissions"] else None,
                           "observed_workflows": recent_templates.get(skill_id, [])})
    return {"model_config_revision": hub["revision"], "agents": agents,
            "models": [{k: p[k] for k in ("id", "provider", "model", "enabled", "health")}
                       for p in hub["profiles"]],
            "skills": skills,
            "rules": [{"id": permission, "source": "agentforge/core/skill_runner.py",
                       "skills": [s["id"] for s in skills if permission in s["required_permissions"]]}
                      for permission in sorted(skill_registry.PERMISSIONS)],
            "tools": [{"id": tool, "runtime_dependencies": TOOL_DEPENDENCIES.get(tool, []),
                       "skills": [s["id"] for s in skills if tool in s["required_tools"]]}
                      for tool in sorted(skill_registry.TOOLS)],
            "workflow_scope": "MOST_RECENT_30_SAVED_GOALS"}
