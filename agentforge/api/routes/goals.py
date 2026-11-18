"""Owner-gated goals, schedules and explicit memory actions."""
from agentforge import brain_planner, brain_runner, brain_scheduler, brain_store
from agentforge import goal_preflight, skill_registry
from agentforge.api.auth import SENSITIVE_GRANTS
from agentforge.api.routes._shared import UNHANDLED


# Only current Film Studio and generic Owner workflows may be newly submitted.
# Historical goals remain inspectable and may finish with their original gates.
RETIRED_TEMPLATES = frozenset({
    "campaign.review", "website.campaign", "website.draft", "website.browser",
    "webapp.draft", "webapp.develop", "webapp.company", "webapp.revision",
    "webapp.source_revision", "webapp.qa", "webapp.browser_qa",
    "media.produce", "media.review", "growth.review", "growth.launch_local",
})


def _require_current_template(template):
    canonical = brain_planner.ALIASES.get(template, template) if isinstance(template, str) else ""
    if canonical in RETIRED_TEMPLATES:
        raise ValueError("RETIRED_GOAL_TEMPLATE: legacy business/media workflow is unavailable")


def handle(server, path, request, session=None):
    if path == "/api/goals/preflight":
        _require_current_template(request.get("template"))
        if request.get("ack") != "PREFLIGHT":
            raise PermissionError("Confirm PREFLIGHT before reading references")
        return goal_preflight.inspect(
            request.get("template"), request.get("inputs"),
            analytics_db_path=server.analytics_db_path,
            growth_db_path=server.growth_db_path)
    if path == "/api/goals/propose":
        _require_current_template(request.get("template"))
        if request.get("ack") != "PROPOSE":
            raise PermissionError("Confirm PROPOSE before making a goal")
        goal_preflight.require_ready(
            request.get("template"), request.get("inputs"),
            analytics_db_path=server.analytics_db_path,
            growth_db_path=server.growth_db_path)
        return brain_planner.propose(
            request.get("title"), request.get("template"), request.get("inputs"),
            max_model_calls=request.get("max_model_calls", 0),
            max_external_runs=request.get("max_external_runs", 0),
            db_path=server.brain_db_path)
    if path.startswith("/api/goals/"):
        parts = path.split("/")
        if len(parts) != 5 or parts[1:3] != ["api", "goals"]:
            raise ValueError("Unknown goal operation")
        ident, action = parts[3], parts[4]
        goal = brain_store.get_goal(ident, db_path=server.brain_db_path)
        if request.get("plan_sha256") != goal["plan_sha256"]:
            raise PermissionError("Goal plan SHA changed; inspect before authorizing")
        if action == "approve":
            if request.get("ack") != "APPROVE":
                raise PermissionError("Explicit APPROVE required")
            goal_preflight.require_ready(
                goal["template"], goal["inputs"],
                analytics_db_path=server.analytics_db_path,
                growth_db_path=server.growth_db_path)
            return brain_store.approve_goal(
                ident, request["plan_sha256"], db_path=server.brain_db_path)
        if action == "cancel":
            if (set(request) != {"ack", "plan_sha256", "goal_updated_at"}
                    or request["ack"] != "CANCEL_PENDING_GOAL"):
                raise PermissionError("Explicit cancellation of the reviewed goal required")
            return brain_runner.cancel_waiting(
                ident, request["goal_updated_at"],
                brain_db_path=server.brain_db_path, task_db_path=server.task_db_path)
        if action == "retry":
            if request.get("ack") != "RETRY_FAILED_STEP":
                raise PermissionError("Explicit failed-step retry approval required")
            # This call only rearms the exact failed step. It never invokes a
            # model; the following RUN needs separate grants and confirmations.
            return brain_runner.retry_failed_step(
                ident, request["plan_sha256"], request.get("child_task_id"),
                brain_db_path=server.brain_db_path,
                task_db_path=server.task_db_path)
        if action in {"run", "resume"}:
            required_status = "APPROVED" if action == "run" else "WAITING_APPROVAL"
            if goal["status"] != required_status or request.get("ack") != action.upper():
                raise PermissionError(f"Explicit {action.upper()} on {required_status} goal required")
            goal_preflight.require_ready(
                goal["template"], goal["inputs"],
                analytics_db_path=server.analytics_db_path,
                growth_db_path=server.growth_db_path)
            grants = request.get("grants", [])
            if (not isinstance(grants, list) or len(grants) > 8 or
                    any(not isinstance(g, str) for g in grants) or
                    len(set(grants)) != len(grants) or
                    not set(grants).issubset(skill_registry.PERMISSIONS)):
                raise ValueError("Invalid tool grants")
            revision = request.get("goal_updated_at")
            # Legacy initial RUN remains supported only before any dispatch or retry.
            fresh_start = (action == "run" and goal["current_step"] == 0
                           and all(event["name"] in {"PLANNED", "APPROVED"}
                                   for event in goal["events"]))
            if revision != goal["updated_at"] and not (revision is None and fresh_start):
                raise PermissionError("Goal changed; reload the current step before authorizing")
            current = goal["current_step"]
            if not 0 <= current < len(goal["plan"]):
                raise PermissionError("No executable step in the reviewed goal")
            needed = set(goal["plan"][current]["required_permissions"])
            if set(grants) - (needed | {"workspace.read"}):
                raise PermissionError("Only grants for the current step are allowed")
            if needed & SENSITIVE_GRANTS:
                if not server.allow_external_actions:
                    raise PermissionError("External tools are disabled in this Control Center")
                if request.get("ack_external") != "AUTHORIZE_EXTERNAL_TOOLS":
                    raise PermissionError("Separate external tool approval required")
            flags = {}
            for key in ("confirm_model_call", "confirm_browser_run",
                        "confirm_external_run"):
                value = request.get(key, False)
                if type(value) is not bool:
                    raise ValueError("Confirmation flags must be boolean")
                flags[key] = value
            # No implicit or persistent grants. The S1 runner enforces each step.
            return brain_runner.execute(
                ident, grants=grants, brain_db_path=server.brain_db_path,
                task_db_path=server.task_db_path, expected_updated_at=goal["updated_at"],
                scope_to_current_step=True, **flags)
        raise ValueError("Unknown goal operation")
    if path == "/api/schedules/create":
        _require_current_template(request.get("template"))
        if request.get("ack") != "SCHEDULE":
            raise PermissionError("Explicit SCHEDULE required")
        return brain_scheduler.create_schedule(
            request.get("title"), request.get("template"), request.get("inputs"),
            request.get("next_due"), request.get("frequency_minutes"),
            confirm_schedule=True, db_path=server.brain_db_path)
    if path == "/api/schedules/tick":
        if request.get("ack") != "TICK":
            raise PermissionError("Explicit TICK required")
        return brain_scheduler.tick(
            confirm_tick=True, db_path=server.brain_db_path,
            task_db_path=server.task_db_path, max_due=3)
    if path.startswith("/api/schedules/") and path.endswith("/status"):
        pieces = path.split("/")
        if len(pieces) != 5 or pieces[1:3] != ["api", "schedules"]:
            raise ValueError("Unknown schedule operation")
        target = request.get("status")
        if target not in ("ACTIVE", "PAUSED") or request.get("ack") != target:
            raise PermissionError("Explicit schedule status confirmation required")
        return brain_scheduler.set_schedule_status(
            pieces[3], target, confirm_write=True, db_path=server.brain_db_path)
    if path == "/api/memory/set":
        if request.get("ack") != "SAVE_NOTE":
            raise PermissionError("Explicit SAVE_NOTE required")
        return brain_store.set_memory(
            request.get("key"), request.get("note"),
            request.get("evidence_ref"), confirm_write=True,
            db_path=server.brain_db_path)
    return UNHANDLED
