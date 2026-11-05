"""AgentForge Control Center V1 — authenticated, localhost-only owner console.

This is NOT internet-facing multi-user authentication. A fresh console-printed
owner code logs in to an in-memory HttpOnly session. Every mutation requires
same-origin JSON, an authenticated session, a per-session CSRF token, an
explicit owner action phrase and the underlying S1/S4 permission gates.

All existing V0 read-only endpoints and CLIs remain intact.
"""
import argparse
import hmac
import json
import re
import secrets
import threading
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from agentforge import analytics_insights, analytics_store, brain_planner
from agentforge import brain_runner, brain_scheduler, brain_store, growth_reports
from agentforge import growth_store, skill_registry, task_history, goal_preflight, result_view
from agentforge import ops_control
from agentforge.dashboard_v0 import _artifact_names, _task_public

STATIC = Path(__file__).with_name("control_center_static")
COOKIE = "af_owner_session"
SESSION_SECONDS = 8 * 60 * 60
MAX_BODY = 8192
SENSITIVE_GRANTS = {"model.invoke", "network.read", "network.search",
                    "browser.run", "process.run"}
LOCAL_GRANTS = {"workspace.write", "workspace.propose", "workspace.read"}


def _read_static(name):
    path = STATIC / name
    return path.read_bytes()

# React build output is a separate artifact, never a writable workspace file.
REACT_DIST = Path(__file__).resolve().parents[2] / "ui" / "dashboard" / "dist"
REACT_ASSET_RE = re.compile(r"[A-Za-z0-9_.-]{1,120}\.(?:js|css|svg|png|webp|ico)\Z")


def _react_asset(route):
    """Serve only allowlisted built files, no source files or path traversal."""
    if route in ("/dashboard", "/dashboard/"):
        file = REACT_DIST / "index.html"
        mime = "text/html; charset=utf-8"
    elif route.startswith("/dashboard/assets/"):
        name = route.removeprefix("/dashboard/assets/")
        if not REACT_ASSET_RE.fullmatch(name):
            raise ValueError("Invalid dashboard build asset")
        file = REACT_DIST / "assets" / name
        mime = {
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".webp": "image/webp",
            ".ico": "image/x-icon",
        }[file.suffix]
    else:
        raise ValueError("Not a React dashboard asset")
    if (not file.is_file() or file.is_symlink() or
            REACT_DIST.is_symlink() or file.parent.is_symlink()):
        raise FileNotFoundError("React build not installed; run npm run build")
    if file.stat().st_size > 7 * 1024 * 1024:
        raise ValueError("Dashboard build asset exceeds limit")
    return file.read_bytes(), mime



def _public_task(task):
    output = _task_public(task)
    output["artifacts"] = _artifact_names(task.get("result"))
    output["report"] = result_view.present(task.get("skill_id"), task.get("result")) if (
        task.get("status") == "SUCCEEDED") else None
    if (task.get("skill_id") == "web.create" and task.get("status") == "SUCCEEDED"
            and isinstance(task.get("result"), dict)):
        result = task["result"]
        if (isinstance(result.get("proposal_id"), str)
                and isinstance(result.get("sha256"), str)):
            output["web_proposal"] = {
                "proposal_id": result["proposal_id"],
                "sha256": result["sha256"],
                "slug": result.get("project_slug", ""),
            }
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
    schedules = brain_scheduler.list_schedules(db_path=server.brain_db_path)
    datasets = analytics_store.list_datasets(db_path=server.analytics_db_path)
    campaigns = growth_store.list_campaigns(db_path=server.growth_db_path, limit=30)
    growth = []
    for item in campaigns:
        report = growth_reports.report(item["campaign"], db_path=server.growth_db_path)
        growth.append({
            "campaign": item["campaign"], "title": item["title"],
            "synthetic": bool(item["synthetic"]),
            "lead_total": report["lead_total"],
            "package_count": report["package_count"],
            "owner_reported_posts": report["owner_reported_posts"],
            "owner_recorded_net_cash_vnd": report["owner_recorded_net_cash_vnd"],
            "verified_net_profit_vnd": None,
        })
    health = {"status": "NOT_RUNNING", "fresh": False}
    try:
        from agentforge.ops_daemon import read_heartbeat
        health = read_heartbeat()
    except (OSError, ValueError):
        health = {"status": "UNKNOWN", "fresh": False}
    states = ("SUCCEEDED", "RUNNING", "WAITING_APPROVAL", "FAILED", "INTERRUPTED")
    from agentforge.quality_v14 import inbox as quality_inbox
    quality = quality_inbox()
    review_items = quality["reviews"][:15]
    from agentforge import autopilot_v13, company_v2
    delegated = autopilot_v13.policy()
    owner_company = company_v2.report()
    from agentforge.media_workflow_v15 import report as production_report
    productions = production_report()["productions"][:15]
    from agentforge.workspace_policy import read as read_workspace_policy
    return {
        "workspace_policy": read_workspace_policy(),
        "autopilot_policy": delegated,
        "company_v2": owner_company,
        "local_video": {
            "items": [{
                "production_id": x["production_id"], "run_id": x["run_id"],
                "status": x["status"], "quality": x["quality"],
                "storyboard_sha": x["storyboard_sha"],
                "video_sha": x["video_sha"],
            } for x in productions],
            "pending_count": sum(x["status"] == "VIDEO_READY" for x in productions),
        },
        "autopilot_reviews": {
            "business_context": quality["business_context"],
            "pending_count": sum(x["decision"] == "PENDING" for x in quality["reviews"]),
            "items": [{
                "job_id": x["job_id"], "task_id": x["task_id"],
                "skill_id": x["skill_id"], "quality": x["quality"],
                "decision": x["decision"], "reasons": x["reasons"],
                "output_sha": x["output_sha"],
            } for x in review_items],
        },
        "version": "v1", "local_only": True, "authenticated": True,
        "external_actions_enabled": server.allow_external_actions,
        "stats": {"tasks": len(tasks), "skills": len(skill_registry.load_registry()),
                  "goals": len(goals),
                  **{x.lower(): sum(t["status"] == x for t in tasks) for x in states}},
        "tasks": [
            _public_task(
                task_history.get_task(t["task_id"], db_path=server.task_db_path)
                if t["skill_id"] == "web.create" and t["status"] == "SUCCEEDED"
                else t
            ) for t in tasks[:40]
        ],
        "goals": goals, "schedules": schedules,
        "skills": [{"id": k, "worker": v["worker_id"],
                    "mode": v["execution_mode"]}
                   for k, v in skill_registry.load_registry().items()],
        "datasets": [{"dataset": x["dataset"], "synthetic": bool(x["synthetic"]),
                      "performance_rows": x["performance_rows"],
                      "ledger_rows": x["ledger_rows"]} for x in datasets[:30]],
        "growth": growth, "daemon": health,
        "operations": ops_control.read(),
        "attention": _owner_attention(goals, tasks, schedules, health),
        "templates": {k: list(v) for k, v in brain_planner.TEMPLATES.items()},
        "connectors": [
            {"name": "YouTube", "status": "MANUAL_HANDOFF_ONLY",
             "authenticated": False, "automated_upload": False},
            {"name": "TikTok", "status": "MANUAL_HANDOFF_ONLY",
             "authenticated": False, "automated_upload": False},
            {"name": "Bank / affiliate", "status": "OWNER_RECORDED_ONLY",
             "authenticated": False, "verified_profit": False},
        ],
    }


def _owner_action(server, path, request, session=None):
    """Explicit allowlist; no arbitrary skill invocation or Python execution."""
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


class _Handler(BaseHTTPRequestHandler):
    # No persistent request bodies: malformed Content-Length cannot desync keep-alive.
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        return  # Do not log authentication credentials, URLs or customer data.

    def _origin(self):
        return f"http://{self.headers.get('Host', '')}"

    def _host_ok(self):
        host = self.headers.get("Host", "")
        port = self.server.server_port
        return (host in (f"127.0.0.1:{port}", f"localhost:{port}") and
                self.client_address[0] in {"127.0.0.1", "::1"})

    def _reply(self, code, data, *, mime="application/json", headers=(),
               isolated_preview=False):
        if isinstance(data, (dict, list)):
            raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        elif isinstance(data, bytes):
            raw = data
        else:
            raw = str(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if not isolated_preview:
            self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if isolated_preview:
            # Opaque-origin sandbox: NO JS, forms, network, navigation or top access.
            # Only inline CSS and bounded local document rendering are allowed.
            self.send_header("Content-Security-Policy",
                "sandbox; default-src 'none'; script-src 'none'; "
                "style-src 'unsafe-inline'; img-src data:; font-src data:; "
                "connect-src 'none'; form-action 'none'; base-uri 'none'; "
                "frame-ancestors 'self'")
        else:
            self.send_header("Content-Security-Policy",
                ("default-src 'none'; script-src 'self'; style-src 'self'"+
                 (" 'unsafe-inline'" if self.path.startswith("/dashboard") else "")+
                 "; connect-src 'self'; img-src 'self' data:; font-src 'self' data:; "+
                 "frame-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _session(self):
        raw = self.headers.get("Cookie", "")
        if len(raw) > 2048:
            return None
        try:
            jar = cookies.SimpleCookie()
            jar.load(raw)
            item = jar.get(COOKIE)
        except cookies.CookieError:
            return None
        if item is None:
            return None
        with self.server.auth_lock:
            session = self.server.sessions.get(item.value)
            if session and session["expires"] > time.monotonic():
                return session
        return None

    def _blocked(self, code=403, error="forbidden"):
        self._reply(code, {"error": error})

    def do_GET(self):
        if not self._host_ok():
            return self._blocked(error="invalid_host")
        route = urlsplit(self.path).path
        if route in ("/dashboard", "/dashboard/") or route.startswith("/dashboard/assets/"):
            try:
                body, mime = _react_asset(route)
                return self._reply(200, body, mime=mime)
            except (ValueError, FileNotFoundError, OSError):
                return self._blocked(404, "react_dashboard_not_built_or_invalid_asset")
        if route in ("/", "/app.css", "/app.js"):
            filename, mime = {
                "/": ("app.html", "text/html; charset=utf-8"),
                "/app.css": ("app.css", "text/css; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            }[route]
            return self._reply(200, _read_static(filename), mime=mime)
        if self._session() is None:
            return self._blocked(401, "authentication_required")
        try:
            if route == "/api/session":
                session = self._session()
                return self._reply(200, {
                    "status": "AUTHENTICATED", "csrf": session["csrf"]})
            if route == "/api/bootstrap":
                return self._reply(200, _summary(self.server))
            if route == "/api/image/health":
                from agentforge.image_studio_v24 import health
                return self._reply(200, health())
            if route == "/api/image/jobs":
                from agentforge.image_studio_v24 import report
                return self._reply(200, report())
            if route == "/api/model/health":
                from agentforge.model_health import check
                return self._reply(200, check())
            if route == "/api/retention/inventory":
                from agentforge.storage import retention
                return self._reply(200, retention.inventory())
            if route == "/api/retention/backups":
                from agentforge.storage import retention
                return self._reply(200, retention.list_backups())
            if route.startswith("/api/retention/inspect/"):
                from agentforge.storage import retention
                pieces = route.split("/")
                if len(pieces) != 6 or pieces[1:4] != ["api", "retention", "inspect"]:
                    raise ValueError("Invalid artifact inspection route")
                inspected = retention.inspect(pieces[4], pieces[5])
                session = self._session()
                session.setdefault("inspected_artifacts", {})[(pieces[4], pieces[5])] = inspected["tree_sha256"]
                return self._reply(200, inspected)
            if route.startswith("/api/retention/verify/"):
                from agentforge.storage import retention
                pieces = route.split("/")
                if len(pieces) != 5 or pieces[1:4] != ["api", "retention", "verify"]:
                    raise ValueError("Invalid backup verification route")
                verified = retention.verify(pieces[4])
                session = self._session()
                session.setdefault("verified_artifact_backups", {})[pieces[4]] = verified["tree_sha256"]
                return self._reply(200, verified)
            if route == "/api/artifacts":
                from agentforge.artifact_catalog import report
                return self._reply(200, report())
            if route == "/api/ops/health":
                from agentforge import ops_doctor
                source_paths = {
                    "S1 tasks": self.server.task_db_path or task_history.DEFAULT_DB,
                    "S3 analytics": self.server.analytics_db_path or analytics_store.DB,
                    "S4 goals": self.server.brain_db_path or brain_store.DB,
                    "S5 growth": self.server.growth_db_path or growth_store.DB,
                }
                return self._reply(200, ops_doctor.inspect(
                    paths=source_paths, task_db=self.server.task_db_path,
                    brain_db=self.server.brain_db_path))
            if route == "/api/memory":
                return self._reply(200, brain_store.list_memory(
                    db_path=self.server.brain_db_path))
            if route.startswith("/api/proposals/") and route.endswith("/preview"):
                from agentforge.website_preview import from_proposal
                ident = route[len("/api/proposals/"):-len("/preview")]
                page = from_proposal(ident)
                return self._reply(200, page, mime="text/html; charset=utf-8",
                                   isolated_preview=True)
            if route.startswith("/api/proposals/"):
                from agentforge import product_builder
                ident = route.removeprefix("/api/proposals/")
                document, _ = product_builder._read_proposal(ident)
                if document["status"] != "PROPOSED_NOT_APPLIED":
                    raise ValueError("Proposal cannot be reviewed")
                session = self._session()
                session.setdefault("reviewed_proposals", {})[ident] = document["sha256"]
                return self._reply(200, {
                    "proposal_id": ident, "project_slug": document["project_slug"],
                    "sha256": document["sha256"],
                    "status": document["status"],
                    "summary": document["summary"],
                    "files": [{"path": f["path"], "content": f["content"]}
                              for f in document["files"]],
                    "execution_authorized": False,
                })
            if route.startswith("/api/videos/"):
                from agentforge import media_workflow_v15, media_quality
                ident = route.removeprefix("/api/videos/")
                record = media_workflow_v15._row(ident)
                if record["status"] != "VIDEO_READY":
                    raise PermissionError("Only completed MP4 can be reviewed")
                _, manifest = media_workflow_v15._verify_storyboard_manifest(record)
                qa = media_quality.check(record["run_id"])
                if (qa["status"] != "VIDEO_PASS" or qa["failures"] or
                        not qa["video_verified"] or
                        manifest["artifacts"].get("video.mp4") != record["video_sha"]):
                    raise PermissionError("MP4 integrity/quality is not verified")
                self._session().setdefault("inspected_video", {})[ident] = record["video_sha"]
                return self._reply(200, {
                    "production_id": ident, "run_id": record["run_id"],
                    "video_sha": record["video_sha"], "quality": qa["status"],
                    "relative_path": "workspace/media/" + record["run_id"] + "/video.mp4",
                    "published": False, "review_requires_playback": True})
            if route.startswith("/api/drafts/"):
                from agentforge import quality_v14
                ident = route.removeprefix("/api/drafts/")
                from agentforge import brain_store
                brain_store._id(ident)
                found = next((item for item in quality_v14.inbox()["reviews"]
                              if item["job_id"] == ident), None)
                if found is None:
                    raise KeyError("Draft not found")
                task = task_history.get_task(found["task_id"], db_path=self.server.task_db_path)
                if (task.get("status") != "SUCCEEDED" or
                        task.get("skill_id") != "media.copy_draft" or
                        found["skill_id"] != "media.copy_draft"):
                    raise PermissionError("Only bounded storyboard drafts can be inspected")
                result = task.get("result")
                if (not isinstance(result, dict) or
                        len(quality_v14._canonical(result).encode("utf-8")) > 65000 or
                        quality_v14._sha(result) != found["output_sha"]):
                    raise PermissionError("Storyboard result digest mismatch")
                # Read-only review: model data displayed as text, never executed.
                session = self._session()
                session.setdefault("reviewed_ai_drafts", {})[ident] = found["output_sha"]
                return self._reply(200, {
                    "job_id": ident, "output_sha": found["output_sha"],
                    "quality": found["quality"], "decision": found["decision"],
                    "task": _public_task(task),
                    "storyboard": result})
            if route.startswith("/api/goals/"):
                ident = route.removeprefix("/api/goals/")
                return self._reply(200, brain_runner.inspect(
                    ident, brain_db_path=self.server.brain_db_path))
            if route.startswith("/api/tasks/"):
                ident = route.removeprefix("/api/tasks/")
                task = task_history.get_task(ident, db_path=self.server.task_db_path)
                return self._reply(200, {
                    **_public_task(task),
                    "events": [{"at": x["at"], "name": x["name"]}
                               for x in task["events"]]})
            if route.startswith("/api/growth/"):
                return self._reply(200, growth_reports.report(
                    route.removeprefix("/api/growth/"),
                    db_path=self.server.growth_db_path))
            return self._blocked(404, "not_found")
        except (ValueError, KeyError, PermissionError, TypeError, FileNotFoundError):
            return self._blocked(404, "not_found")

    def _read_json(self):
        if self.headers.get("Content-Type", "").lower() != "application/json":
            raise ValueError("Content-Type must be application/json")
        length_text = self.headers.get("Content-Length", "")
        if not length_text.isdecimal():
            raise ValueError("Content-Length required")
        length = int(length_text)
        if not 2 <= length <= MAX_BODY:
            raise ValueError("Request must be 2–8192 bytes")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("Incomplete request")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON object required")
        return data

    def do_POST(self):
        if not self._host_ok():
            return self._blocked(error="invalid_host")
        origin = self.headers.get("Origin")
        if origin != self._origin():
            return self._blocked(error="invalid_origin")
        if self.headers.get("Sec-Fetch-Site", "same-origin") not in {
                "same-origin", "none"}:
            return self._blocked(error="invalid_fetch_site")
        path = urlsplit(self.path).path
        try:
            data = self._read_json()
        except (UnicodeError, json.JSONDecodeError, ValueError):
            return self._blocked(400, "bad_json")
        if path == "/api/login":
            code = data.get("code")
            if not isinstance(code, str) or len(code) > 128:
                return self._blocked(401, "invalid_credentials")
            with self.server.auth_lock:
                now = time.monotonic()
                self.server.failed_logins = [
                    at for at in self.server.failed_logins if now - at < 60]
                if len(self.server.failed_logins) >= 5:
                    return self._blocked(429, "login_rate_limited")
                if not hmac.compare_digest(code, self.server.owner_code):
                    self.server.failed_logins.append(now)
                    return self._blocked(401, "invalid_credentials")
                session_id = secrets.token_urlsafe(32)
                csrf = secrets.token_urlsafe(32)
                self.server.sessions[session_id] = {
                    "csrf": csrf, "expires": now + SESSION_SECONDS}
            return self._reply(200, {"status": "AUTHENTICATED", "csrf": csrf},
                               headers=(("Set-Cookie", f"{COOKIE}={session_id}; "
                                         "HttpOnly; SameSite=Strict; Path=/; "
                                         f"Max-Age={SESSION_SECONDS}"),))
        session = self._session()
        if session is None:
            return self._blocked(401, "authentication_required")
        header = self.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(header, session["csrf"]):
            return self._blocked(403, "invalid_csrf")
        if path == "/api/logout":
            with self.server.auth_lock:
                jar = cookies.SimpleCookie()
                jar.load(self.headers.get("Cookie", ""))
                item = jar.get(COOKIE)
                if item:
                    self.server.sessions.pop(item.value, None)
            return self._reply(200, {"status": "LOGGED_OUT"},
                               headers=(("Set-Cookie", f"{COOKIE}=; "
                                         "HttpOnly; SameSite=Strict; Path=/; Max-Age=0"),))
        try:
            output = _owner_action(self.server, path, data, session)
            return self._reply(200, output)
        except (ValueError, KeyError, TypeError, PermissionError, FileExistsError) as exc:
            # Do not echo arbitrary input or secrets into an error response.
            msg = str(exc)[:180]
            return self._reply(400, {"error": type(exc).__name__,
                                     "message": msg})
        except Exception:
            return self._reply(500, {"error": "internal_error",
                                     "message": "Inspect local task/goal status; no automatic retry"})

    def do_PUT(self):
        return self._blocked(405, "method_not_allowed")

    def do_DELETE(self):
        return self._blocked(405, "method_not_allowed")

    def do_OPTIONS(self):
        return self._blocked(405, "no_cors")


def create_server(port=8780, *, owner_code=None, allow_external_actions=False,
                  task_db_path=None, brain_db_path=None, analytics_db_path=None,
                  growth_db_path=None):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Invalid port")
    if owner_code is not None and (
            not isinstance(owner_code, str) or not 12 <= len(owner_code) <= 128):
        raise ValueError("Owner code must be 12-128 characters")
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    server.daemon_threads = True
    server.owner_code = owner_code or secrets.token_urlsafe(24)
    server.sessions = {}
    server.failed_logins = []
    server.auth_lock = threading.RLock()
    server.task_db_path = task_db_path
    server.brain_db_path = brain_db_path
    server.analytics_db_path = analytics_db_path
    server.growth_db_path = growth_db_path
    server.allow_external_actions = allow_external_actions is True
    return server


def main():
    cli = argparse.ArgumentParser(
        description="Owner-authenticated localhost AgentForge Control Center V1")
    cli.add_argument("--port", type=int, default=8780)
    cli.add_argument("--allow-external-tools", action="store_true",
                     help="Explicitly enable gated model/network/browser/process workflows")
    args = cli.parse_args()
    server = create_server(args.port, allow_external_actions=args.allow_external_tools)
    print(f"Control Center V1: http://127.0.0.1:{server.server_port}/", flush=True)
    print("ONE-TIME OWNER CODE (do not share, paste into Git or logs):",
          server.owner_code, flush=True)
    print("Localhost only. Session expires in 8h; Ctrl+C to stop.", flush=True)
    if args.allow_external_tools:
        print("External-capable tools are ENABLED but still require per-action approvals.",
              flush=True)
    else:
        print("External-capable tools DISABLED. Read-only and owner-gated local actions only.",
              flush=True)
    try:
        server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
