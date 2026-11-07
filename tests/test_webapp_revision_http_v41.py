"""V4.1 real authenticated Control Center app review/revise/apply API tests."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import control_center_v1 as cc
from agentforge import webapp_builder, brain_store
from tests.test_webapp_builder_v40 import SPEC, BRIEF

CODE = "strong-local-v41-test-owner-code"


class WebappRevisionHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.brain = root / "brain.sqlite3"
        self.tasks = root / "tasks.sqlite3"
        for name, value in [
            ("PROJECTS", root / "workspace" / "webapps"),
            ("PROPOSALS", root / "proposals"),
        ]:
            p = patch.object(webapp_builder, name, value)
            p.start()
            self.addCleanup(p.stop)
        with patch("agentforge.model.generate_json", return_value=SPEC):
            self.proposal = webapp_builder.propose("demo-source", BRIEF)
        self.server = cc.create_server(
            0, owner_code=CODE, brain_db_path=self.brain, task_db_path=self.tasks)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._shutdown)
        self.host = "127.0.0.1:" + str(self.server.server_port)
        self.cookie = None
        self.csrf = None

    def _shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=4)

    def req(self, method, path, data=None, *, csrf=True, cookie=True):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=8)
        headers = {"Host": self.host}
        if method == "POST":
            headers["Origin"] = "http://" + self.host
            headers["Content-Type"] = "application/json"
            if csrf and self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        conn.request(method, path,
                     body=json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None,
                     headers=headers)
        r = conn.getresponse()
        status = r.status
        headers = dict(r.getheaders())
        raw = r.read()
        conn.close()
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            data = raw.decode("utf-8", errors="replace")
        return status, data, headers

    def login(self):
        code, response, headers = self.req("POST", "/api/login", {"code": CODE})
        self.assertEqual(code, 200, response)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = response["csrf"]

    def test_get_requires_login_and_allows_signed_source_review(self):
        pid = self.proposal["proposal_id"]
        unauth, _, _ = self.req("GET", "/api/webapps/" + pid)
        self.assertEqual(unauth, 401)
        self.login()
        ok, data, headers = self.req("GET", "/api/webapps/" + pid)
        self.assertEqual(ok, 200, data)
        self.assertEqual(data["sha256"], self.proposal["sha256"])
        self.assertEqual(data["proposal_id"], pid)
        self.assertEqual(len(data["files"]), len(webapp_builder.OUTPUTS))
        self.assertFalse(data["comparison"]["revision"])
        self.assertFalse(data["execution_authorized"])
        self.assertIn("no-store", headers["Cache-Control"])

    def test_app_apply_requires_session_review_matching_sha_and_csrf(self):
        pid, sha = self.proposal["proposal_id"], self.proposal["sha256"]
        self.login()
        path = "/api/webapps/" + pid + "/apply"
        payload = {"ack": "APPLY_WEBAPP", "sha256": sha}
        missing_review, _, _ = self.req("POST", path, payload)
        self.assertEqual(missing_review, 400)
        self.req("GET", "/api/webapps/" + pid)
        forged, _, _ = self.req("POST", path, {"ack": "APPLY_WEBAPP", "sha256": "0" * 64})
        self.assertEqual(forged, 400)
        no_csrf, _, _ = self.req("POST", path, payload, csrf=False)
        self.assertEqual(no_csrf, 403)
        ok, data, _ = self.req("POST", path, payload)
        self.assertEqual(ok, 200, data)
        self.assertEqual(data["status"], "FILES_WRITTEN_NOT_EXECUTED")
        self.assertTrue((webapp_builder.PROJECTS / "demo-source" / "src" / "App.jsx").exists())

    def test_revision_endpoint_creates_goal_but_does_not_dispatch_model(self):
        pid, sha = self.proposal["proposal_id"], self.proposal["sha256"]
        self.login()
        self.req("GET", "/api/webapps/" + pid)
        path = "/api/webapps/" + pid + "/revision"
        feedback = "Đổi màu xanh navy và chỉnh phần tiêu đề đầu trang."
        with (patch("agentforge.workspace_policy.read", return_value={
            "website_enabled": True, "max_estimated_model_calls": 1
        }), patch("agentforge.model.generate_json") as model):
            code, result, _ = self.req(
                "POST", path,
                {"ack": "REQUEST_REVISION", "sha256": sha, "feedback": feedback})
            model.assert_not_called()
        self.assertEqual(code, 200, result)
        self.assertEqual(result["status"], "PLAN_CREATED")
        goal = brain_store.get_goal(result["goal_id"], db_path=self.brain)
        self.assertEqual(goal["template"], "webapp.revision")
        self.assertEqual(goal["plan"][0]["payload"]["revision_feedback"], feedback)
        self.assertEqual(goal["plan"][0]["payload"]["source_sha256"], sha)
        self.assertFalse(webapp_builder.PROJECTS.exists())
        rejected, _, _ = self.req("POST", path,
            {"ack": "REQUEST_REVISION", "sha256": "0" * 64, "feedback": feedback})
        self.assertEqual(rejected, 400)


if __name__ == "__main__":
    unittest.main()
