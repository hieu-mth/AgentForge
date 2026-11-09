"""Explicit Owner mutation allowlist: preserve policy and SHA acceptance gates."""
from agentforge import brain_planner, brain_runner, brain_scheduler, brain_store
from agentforge import goal_preflight, growth_store, ops_control, skill_registry
from agentforge.core import artifact_acceptance
from agentforge.api.auth import SENSITIVE_GRANTS


def _owner_action(server, path, request, session=None):
    """Explicit allowlist; no arbitrary skill invocation or Python execution."""
    if path.startswith("/api/artifacts/") and path.endswith("/syntax"):
        parts = path.split("/")
        if (len(parts) != 6 or parts[3] not in {"webapps", "proposals"}
                or set(request) != {"ack", "sha256"} or request["ack"] != "VALIDATE_SYNTAX"):
            raise ValueError("Invalid source validation request")
        namespace, pid = parts[3:5]
        reviewed = "reviewed_webapps" if namespace == "webapps" else "reviewed_proposals"
        if session is None or session.get(reviewed, {}).get(pid) != request["sha256"]:
            raise PermissionError("Inspect exact source before validation")
        from agentforge.ops_control import require_active
        require_active()
        return artifact_acceptance.validate_source(pid, request["sha256"], namespace, db_path=server.task_db_path)
    if path.startswith("/api/artifacts/") and path.endswith("/decision"):
        parts = path.split("/")
        if (len(parts) != 6 or parts[3] not in {"webapps", "proposals"}
                or set(request) != {"ack", "sha256", "expected_revision", "evidence_sha"}):
            raise ValueError("Invalid artifact decision")
        namespace, pid = parts[3:5]
        decision = {"ACCEPT_ARTIFACT": "ACCEPTED", "REJECT_ARTIFACT": "REJECTED"}.get(request["ack"])
        reviewed = "reviewed_webapps" if namespace == "webapps" else "reviewed_proposals"
        if (decision is None or session is None
                or session.get(reviewed, {}).get(pid) != request["sha256"]):
            raise PermissionError("Inspect the exact source before deciding acceptance")
        from agentforge.ops_control import require_active
        require_active()
        return artifact_acceptance.decide(
            pid, request["sha256"], namespace, decision, confirm=True,
            expected_revision=request["expected_revision"], evidence_sha=request["evidence_sha"],
            db_path=server.task_db_path)
    if path == "/api/retention/backup":
        from agentforge.storage import retention
        if (set(request) != {"ack", "kind", "id", "tree_sha"} or
                request.get("ack") != "BACKUP_ARTIFACT"):
            raise PermissionError("Explicit reviewed artifact backup required")
        key = (request["kind"], request["id"])
        if (session is None or session.get("inspected_artifacts", {}).get(key)
                != request["tree_sha"]):
            raise PermissionError("Inspect exact live artifact SHA first")
        return retention.backup(request["kind"], request["id"], request["tree_sha"],
                                confirm=True)
    if path == "/api/retention/quarantine":
        from agentforge.storage import retention
        if (set(request) != {"ack", "backup_id", "tree_sha"} or
                request.get("ack") != "QUARANTINE_ARTIFACT"):
            raise PermissionError("Explicit reversible quarantine required")
        if (session is None or session.get("verified_artifact_backups", {}).get(
                request["backup_id"]) != request["tree_sha"]):
            raise PermissionError("Verify exact backup SHA in this session")
        return retention.quarantine(request["backup_id"], request["tree_sha"],
                                    confirm=True)
    if path == "/api/retention/restore":
        from agentforge.storage import retention
        if (set(request) != {"ack", "backup_id", "tree_sha"} or
                request.get("ack") != "RESTORE_ARTIFACT"):
            raise PermissionError("Explicit owner restore required")
        if (session is None or session.get("verified_artifact_backups", {}).get(
                request["backup_id"]) != request["tree_sha"]):
            raise PermissionError("Verify exact backup SHA in this session")
        return retention.restore(request["backup_id"], request["tree_sha"],
                                 confirm=True)
    if path == "/api/image/submit":
        from agentforge.image_studio_v24 import submit
        if not server.allow_external_actions:
            raise PermissionError("ComfyUI image generation requires external-capable owner mode")
        if set(request) != {"ack", "slug", "prompt", "checkpoint"} or request.get("ack") != "GENERATE_LOCAL_IMAGE":
            raise PermissionError("Explicit owner image generation request required")
        return submit(request["slug"], request["prompt"], request["checkpoint"],
                      confirm_generation=True)
    if path.startswith("/api/image/") and path.endswith("/collect"):
        from agentforge.image_studio_v24 import collect
        if not server.allow_external_actions:
            raise PermissionError("Image import requires external-capable owner mode")
        parts = path.split("/")
        if len(parts) != 5 or set(request) != {"ack"} or request["ack"] != "IMPORT_AI_IMAGE":
            raise PermissionError("Explicit owner image import required")
        return collect(parts[3], confirm_import=True)
    if path.startswith("/api/image/") and path.endswith("/attach"):
        from agentforge.image_studio_v24 import attach
        if set(request) != {"ack", "image_sha", "html_sha"} or request["ack"] != "ATTACH_AI_IMAGE":
            raise PermissionError("Explicit SHA-bound owner image attachment required")
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid image job route")
        return attach(parts[3], request["image_sha"], request["html_sha"],
                      confirm_attach=True)
    if path == "/api/workspace/policy":
        from agentforge import workspace_policy
        if (set(request) != {"ack", "max_estimated_model_calls",
                             "website_enabled", "storyboard_enabled"} or
                request.get("ack") != "UPDATE_WORKSPACE_POLICY"):
            raise PermissionError("Only explicit bounded owner workspace policy is allowed")
        return workspace_policy.configure(
            max_estimated_model_calls=request["max_estimated_model_calls"],
            website_enabled=request["website_enabled"],
            storyboard_enabled=request["storyboard_enabled"], confirm=True)
    if path == "/api/workspace/request":
        if set(request) != {"ack", "prompt", "max_model_calls"} or request.get("ack") != "PLAN_ONLY":
            raise PermissionError("Chỉ được tạo kế hoạch sau xác nhận owner.")
        from agentforge.prompt_intake import plan_request
        return plan_request(
            request["prompt"], max_model_calls=request["max_model_calls"],
            max_external_runs=0, brain_db_path=server.brain_db_path,
            analytics_db_path=server.analytics_db_path,
            growth_db_path=server.growth_db_path)
    if path == "/api/autopilot/configure":
        from agentforge import autopilot_v13
        if request.get("ack") != "SET_DAILY_MODEL_POLICY":
            raise PermissionError("Owner must explicitly approve standing delegation")
        if set(request) != {"ack", "enabled", "daily_cap"}:
            raise ValueError("Only bounded policy fields accepted")
        return autopilot_v13.configure(
            enabled=request["enabled"], daily_cap=request["daily_cap"],
            confirm=True)
    if path.startswith("/api/videos/") and path.endswith("/decide"):
        from agentforge import media_workflow_v15
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid video review route")
        ident = parts[3]
        if set(request) != {"ack", "decision", "video_sha", "watched_local_file"}:
            raise ValueError("Only bounded video approval fields accepted")
        decision = request["decision"]
        if decision not in ("APPROVE", "REJECT") or request["ack"] != "VIDEO_" + decision:
            raise PermissionError("Explicit video decision required")
        if request["watched_local_file"] is not True:
            raise PermissionError("Owner must confirm watching local MP4")
        if (session is None or
                session.get("inspected_video", {}).get(ident) != request["video_sha"]):
            raise PermissionError("Inspect exact MP4 metadata in this session first")
        return media_workflow_v15.decide(
            ident, decision, request["video_sha"], confirm_review=True)
    if path.startswith("/api/drafts/") and path.endswith("/decide"):
        from agentforge import quality_v14
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid content review route")
        job_id = parts[3]
        if set(request) != {"ack", "decision", "output_sha"}:
            raise ValueError("Only bounded content review fields accepted")
        decision = request["decision"]
        if decision not in ("APPROVE", "REJECT") or request["ack"] != "REVIEW_" + decision:
            raise PermissionError("Explicit exact owner decision required")
        if (decision == "APPROVE" and
                (session is None or session.get("reviewed_ai_drafts", {}).get(job_id)
                 != request["output_sha"])):
            raise PermissionError("Inspect the full task in this session before approving")
        return quality_v14.decide(
            job_id, decision, request["output_sha"], confirm=True)
    if path == "/api/media/prepare":
        if request.get("ack") != "PREPARE_EDITED_STORYBOARD":
            raise PermissionError("Explicit owner storyboard edit confirmation required")
        if set(request) - {"ack", "storyboard"}:
            raise ValueError("Only owner storyboard content is accepted in dashboard")
        from agentforge import media_workflow_v15
        return media_workflow_v15.prepare(
            request.get("storyboard"), confirm_edit=True)
    if path == "/api/ops/control":
        mode = request.get("mode")
        expected = "PAUSE_OPERATIONS" if mode == "PAUSED" else (
            "RESUME_OPERATIONS" if mode == "ACTIVE" else None)
        if expected is None or request.get("ack") != expected:
            raise PermissionError("Explicit matching operations control acknowledgment required")
        return ops_control.set_mode(mode, confirm=True)
    if path.startswith("/api/webapps/") and (
            path.endswith("/revision") or path.endswith("/apply")):
        from agentforge import webapp_developer
        parts = path.split("/")
        if len(parts) != 5 or parts[1:3] != ["api", "webapps"]:
            raise ValueError("Invalid application action")
        proposal_id, action = parts[3], parts[4]
        if set(request) != ({"ack", "sha256", "feedback"} if action == "revision"
                              else {"ack", "sha256"}):
            raise ValueError("Invalid application request fields")
        provider = webapp_developer.provider(proposal_id)
        proposal = provider.inspect(proposal_id)
        if request.get("sha256") != proposal["sha256"]:
            raise PermissionError("Application proposal SHA mismatch")
        if (session is None or session.get("reviewed_webapps", {}).get(proposal_id)
                != proposal["sha256"]):
            raise PermissionError("Inspect this exact app proposal before authorizing")
        if action == "revision":
            if provider is not webapp_developer.base:
                raise PermissionError("AI Developer source revision is not supported yet")
            if request["ack"] != "REQUEST_REVISION":
                raise PermissionError("Explicit app revision acknowledgment required")
            from agentforge.webapp_feedback import request_revision
            return request_revision(
                proposal_id, proposal["sha256"], request["feedback"],
                brain_db_path=server.brain_db_path,
                analytics_db_path=server.analytics_db_path,
                growth_db_path=server.growth_db_path)
        if request["ack"] != "APPLY_WEBAPP":
            raise PermissionError("Explicit app source approval required")
        return provider.apply(
            proposal_id, sha256=proposal["sha256"], confirm_write=True)
    if path.startswith("/api/proposals/") and path.endswith("/revision"):
        from agentforge.website_feedback import request_revision
        parts = path.split("/")
        if len(parts) != 5 or set(request) != {"ack", "sha256", "feedback"}:
            raise ValueError("Invalid revision request")
        if request["ack"] != "REQUEST_REVISION":
            raise PermissionError("Owner must explicitly request a revision")
        ident = parts[3]
        if (session is None or session.get("reviewed_proposals", {}).get(ident)
                != request["sha256"]):
            raise PermissionError("Review this exact proposal SHA before requesting changes")
        return request_revision(
            ident, request["sha256"], request["feedback"],
            brain_db_path=server.brain_db_path,
            analytics_db_path=server.analytics_db_path,
            growth_db_path=server.growth_db_path)
    if path.startswith("/api/proposals/") and path.endswith("/apply"):
        from agentforge import product_builder
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid proposal action")
        proposal_id = parts[3]
        metadata = product_builder.inspect(proposal_id)
        if (request.get("ack") != "APPLY_PROPOSAL"
                or request.get("sha256") != metadata["sha256"]):
            raise PermissionError("Explicit matching proposal SHA required")
        if (session is None or session.get("reviewed_proposals", {}).get(
                proposal_id) != metadata["sha256"]):
            raise PermissionError("Inspect original proposal in this session before applying")
        return product_builder.apply(
            proposal_id, confirm_write=True, sha256=metadata["sha256"])
    if path == "/api/goals/preflight":
        if request.get("ack") != "PREFLIGHT":
            raise PermissionError("Confirm PREFLIGHT before reading references")
        return goal_preflight.inspect(
            request.get("template"), request.get("inputs"),
            analytics_db_path=server.analytics_db_path,
            growth_db_path=server.growth_db_path)
    if path == "/api/goals/propose":
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
            external = set(grants) & SENSITIVE_GRANTS
            uses_external = any(
                set(step["required_permissions"]) & SENSITIVE_GRANTS
                for step in goal["plan"])
            if (external or uses_external) and not server.allow_external_actions:
                raise PermissionError("External tools are disabled in this Control Center")
            if (external or uses_external) and request.get(
                    "ack_external") != "AUTHORIZE_EXTERNAL_TOOLS":
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
                task_db_path=server.task_db_path, **flags)
        raise ValueError("Unknown goal operation")
    if path == "/api/schedules/create":
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
    if path == "/api/campaigns/create":
        if request.get("ack") != "CREATE_CAMPAIGN":
            raise PermissionError("Explicit CREATE_CAMPAIGN required")
        return growth_store.create_campaign(
            request.get("data"), confirm_write=True,
            db_path=server.growth_db_path, analytics_db_path=server.analytics_db_path)
    if path == "/api/campaigns/event":
        if request.get("ack") != "RECORD_EVENT":
            raise PermissionError("Explicit RECORD_EVENT required")
        # Strict nested validation occurs before any storage; does not log PII.
        growth_store.validate_event_payload(request.get("kind"),
                                            request.get("data"))
        return growth_store.record_event(
            request["kind"], request["data"], confirm_write=True,
            db_path=server.growth_db_path)
    if path == "/api/memory/set":
        if request.get("ack") != "SAVE_NOTE":
            raise PermissionError("Explicit SAVE_NOTE required")
        return brain_store.set_memory(
            request.get("key"), request.get("note"),
            request.get("evidence_ref"), confirm_write=True,
            db_path=server.brain_db_path)
    raise ValueError("Unknown mutation route")
