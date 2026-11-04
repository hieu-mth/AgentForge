"""S4 Company Brain owner CLI: goals, immutable plan review, delegation, tick.

No autonomous background daemon, model-selected arbitrary tool, social
publisher or spending action. Every S1 tool permission is checked again.
"""
import argparse
import json
from pathlib import Path

from agentforge import brain_planner as planner
from agentforge import brain_runner as runner
from agentforge import brain_scheduler as scheduler
from agentforge import brain_store as store
from agentforge import analytics_pipeline


def _input_file(path):
    file = Path(path)
    store._safe(file)
    if not file.is_file() or file.stat().st_size > 8192:
        raise store.BrainError("Input must be a local JSON file <= 8KB")
    result = json.loads(file.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise store.BrainError("Goal inputs must be a JSON object")
    return result


def demo(*, confirm_demo=False):
    """Explicit owner-consented synthetic data + real read-only S4 pipeline."""
    if confirm_demo is not True:
        raise PermissionError("Explicit --confirm-demo required for local synthetic writes")
    seed = analytics_pipeline.synthetic_demo()
    if seed["status"] != "SUCCEEDED" or seed.get("synthetic") is not True:
        return {"status": "FAILED", "stage": "synthetic_seed"}
    goal = planner.propose(
        "Review synthetic mattress campaign", "campaign.review",
        {"dataset": seed["dataset"], "campaign": "nem-shorts"})
    store.approve_goal(goal["goal_id"], goal["plan_sha256"])
    result = runner.execute(goal["goal_id"])
    return {
        "status": result["status"], "synthetic": True,
        "dataset": seed["dataset"], "goal_id": goal["goal_id"],
        "goal_task_id": result.get("task_id"),
        "planned_steps": goal["step_count"],
        "completed_steps": result.get("executed_steps"),
        "seed_imports": len(seed["imports"]),
        "seed_reports": len(seed["reports"]),
        "external_data_verified": False,
        "spending_authorized": False, "publishing_authorized": False,
        "autonomous_background_running": False,
    }


def main():
    cli = argparse.ArgumentParser(description="S4 local-first Company Brain v0")
    sub = cli.add_subparsers(dest="command", required=True)
    propose = sub.add_parser("propose", help="Build an immutable fixed-template goal plan")
    propose.add_argument("template", choices=sorted(planner.TEMPLATES))
    propose.add_argument("--title", required=True)
    propose.add_argument("--input-file", required=True)
    propose.add_argument("--max-model-calls", type=int, default=0)
    propose.add_argument("--max-external-runs", type=int, default=0)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("goal_id")
    approval = sub.add_parser("approve")
    approval.add_argument("goal_id")
    approval.add_argument("--sha256", required=True)
    for action in ("run", "resume"):
        cmd = sub.add_parser(action)
        cmd.add_argument("goal_id")
        cmd.add_argument("--grant", action="append", default=[])
        cmd.add_argument("--confirm-model-call", action="store_true")
        cmd.add_argument("--confirm-browser-run", action="store_true")
        cmd.add_argument("--confirm-external-run", action="store_true")
    sub.add_parser("list")
    demo_cmd = sub.add_parser("demo")
    demo_cmd.add_argument("--confirm-demo", action="store_true")
    recover = sub.add_parser("recover")
    recover.add_argument("--confirm-recover", action="store_true")

    schedule = sub.add_parser("schedule")
    scheduling = schedule.add_subparsers(dest="subcommand", required=True)
    screate = scheduling.add_parser("create")
    screate.add_argument("template", choices=sorted(planner.TEMPLATES))
    screate.add_argument("--title", required=True)
    screate.add_argument("--input-file", required=True)
    screate.add_argument("--next-due", required=True,
                         help="ISO 8601 with timezone, e.g. 2026-11-06T09:00:00+07:00")
    screate.add_argument("--every-minutes", type=int, required=True)
    screate.add_argument("--confirm-schedule", action="store_true")
    scheduling.add_parser("list")
    tick = scheduling.add_parser("tick")
    tick.add_argument("--confirm-tick", action="store_true")
    tick.add_argument("--max-due", type=int, default=3)
    for action in ("pause", "activate"):
        sc = scheduling.add_parser(action)
        sc.add_argument("schedule_id")
        sc.add_argument("--confirm-write", action="store_true")

    memory = sub.add_parser("memory")
    memories = memory.add_subparsers(dest="subcommand", required=True)
    memories.add_parser("list")
    write = memories.add_parser("set")
    write.add_argument("key")
    write.add_argument("--note", required=True)
    write.add_argument("--evidence-ref", required=True)
    write.add_argument("--confirm-write", action="store_true")
    args = cli.parse_args()

    if args.command == "propose":
        result = planner.propose(
            args.title, args.template, _input_file(args.input_file),
            max_model_calls=args.max_model_calls,
            max_external_runs=args.max_external_runs)
    elif args.command == "inspect":
        result = runner.inspect(args.goal_id)
    elif args.command == "approve":
        result = store.approve_goal(args.goal_id, args.sha256)
    elif args.command in {"run", "resume"}:
        current = store.get_goal(args.goal_id)
        required = "APPROVED" if args.command == "run" else "WAITING_APPROVAL"
        if current["status"] != required:
            cli.error(f"{args.command} requires status {required}")
        result = runner.execute(
            args.goal_id, grants=args.grant,
            confirm_model_call=args.confirm_model_call,
            confirm_browser_run=args.confirm_browser_run,
            confirm_external_run=args.confirm_external_run)
    elif args.command == "list":
        result = {"status": "OK", "goals": store.list_goals()}
    elif args.command == "demo":
        result = demo(confirm_demo=args.confirm_demo)
    elif args.command == "recover":
        if not args.confirm_recover:
            cli.error("Explicit --confirm-recover required")
        result = runner.recover()
    elif args.command == "schedule":
        if args.subcommand == "create":
            result = scheduler.create_schedule(
                args.title, args.template, _input_file(args.input_file),
                args.next_due, args.every_minutes,
                confirm_schedule=args.confirm_schedule)
        elif args.subcommand == "list":
            result = {"status": "OK", "schedules": scheduler.list_schedules()}
        elif args.subcommand == "tick":
            result = scheduler.tick(confirm_tick=args.confirm_tick,
                                    max_due=args.max_due)
        else:
            result = scheduler.set_schedule_status(
                args.schedule_id,
                "PAUSED" if args.subcommand == "pause" else "ACTIVE",
                confirm_write=args.confirm_write)
    else:
        if args.subcommand == "list":
            result = {"status": "OK", "owner_memory": store.list_memory()}
        else:
            result = store.set_memory(
                args.key, args.note, args.evidence_ref,
                confirm_write=args.confirm_write)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") in ("FAILED", "INTERRUPTED",
                                "INTERRUPTED_REVIEW_REQUIRED"):
        cli.exit(2)
    if result.get("status") == "WAITING_APPROVAL":
        cli.exit(3)


if __name__ == "__main__":
    main()
