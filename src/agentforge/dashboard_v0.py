"""S1 Dashboard V0: local-only, read-only task/skill monitor.

No JavaScript, no mutations, no execution endpoints, no external assets.
Do not expose this unauthenticated localhost UI to an external interface.
"""
import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from agentforge import skill_registry, task_history

CSS = """body{margin:0;background:#101827;color:#e5eaf2;font:16px/1.55 system-ui,Segoe UI,Tahoma,sans-serif}
main{max-width:1160px;margin:auto;padding:28px 20px}
h1{font-size:2rem;letter-spacing:-.03em}h2{font-size:1.2rem;margin-top:32px}
small,.muted{color:#9eabc1}a{color:#96c5ff;text-decoration:none}
table{width:100%;border-collapse:collapse;background:#1b2638;border-radius:12px;overflow:hidden}
th,td{padding:11px 12px;border-bottom:1px solid #35445d;text-align:left;vertical-align:top}
th{font-size:.84rem;color:#b9c5d5}td{overflow-wrap:anywhere}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.stat{padding:18px;background:#1b2638;border:1px solid #35445d;border-radius:12px}
.stat strong{font-size:1.5rem;display:block}code{color:#d1e2f9}
.note{margin:20px 0;padding:12px;background:#293344;border-left:3px solid #96c5ff}
@media(max-width:600px){body{font-size:14px}th,td{padding:7px 5px}main{padding:15px 10px}}
"""


def _safe(value):
    return html.escape(str(value), quote=True)


def _task_public(task):
    """Avoid exposing full prompts, file contents and model output via HTTP."""
    return {key: task[key] for key in (
        "task_id", "kind", "skill_id", "parent_id", "status",
        "created_at", "updated_at", "error"
    )}


def _artifact_names(result):
    """Show only artifact basenames, never full local paths or output bodies."""
    found = []
    def visit(value, depth=0):
        if depth > 4 or len(found) >= 12:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"report_path", "proposal_path", "project_path",
                           "preview_path", "screenshot_path"} and isinstance(item, str):
                    label = item.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
                    if label and label not in found:
                        found.append(label[:100])
                elif key == "screenshots" and isinstance(item, list):
                    for image in item[:6]:
                        if isinstance(image, str):
                            visit({"screenshot_path": image}, depth + 1)
                elif isinstance(item, dict):
                    visit(item, depth + 1)
    visit(result)
    return found


def render_dashboard(*, db_path=None, selected=None):
    tasks = task_history.list_tasks(db_path=db_path, limit=100)
    registry = skill_registry.load_registry()
    skill_count = len(registry)
    stats = {name: sum(t["status"] == name for t in tasks)
             for name in ("SUCCEEDED", "RUNNING", "WAITING_APPROVAL", "FAILED", "INTERRUPTED")}
    cards = "".join(
        '<div class="stat"><strong>' + str(value) + '</strong>' + _safe(label) + '</div>'
        for label, value in [("Visible tasks", len(tasks)), ("Registered skills", skill_count),
                             ("Succeeded", stats["SUCCEEDED"]), ("Needs approval", stats["WAITING_APPROVAL"]),
                             ("Failed", stats["FAILED"])]
    )
    task_rows = "".join(
        "<tr><td><a href='/?task=" + _safe(t["task_id"]) + "'><code>" +
        _safe(t["task_id"][:12]) + "</code></a></td><td>" + _safe(t["skill_id"]) +
        "</td><td>" + _safe(t["status"]) + "</td><td>" +
        _safe(t["updated_at"]) + "</td></tr>" for t in tasks
    )
    detail = ""
    if selected:
        task = task_history.get_task(selected, db_path=db_path)
        event_rows = "".join(
            "<tr><td>" + _safe(e["at"]) + "</td><td>" +
            _safe(e["name"]) + "</td></tr>" for e in task["events"]
        )
        artifacts = _artifact_names(task["result"])
        artifact_text = ", ".join(_safe(a) for a in artifacts) if artifacts else "None recorded"
        detail = ("<h2>Task " + _safe(task["task_id"]) + "</h2><p>" +
                  _safe(task["status"]) + " · " + _safe(task["skill_id"]) +
                  "</p><p>Artifact references (basenames): " + artifact_text + "</p>"
                  "<table><tr><th>At</th><th>Event</th></tr>" +
                  event_rows + "</table>")
    skill_rows = "".join(
        "<tr><td>" + _safe(item["id"]) + "</td><td>" +
        _safe(item["worker_id"]) + "</td><td>" +
        _safe(item["execution_mode"]) + "</td></tr>"
        for item in registry.values()
    )
    return ("<!doctype html><html lang='vi'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>AgentForge · Control Center V0</title><style>" + CSS +
            "</style></head><body><main><h1>AgentForge Control Center</h1>"
            "<p class='muted'>S1 Dashboard V0 · Local-only · Read-only</p>"
            "<div class='note'>Tasks are recorded facts about execution, not proof of secure "
            "code, customer revenue, or an autonomous company. No actions can run here.</div>"
            "<div class='stats'>" + cards + "</div>"
            "<h2>Recent tasks <small>(last 100)</small></h2>"
            "<table><tr><th>Task ID</th><th>Skill / Workflow</th>"
            "<th>Status</th><th>Updated (UTC)</th></tr>" + task_rows +
            "</table>" + detail +
            "<h2>Skills and Workers</h2>"
            "<table><tr><th>Skill</th><th>Worker</th><th>Mode</th></tr>" +
            skill_rows + "</table>"
            "<p class='muted'>Refresh to update. API: /api/tasks · /api/skills</p>"
            "</main></body></html>")


def create_server(port=8765, *, db_path=None):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535")

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code, body, mime):
            raw = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; style-src 'unsafe-inline'; "
                             "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def _local_host(self):
            # Reject DNS-rebinding style Host headers, not just remote binds.
            host = self.headers.get("Host", "").lower()
            return host in {"127.0.0.1", "localhost",
                            f"127.0.0.1:{self.server.server_port}",
                            f"localhost:{self.server.server_port}"}

        def do_GET(self):
            if not self._local_host():
                self._reply(403, '{"error":"invalid_host"}', "application/json")
                return
            parsed = urlsplit(self.path)
            try:
                if parsed.path == "/":
                    params = parse_qs(parsed.query)
                    selected = params.get("task", [None])[0]
                    self._reply(200, render_dashboard(db_path=db_path, selected=selected),
                                "text/html")
                elif parsed.path == "/api/tasks":
                    data = [_task_public(t) for t in task_history.list_tasks(db_path=db_path)]
                    self._reply(200, json.dumps(data, ensure_ascii=False), "application/json")
                elif parsed.path == "/api/skills":
                    data = [{"id": k, "version": v["version"],
                             "execution_mode": v["execution_mode"]}
                            for k, v in skill_registry.load_registry().items()]
                    self._reply(200, json.dumps(data), "application/json")
                elif parsed.path.startswith("/api/tasks/"):
                    ident = parsed.path.removeprefix("/api/tasks/")
                    data = task_history.get_task(ident, db_path=db_path)
                    data = {**_task_public(data),
                            "artifacts": _artifact_names(data["result"]),
                            "events": [{"at": e["at"], "name": e["name"]}
                                       for e in data["events"]]}
                    self._reply(200, json.dumps(data), "application/json")
                else:
                    self._reply(404, '{"error":"not_found"}', "application/json")
            except (ValueError, KeyError, PermissionError):
                self._reply(404, '{"error":"not_found"}', "application/json")

        def do_POST(self):
            if not self._local_host():
                self._reply(403, '{"error":"invalid_host"}', "application/json")
                return
            self._reply(405, '{"error":"read_only"}', "application/json")

        def log_message(self, format, *args):
            return  # Do not log task identifiers/URLs to the console.

    # Never allow a custom network host. No remote access or authentication.
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="S1 local-only task monitor")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = create_server(args.port)
    print(f"Read-only Dashboard V0: http://127.0.0.1:{server.server_port}/",
          flush=True)
    print("Ctrl+C to stop; do not expose to other hosts.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
