"""S4 Owner API: explicit authentication and no public legacy dashboard."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import brain_planner, brain_store
from agentforge import control_center_v1 as cc


class TestS4Dashboard(unittest.TestCase):
    def test_goals_are_auth_protected_and_served_as_json_not_html(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            brain_db = root / "brain.db"
            goal = brain_planner.propose(
                "Review <script>alert(1)</script> campaign",
                "campaign.review", {"dataset": "secret-campaign"},
                db_path=brain_db)
            brain_store.set_memory(
                "owner.internal", "private note: do not expose", "owner:private",
                confirm_write=True, db_path=brain_db)
            server = cc.create_server(
                0, owner_code="test-owner-secret-2026",
                task_db_path=root / "task.db",
                brain_db_path=brain_db,
                analytics_db_path=root / "analytics.db",
                growth_db_path=root / "growth.db")
            self.assertEqual(server.server_address[0], "127.0.0.1")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host = f"127.0.0.1:{server.server_port}"

            def request(method, route, *, payload=None, cookie=None, host_header=None):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                                  timeout=6)
                headers = {"Host": host if host_header is None else host_header}
                if method == "POST":
                    headers["Origin"] = f"http://{host}"
                    headers["Content-Type"] = "application/json"
                if cookie:
                    headers["Cookie"] = cookie
                body = json.dumps(payload) if payload is not None else None
                conn.request(method, route, body=body, headers=headers)
                resp = conn.getresponse()
                status, meta, content = resp.status, dict(resp.getheaders()), resp.read()
                conn.close()
                return status, meta, content

            try:
                status, _, _ = request("GET", "/api/bootstrap")
                self.assertEqual(401, status)
                status, _, _ = request("GET", "/api/bootstrap",
                                       host_header="evil.invalid")
                self.assertEqual(403, status)
                status, headers, body = request(
                    "POST", "/api/login", payload={"code": "test-owner-secret-2026"})
                self.assertEqual(200, status)
                cookie = headers["Set-Cookie"].split(";", 1)[0]
                self.assertIn("HttpOnly", headers["Set-Cookie"])
                status, headers, body = request(
                    "GET", "/api/bootstrap", cookie=cookie)
                self.assertEqual(200, status)
                self.assertTrue(headers["Content-Type"].startswith("application/json"))
                self.assertEqual("no-store", headers["Cache-Control"])
                data = json.loads(body)
                self.assertTrue(data["authenticated"])
                self.assertIn(goal["goal_id"], [g["goal_id"] for g in data["goals"]])
                self.assertNotIn("private note: do not expose", body.decode())
                status, headers, _ = request("GET", "/", cookie=None)
                self.assertEqual(302, status)
                self.assertEqual("/dashboard/", headers["Location"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(5)


if __name__ == "__main__":
    unittest.main()
