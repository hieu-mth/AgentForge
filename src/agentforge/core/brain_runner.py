"""S4 bounded, owner-governed Company Brain execution over S1 Skill Runner.

Persistent dispatch markers are written BEFORE each skill call. An ambiguous
crash is INTERRUPTED, not retried. Permissions/confirmations are ephemeral
per invocation; approval of a plan is NOT blanket tool authorization.
"""
import hashlib
import json
from agentforge import brain_planner as planner
from agentforge import brain_store as store
from agentforge import skill_runner, task_history


def _verify(goal):
    raw = json.dumps(goal["plan"], ensure_ascii=False, separators=(",", ":"),
                     sort_keys=True, allow_nan=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if digest != goal["plan_sha256"]:
        raise store.BrainError("Immutable plan SHA changed: stop execution")
    if len(goal["plan"]) > 6:
        raise store.BrainError("Unbounded goal plan refused")
    limits = goal["inputs"].get("_limits")
    if (not isinstance(limits, dict)
            or type(limits.get("max_model_calls")) is not int
            or type(limits.get("max_external_runs")) is not int):
        raise store.BrainError("Missing owner-reviewed resource caps")
    if sum(x["estimated_model_calls"] for x in goal["plan"]) > limits["max_model_calls"]:
        raise store.BrainError("Planned model calls exceed owner-reviewed cap")
    if sum(x["external_process"] for x in goal["plan"]) > limits["max_external_runs"]:
        raise store.BrainError("Planned subprocess calls exceed owner-reviewed cap")
    for x in goal["plan"]:
        contract, required = skill_runner._contract(x["skill_id"])
        if (x["worker_id"] != contract["worker_id"]
                or x["required_permissions"] != sorted(required)
                or x["estimated_model_calls"] != contract["limits"]["estimated_model_calls"]
                or x["external_process"] != ("process.run" in required)):
            raise store.BrainError("Plan and current trusted skill policy diverged")


def _safe_error(exc):
    return f"{type(exc).__name__}: inspect recorded child task and source logs"


def _finish(goal_id, parent_id, status, *, brain_db_path, task_db_path, error=None):
    if status not in {"SUCCEEDED", "FAILED", "INTERRUPTED"}:
        raise store.BrainError("Invalid terminal goal state")
    task_history.transition(parent_id, status, error=error, db_path=task_db_path)
    store.change_state(goal_id, status, expected="RUNNING", error=error,
                       db_path=brain_db_path)
    goal = store.get_goal(goal_id, db_path=brain_db_path)
    from agentforge.core import artifact_acceptance
    return {"goal_id": goal_id, "task_id": parent_id, "status": status,
            "artifact_acceptance": artifact_acceptance.for_goal(goal, task_db_path=task_db_path),
            "executed_steps": len(goal["steps"]), "step_count": len(goal["plan"]),
            "error": error, "spending_authorized": False,
            "published": False}


def _pause(goal_id, parent_id, step_index, response, *, brain_db_path, task_db_path):
    task_history.transition(parent_id, "WAITING_APPROVAL", db_path=task_db_path)
    store.change_state(goal_id, "WAITING_APPROVAL", expected="RUNNING",
                       db_path=brain_db_path)
    return {"goal_id": goal_id, "task_id": parent_id,
            "status": "WAITING_APPROVAL", "waiting_step": step_index,
            "missing": response.get("missing", []),
            "executed": False,
            "automatic_resume": False,
            "spending_authorized": False}


def _run_steps(goal_id, *, grants, confirm_model_call,
               confirm_browser_run, confirm_external_run,
               brain_db_path, task_db_path):
    goal = store.get_goal(goal_id, db_path=brain_db_path)
    parent = goal["parent_task_id"]
    # Each execute()/resume call can authorize AT MOST ONE model invocation
    # and one external process. A single click must never spend 3 V5 calls.
    model_used = False
    process_used = False
    try:
        _verify(goal)
        while True:
            goal = store.get_goal(goal_id, db_path=brain_db_path)
            index = goal["current_step"]
            if index >= len(goal["plan"]):
                return _finish(goal_id, parent, "SUCCEEDED",
                               brain_db_path=brain_db_path, task_db_path=task_db_path)
            # A pause requested during this Goal blocks subsequent skill
            # dispatch. Already-running external tools are not forcibly killed.
            from agentforge.ops_control import require_active
            require_active()
            step = goal["plan"][index]
            previous = next((x for x in goal["steps"]
                             if x["step_index"] == index), None)
            if previous is None:
                # Validate derived inputs BEFORE durable no-retry marker.
                payload = planner.resolve_payload(goal, index, task_db_path=task_db_path)
                store.claim_step(goal_id, index, step["skill_id"],
                                 db_path=brain_db_path)
                receipt = skill_runner.invoke(
                    step["skill_id"], payload, parent_id=parent,
                    grants=grants,
                    confirm_model_call=confirm_model_call and not model_used,
                    confirm_browser_run=confirm_browser_run,
                    confirm_external_run=confirm_external_run and not process_used,
                    db_path=task_db_path)
                store.finish_step(goal_id, index, receipt["task_id"], receipt["status"],
                                  db_path=brain_db_path)
            elif previous["status"] == "WAITING_APPROVAL":
                receipt = skill_runner.resume_waiting(
                    previous["child_task_id"], grants=grants,
                    confirm_model_call=confirm_model_call and not model_used,
                    confirm_browser_run=confirm_browser_run,
                    confirm_external_run=confirm_external_run and not process_used,
                    db_path=task_db_path)
                if receipt["status"] != "WAITING_APPROVAL":
                    store.resume_step(goal_id, index, receipt["status"],
                                      db_path=brain_db_path)
            else:
                # DISPATCHING / terminal markers must NEVER cause a second invoke.
                raise store.BrainError("Previously dispatched step cannot be replayed")
            if receipt["status"] == "SUCCEEDED":
                if "model.invoke" in step["required_permissions"]:
                    model_used = True
                if "process.run" in step["required_permissions"]:
                    process_used = True
            if receipt["status"] == "WAITING_APPROVAL":
                return _pause(goal_id, parent, index, receipt,
                              brain_db_path=brain_db_path, task_db_path=task_db_path)
            if receipt["status"] == "FAILED":
                return _finish(goal_id, parent, "FAILED",
                               error="Trusted S1 skill execution failed",
                               brain_db_path=brain_db_path, task_db_path=task_db_path)
            # Distinguish skill execution success from a failed quality report.
            inner = receipt.get("result")
            if (isinstance(inner, dict) and
                    (inner.get("status") == "FAIL" or inner.get("failures", 0) > 0)):
                return _finish(goal_id, parent, "FAILED",
                               error="Quality gate returned FAIL",
                               brain_db_path=brain_db_path, task_db_path=task_db_path)
    except Exception as exc:
        # A child may have side effects and no stored receipt after power loss.
        # Always interrupt the parent instead of replaying an uncertain step.
        error = _safe_error(exc)
        goal = store.get_goal(goal_id, db_path=brain_db_path)
        if goal["status"] == "RUNNING":
            try:
                return _finish(goal_id, parent, "INTERRUPTED", error=error,
                               brain_db_path=brain_db_path, task_db_path=task_db_path)
            except Exception:
                # A manual 'recover' can mark abandoned RUNNING tasks safely.
                return {"goal_id": goal_id, "task_id": parent,
                        "status": "INTERRUPTED_REVIEW_REQUIRED",
                        "error": error, "automatic_resume": False}
        raise


def execute(goal_id, *, grants=(), confirm_model_call=False,
            confirm_browser_run=False, confirm_external_run=False,
            brain_db_path=None, task_db_path=None):
    """Start or resume approved goal; only new explicit ephemeral tool grants."""
    from agentforge.ops_control import require_active
    require_active()
    goal = store.get_goal(goal_id, db_path=brain_db_path)
    if goal["status"] not in {"APPROVED", "WAITING_APPROVAL"}:
        raise store.BrainError("Goal must be approved or waiting for owner")
    _verify(goal)
    if goal["status"] == "APPROVED":
        parent = task_history.create_task(
            "workflow", "brain.goal",
            {"goal_id": goal_id, "plan_sha256": goal["plan_sha256"],
             "template": goal["template"]},
            db_path=task_db_path)
        store.change_state(goal_id, "RUNNING", expected="APPROVED",
                           parent_task_id=parent, db_path=brain_db_path)
        task_history.transition(parent, "RUNNING", db_path=task_db_path)
    else:
        parent = goal["parent_task_id"]
        if not isinstance(parent, str):
            raise store.BrainError("Awaiting goal has no parent task")
        store.change_state(goal_id, "RUNNING", expected="WAITING_APPROVAL",
                           db_path=brain_db_path)
        task_history.transition(parent, "RUNNING", db_path=task_db_path)
    return _run_steps(
        goal_id, grants=grants, confirm_model_call=confirm_model_call,
        confirm_browser_run=confirm_browser_run,
        confirm_external_run=confirm_external_run,
        brain_db_path=brain_db_path, task_db_path=task_db_path)


def recover(*, brain_db_path=None, task_db_path=None):
    """Manual recovery of ambiguous in-flight work. No retries ever."""
    running = [x for x in store.list_goals(db_path=brain_db_path, limit=100)
               if x["status"] == "RUNNING"]
    count = store.recover(db_path=brain_db_path)
    for item in running:
        goal = store.get_goal(item["goal_id"], db_path=brain_db_path)
        ids = [goal["parent_task_id"]] + [
            x["child_task_id"] for x in goal["steps"]]
        for task_id in ids:
            if not task_id:
                continue
            try:
                child = task_history.get_task(task_id, db_path=task_db_path)
                if child["status"] == "RUNNING":
                    task_history.transition(task_id, "INTERRUPTED",
                                            db_path=task_db_path)
            except (KeyError, ValueError, RuntimeError):
                pass
    return {"interrupted_goals": count, "automatic_replay": False}


def inspect(goal_id, *, brain_db_path=None, task_db_path=None):
    goal = store.get_goal(goal_id, db_path=brain_db_path)
    from agentforge.core import artifact_acceptance
    return {
        "goal_id": goal_id, "status": goal["status"],
        "artifact_acceptance": artifact_acceptance.for_goal(goal, task_db_path=task_db_path),
        "title": goal["title"], "template": goal["template"],
        "plan_sha256": goal["plan_sha256"],
        "error": goal.get("error"),
        "inputs": goal["inputs"],
        "plan": goal["plan"], "step_runs": goal["steps"],
        "parent_task_id": goal["parent_task_id"],
        "events": goal["events"],
        "spending_authorized": False,
        "execution_authorized": goal["status"] != "PLANNED",
    }
