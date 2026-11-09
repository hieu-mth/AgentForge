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
from agentforge.core import artifact_acceptance
from agentforge.dashboard_v0 import _artifact_names, _task_public

STATIC = Path(__file__).with_name("control_center_static")
COOKIE = "af_owner_session"
SESSION_SECONDS = 8 * 60 * 60
MAX_BODY = 65536
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



def _public_task(task, *, db_path=None):
    output = _task_public(task)
    output["artifact_acceptance"] = artifact_acceptance.for_task(task, db_path=db_path)
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
