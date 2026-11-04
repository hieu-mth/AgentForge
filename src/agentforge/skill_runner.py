"""S1 allowlisted skill adapters; explicit per-call grants and durable results.

This is a local owner CLI, not OS isolation or multi-user authentication.
"""
import argparse
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from agentforge import skill_registry as registry
from agentforge import task_history as history

# Code-level policy: manifests cannot silently remove required grants.
POLICY = {
    "web.quality_check": ("product_builder", "read_only",
                          frozenset({"workspace.read"})),
    "web.create": ("product_builder", "owner_gated",
                   frozenset({"model.invoke", "workspace.propose"})),
    "web.browser_test": ("product_builder", "owner_gated",
                         frozenset({"workspace.read", "browser.run"})),
    "research.opportunity": ("opportunity_researcher", "owner_gated",
                             frozenset({"model.invoke", "network.search", "workspace.write"})),
    "research.source_review": ("source_reviewer", "owner_gated",
                               frozenset({"workspace.read", "workspace.write",
                                          "model.invoke", "network.read"})),
}


def _contract(skill_id):
    skill = registry.load_skill(skill_id)
    if skill_id not in POLICY:
        raise PermissionError("Skill has no trusted adapter")
    worker, mode, grants = POLICY[skill_id]
    if (skill["worker_id"] != worker or skill["execution_mode"] != mode
            or set(skill["required_permissions"]) != grants):
        raise PermissionError("Manifest differs from fixed adapter policy")
    return skill, grants


def missing_grants(skill_id, granted=(), *, confirm_model_call=False,
                   confirm_browser_run=False, payload=None):
    _, needed = _contract(skill_id)
    granted = frozenset(granted)
    if not granted.issubset(registry.PERMISSIONS):
        raise PermissionError("Unknown permission grant")
    missing = set(needed - (granted | {"workspace.read"}))
    if "model.invoke" in needed and confirm_model_call is not True:
        missing.add("confirm_model_call")
    if "browser.run" in needed and confirm_browser_run is not True:
        missing.add("confirm_browser_run")
    if skill_id == "web.browser_test" and (
        not isinstance(payload, dict) or payload.get("confirm_browser_run") is not True
    ):
        missing.add("input.confirm_browser_run")
    if skill_id == "research.source_review" and (
        not isinstance(payload, dict) or payload.get("approve_read_only") is not True
    ):
        missing.add("input.approve_read_only")
    return sorted(missing)


def _dispatch(skill_id, payload):
    if skill_id == "web.quality_check":
        from agentforge.product_quality import check_project
        return check_project(payload["slug"])
    if skill_id == "web.create":
        from agentforge.product_builder import propose
        return propose(payload["slug"], payload["brief"])
    if skill_id == "web.browser_test":
        from agentforge.browser_validation import validate
        return validate("project", payload["slug"], confirm_browser_run=True,
                        browser_channel=payload.get("browser_channel", "msedge"))
    if skill_id == "research.opportunity":
        from agentforge.research import run
        with redirect_stdout(StringIO()):
            return run(payload["topic"])
    if skill_id == "research.source_review":
        from agentforge.source_review import run_review
        with redirect_stdout(StringIO()):
            return run_review(payload["task_id"], payload["allowed_hosts"],
                              max_pages=payload.get("max_pages", 4),
                              approve_read_only=True)
    raise PermissionError("No trusted adapter")


def _execute(task_id, skill_id, payload, *, grants, confirm_model_call,
             confirm_browser_run, db_path):
    missing = missing_grants(skill_id, grants, confirm_model_call=confirm_model_call,
                             confirm_browser_run=confirm_browser_run, payload=payload)
    if missing:
        result = {"task_id": task_id, "skill_id": skill_id,
                  "status": "WAITING_APPROVAL", "missing": missing, "executed": False}
        if history.get_task(task_id, db_path=db_path)["status"] == "QUEUED":
            history.transition(task_id, "WAITING_APPROVAL", result=result, db_path=db_path)
        return result
    history.transition(task_id, "RUNNING", db_path=db_path)
    # Only permission NAMES/booleans enter audit, never tokens or payloads.
    _, required = _contract(skill_id)
    history.checkpoint(
        task_id, "POLICY_GRANTED",
        {"required": sorted(required),
         "model_confirmed": confirm_model_call is True,
         "browser_confirmed": confirm_browser_run is True},
        db_path=db_path,
    )
    try:
        result = _dispatch(skill_id, payload)
        registry.validate_payload(registry.load_skill(skill_id), result, direction="output")
        history.transition(task_id, "SUCCEEDED", result=result, db_path=db_path)
        return {"task_id": task_id, "skill_id": skill_id,
                "status": "SUCCEEDED", "executed": True, "result": result}
    except Exception as exc:
        # Do not serialize raw model text, URLs or secrets from exceptions.
        error = f"{type(exc).__name__}: execution failed; inspect original module logs"
        history.transition(task_id, "FAILED", error=error, db_path=db_path)
        return {"task_id": task_id, "skill_id": skill_id,
                "status": "FAILED", "executed": True, "error": error}


def invoke(skill_id, payload, *, grants=(), confirm_model_call=False,
           confirm_browser_run=False, parent_id=None, db_path=None):
    skill, _ = _contract(skill_id)
    registry.validate_payload(skill, payload)
    # Reject malformed grants before recording a runnable task.
    missing_grants(skill_id, grants, confirm_model_call=confirm_model_call,
                   confirm_browser_run=confirm_browser_run, payload=payload)
    task_id = history.create_task("skill", skill_id, payload,
                                  parent_id=parent_id, db_path=db_path)
    return _execute(task_id, skill_id, payload, grants=grants,
                    confirm_model_call=confirm_model_call,
                    confirm_browser_run=confirm_browser_run, db_path=db_path)


def resume_waiting(task_id, *, grants=(), confirm_model_call=False,
                   confirm_browser_run=False, db_path=None):
    task = history.get_task(task_id, db_path=db_path)
    if task["kind"] != "skill" or task["status"] != "WAITING_APPROVAL":
        raise ValueError("Only never-started approval tasks may be resumed")
    skill, _ = _contract(task["skill_id"])
    registry.validate_payload(skill, task["request"])
    return _execute(task_id, task["skill_id"], task["request"], grants=grants,
                    confirm_model_call=confirm_model_call,
                    confirm_browser_run=confirm_browser_run, db_path=db_path)


def main():
    parser = argparse.ArgumentParser(description="S1 owner-gated skill invocation")
    commands = parser.add_subparsers(dest="command", required=True)
    invoke_cmd = commands.add_parser("invoke")
    invoke_cmd.add_argument("skill_id")
    invoke_cmd.add_argument("--input-json")
    invoke_cmd.add_argument("--input-file")
    invoke_cmd.add_argument("--slug", help="Convenience for web quality/browser test")
    resume_cmd = commands.add_parser("resume")
    resume_cmd.add_argument("task_id")
    for cmd in (invoke_cmd, resume_cmd):
        cmd.add_argument("--grant", action="append", default=[])
        cmd.add_argument("--confirm-model-call", action="store_true")
        cmd.add_argument("--confirm-browser-run", action="store_true")
    args = parser.parse_args()
    if args.command == "resume":
        result = resume_waiting(args.task_id, grants=args.grant,
                                confirm_model_call=args.confirm_model_call,
                                confirm_browser_run=args.confirm_browser_run)
    else:
        if sum(x is not None for x in (args.slug, args.input_json, args.input_file)) != 1:
            parser.error("Use exactly one of --slug, --input-json, --input-file")
        if args.slug is not None:
            if args.skill_id not in {"web.quality_check", "web.browser_test"}:
                parser.error("--slug is limited to web.quality_check/web.browser_test")
            payload = {"slug": args.slug}
            if args.skill_id == "web.browser_test":
                payload.update(confirm_browser_run=args.confirm_browser_run,
                               browser_channel="msedge")
        elif args.input_file is not None:
            path = Path(args.input_file)
            if path.stat().st_size > 8192:
                parser.error("JSON input too large")
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        else:
            payload = json.loads(args.input_json)
        result = invoke(args.skill_id, payload, grants=args.grant,
                        confirm_model_call=args.confirm_model_call,
                        confirm_browser_run=args.confirm_browser_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] == "FAILED":
        parser.exit(2)
    if result["status"] == "WAITING_APPROVAL":
        parser.exit(3)


if __name__ == "__main__":
    main()
