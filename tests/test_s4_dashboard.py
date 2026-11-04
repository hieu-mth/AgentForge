"""S4 Dashboard V0 read-only HTTP security and goal queue tests."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import brain_planner, brain_store, brain_scheduler, dashboard_v0


class TestS4Dashboard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.brain_db = self.root / "s4.sqlite3"
        self.task_db = self.root / "s1.sqlite3"
        self.analytics_db = self.root / "s3.sqlite3"
        self.p = patch.object(brain_store, "DB", self.brain_db)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_goal_queue_and_api_exclude_input_and_memory(self):
        goal = brain_planner.propose(
            "Review <script>alert(1)</script> campaign",
            "campaign.review", {"dataset": "secret-campaign"},
            db_path=self.brain_db)
        brain_store.set_memory(
            "owner.internal", "private note: do not expose", "owner:private",
            confirm_write=True, db_path=self.brain_db)
        markup = dashboard_v0.render_dashboard(
            db_path=self.task_db, brain_db_path=self.brain_db,
            analytics_db_path=self.analytics_db)
        self.assertIn("&lt;script&gt;", markup)
        self.assertNotIn("<script>alert(1)</script>", markup)
        self.assertNotIn("private note: do not expose", markup)
        self.assertNotIn("secret-campaign", markup)
        self.assertIn("S4 Company Goals", markup)
        server = dashboard_v0.create_server(
            0, db_path=self.task_db, brain_db_path=self.brain_db,
            analytics_db_path=self.analytics_db)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for endpoint in ("/api/goals", "/api/schedules",
                             "/api/goals/" + goal["goal_id"]):
                conn = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=3)
                conn.request("GET", endpoint)
                resp = conn.getresponse()
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read())
                self.assertNotIn("secret-campaign", json.dumps(body))
                self.assertNotIn("private note", json.dumps(body))
                self.assertEqual(resp.getheader("Cache-Control"), "no-store")
                conn.close()
            conn = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=3)
            conn.request("POST", "/api/goals", body="{}")
            response = conn.getresponse()
            self.assertEqual(response.status, 405)
            response.read()
            conn.close()
            conn = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=3)
            conn.request("GET", "/api/goals", headers={"Host": "evil.invalid"})
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)


if __name__ == "__main__":
    unittest.main()
