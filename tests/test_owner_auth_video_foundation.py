"""Owner HTTP security regression independent of removed Webapp/NovaMart fixtures."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from agentforge.api.server import create_server


class OwnerAuthVideoFoundationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.code = "owner-video-foundation-test-secret"
        self.server = create_server(
            0, owner_code=self.code,
            task_db_path=root / "tasks.sqlite3",
            brain_db_path=root / "brain.sqlite3",
            analytics_db_path=root / "analytics.sqlite3",
            growth_db_path=root / "growth.sqlite3",
        )
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 3)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.cookie = ""
        self.csrf = ""

    def request(self, method, path, payload=None, *, csrf=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=8)
        headers = {"Host": self.host}
        if method == "POST":
            headers.update({"Origin": f"http://{self.host}", "Content-Type": "application/json"})
        if self.cookie:
            headers["Cookie"] = self.cookie
        if csrf and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        try:
            conn.request(method, path,
                         body=json.dumps(payload or {}) if method == "POST" else None,
                         headers=headers)
            response = conn.getresponse()
            raw = response.read()
            try:
                body = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                body = raw
            return response.status, body, dict(response.getheaders())
        finally:
            conn.close()

    def test_owner_session_csrf_and_logout(self):
        self.assertEqual(self.request("GET", "/api/session")[0], 401)
        self.assertEqual(self.request("GET", "/api/video-studio/projects")[0], 401)
        status, result, headers = self.request("POST", "/api/login", {"code": self.code})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = result["csrf"]
        status, session, _ = self.request("GET", "/api/session")
        self.assertEqual(status, 200)
        self.assertEqual(session["csrf"], self.csrf)
        self.assertEqual(self.request("POST", "/api/logout", {}, csrf=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/logout", {})[0], 200)
        self.assertEqual(self.request("GET", "/api/session")[0], 401)

    def test_dashboard_redirect_and_retired_routes_are_not_exposed(self):
        status, _, headers = self.request("GET", "/")
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("Location"), "/dashboard/")
        status, result, headers = self.request("POST", "/api/login", {"code": self.code})
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = result["csrf"]
        for route in ("/api/mattress", "/api/growth/old",
                      "/api/webapps/old", "/api/proposals/old",
                      "/api/visuals/website/old"):
            with self.subTest(route=route):
                self.assertEqual(self.request("GET", route)[0], 404)

    def test_film_inventory_requires_authentication(self):
        self.assertEqual(self.request("GET", "/api/film/productions")[0], 401)
        self.assertEqual(self.request("GET", "/api/characters")[0], 401)
        self.assertEqual(self.request("GET", "/api/model-hub")[0], 401)


if __name__ == "__main__":
    unittest.main()
