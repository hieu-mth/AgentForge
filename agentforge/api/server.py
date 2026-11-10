"""Canonical localhost-only Owner HTTP transport; no business logic in this module."""
import argparse
import hmac
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from agentforge.api import auth
from agentforge.api.auth import COOKIE, SESSION_SECONDS
from agentforge.api.static import _react_asset
from agentforge.api.routes import read
from agentforge.api.routes.mutations import _owner_action

MAX_BODY = 65536


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
                 "; connect-src 'self'; img-src 'self' data:; media-src 'self'; font-src 'self' data:; "+
                 "frame-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _stream_video(self, file_path):
        """Authenticated, bounded-memory local MP4 stream with seek support.

        Caller must verify ownership, source digest and path before entry.
        Only a single strict byte range is supported; malformed ranges fail
        closed instead of falling back to an unbounded full-file response.
        """
        from agentforge.api.video_stream import parse_range
        length = file_path.stat().st_size
        requested = self.headers.get("Range")
        start, end, partial = parse_range(requested, length)
        count = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(count))
        self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{length}")
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        try:
            with file_path.open("rb") as stream:
                stream.seek(start)
                remaining = count
                while remaining:
                    block = stream.read(min(64 * 1024, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError):
            # Browser seek/cancel can close an in-progress response normally.
            pass

    def _session(self):
        return auth.get_session(self)


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
        if route == "/":
            # One canonical frontend: redirect legacy bookmarks without serving old UI.
            return self._reply(302, "", mime="text/plain; charset=utf-8",
                               headers=(("Location", "/dashboard/"),))
        if route in ("/app.css", "/app.js", "/app.html"):
            return self._blocked(404, "not_found")
        if self._session() is None:
            return self._blocked(401, "authentication_required")
        try:
            return read.dispatch(self, route)
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
            return auth.login(self, data)
        session = self._session()
        if session is None:
            return self._blocked(401, "authentication_required")
        header = self.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(header, session["csrf"]):
            return self._blocked(403, "invalid_csrf")
        if path == "/api/logout":
            return auth.logout(self)
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
    print(f"AgentForge Dashboard: http://127.0.0.1:{server.server_port}/dashboard/", flush=True)
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
