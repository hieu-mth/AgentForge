"""Control Center V1: real local HTTP authentication and mutation-policy tests."""
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agentforge import analytics_store, brain_store, growth_store, task_history
from agentforge import control_center_v1 as cc
from agentforge import ops_daemon


CODE = "super-long-test-owner-code-2026"


class TestControlCenterV1(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.taskdb = self.root / "tasks.sqlite3"
        self.brain = self.root / "brain.sqlite3"
        self.growth = self.root / "growth.sqlite3"
        self.analytics = self.root / "analytics.sqlite3"
        self.server = cc.create_server(
            0, owner_code=CODE,
            task_db_path=self.taskdb, brain_db_path=self.brain,
            growth_db_path=self.growth, analytics_db_path=self.analytics)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.cookie = None
        self.csrf = None
        # Underlying trusted S1 adapters use the local default database paths.
        # Patch them to the isolated fixture when testing browser delegation.
        self.store_patch = patch.object(growth_store, "DB", self.growth)
        self.store_patch.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(4)
        self.store_patch.stop()
        self.tmp.cleanup()

    def req(self, method, path, data=None, *, host=None, origin=None,
            cookie=True, csrf=True, content_type="application/json"):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=8)
        headers = {"Host": self.host if host is None else host}
        if method == "POST":
            headers["Origin"] = f"http://{self.host}" if origin is None else origin
            headers["Content-Type"] = content_type
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        if csrf and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        body = json.dumps(data or {}) if method == "POST" else None
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        status = response.status
        meta = dict(response.getheaders())
        raw = response.read()
        conn.close()
        try:
            output = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            output = raw.decode("utf-8", errors="replace")
        return status, output, meta

    def login(self):
        code, result, headers = self.req(
            "POST", "/api/login", {"code": CODE})
        self.assertEqual(code, 200)
        self.csrf = result["csrf"]
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])

    def campaign(self):
        return self.req("POST", "/api/campaigns/create", {
            "ack": "CREATE_CAMPAIGN", "data": {
                "campaign": "nem-pilot", "title": "Tư vấn nệm",
                "analytics_dataset": "", "budget_vnd": 50000,
                "synthetic": False,
            }})

    def test_ui_assets_without_credentials_but_api_requires_session(self):
        for route, expected in (
            ("/", "AgentForge"), ("/app.js", "strict"),
            ("/app.css", "--nav")):
            code, body, headers = self.req("GET", route)
            self.assertEqual(code, 200)
            self.assertIn(expected, body)
            self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
            self.assertEqual(headers["Cache-Control"], "no-store")
        code, _, _ = self.req("GET", "/api/bootstrap")
        self.assertEqual(code, 401)
        code, _, _ = self.req("GET", "/api/goals/" + "a" * 32)
        self.assertEqual(code, 401)
        self.assertFalse(self.brain.exists())

    def test_login_wrong_credentials_rate_limited(self):
        for index in range(5):
            code, _, _ = self.req("POST", "/api/login", {"code": "not-the-code"})
            self.assertEqual(code, 401)
        code, _, _ = self.req("POST", "/api/login", {"code": CODE})
        self.assertEqual(code, 429)
        self.assertFalse(self.brain.exists())

    def test_session_refresh_and_logout(self):
        self.login()
        code, result, _ = self.req("GET", "/api/session")
        self.assertEqual(code, 200)
        self.assertEqual(result["csrf"], self.csrf)
        code, payload, _ = self.req("GET", "/api/bootstrap")
        self.assertEqual(code, 200)
        self.assertEqual(payload["stats"]["skills"], 24)
        self.assertFalse(payload["external_actions_enabled"])
        self.assertEqual(len(payload["connectors"]), 3)
        self.assertFalse(payload["connectors"][0]["authenticated"])
        self.assertNotIn(CODE, json.dumps(payload))
        code, out, headers = self.req("POST", "/api/logout", {})
        self.assertEqual(code, 200)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        code, _, _ = self.req("GET", "/api/bootstrap")
        self.assertEqual(code, 401)

    def test_csrf_origin_host_and_body_guards(self):
        self.login()
        for params in (
            {"csrf": False},
            {"origin": "http://evil.invalid"},
            {"host": "evil.invalid"},
            {"content_type": "text/plain"},
        ):
            code, _, _ = self.req(
                "POST", "/api/goals/propose", {"ack": "PROPOSE",
                  "title": "Review something",
                  "template": "growth.review",
                  "inputs": {"campaign": "nem-pilot"}}, **params)
            self.assertIn(code, (400, 403))
        code, _, _ = self.req("POST", "/api/goals/propose",
                              {"ack": "PROPOSE"} )
        self.assertEqual(code, 400)
        self.assertFalse(self.brain.exists())
        code, _, _ = self.req("GET", "/api/bootstrap", host="evil.invalid")
        self.assertEqual(code, 403)
        code, _, _ = self.req("PUT", "/api/goals/propose")
        self.assertEqual(code, 405)

    def test_approval_sha_and_readonly_growth_execution_via_http(self):
        self.login()
        c, created, _ = self.campaign()
        self.assertEqual(c, 200)
        self.assertEqual(created["status"], "CREATED")
        code, goal, _ = self.req("POST", "/api/goals/propose", {
            "ack": "PROPOSE", "title": "Review local growth",
            "template": "growth.review", "inputs": {"campaign": "nem-pilot"}})
        self.assertEqual(code, 200)
        self.assertEqual(goal["status"], "PLANNED")
        self.assertEqual(goal["step_count"], 3)
        self.assertFalse(self.taskdb.exists())
        id = goal["goal_id"]
        code, _, _ = self.req("POST", f"/api/goals/{id}/approve", {
            "ack": "APPROVE", "plan_sha256": "0" * 64})
        self.assertEqual(code, 400)
        code, g, _ = self.req("GET", f"/api/goals/{id}")
        self.assertEqual(code, 200)
        self.assertEqual(g["plan_sha256"], goal["plan_sha256"])
        code, _, _ = self.req("POST", f"/api/goals/{id}/approve", {
            "ack": "APPROVE", "plan_sha256": goal["plan_sha256"]})
        self.assertEqual(code, 200)
        self.assertFalse(self.taskdb.exists())
        code, output, _ = self.req("POST", f"/api/goals/{id}/run", {
            "ack": "RUN", "plan_sha256": goal["plan_sha256"], "grants":[]})
        self.assertEqual(code, 200)
        self.assertEqual(output["status"], "SUCCEEDED")
        self.assertEqual(output["executed_steps"], 3)
        code, _, _ = self.req("POST", f"/api/goals/{id}/run", {
            "ack": "RUN", "plan_sha256": goal["plan_sha256"], "grants":[]})
        self.assertEqual(code, 400)
        self.assertEqual(len(task_history.list_tasks(db_path=self.taskdb)), 4)
        code, task, _ = self.req("GET", f"/api/tasks/{output['task_id']}")
        self.assertEqual(code, 200)
        self.assertEqual(task["status"], "SUCCEEDED")
        self.assertNotIn("request", task)

    def test_external_actions_disabled_even_when_owner_grants(self):
        self.login()
        code, output, _ = self.req("POST", "/api/goals/propose", {
            "ack": "PROPOSE", "title": "Research a market",
            "template": "research.discovery",
            "inputs": {"topic": "Nghiên cứu thị trường nệm"},
            "max_model_calls": 2})
        self.assertEqual(code, 200)
        id = output["goal_id"]
        self.req("POST", f"/api/goals/{id}/approve", {
            "ack":"APPROVE", "plan_sha256":output["plan_sha256"]})
        code, _, _ = self.req("POST", f"/api/goals/{id}/run", {
            "ack":"RUN", "plan_sha256":output["plan_sha256"],
            "grants": ["model.invoke","network.search","workspace.write"],
            "ack_external":"AUTHORIZE_EXTERNAL_TOOLS",
            "confirm_model_call":True})
        self.assertEqual(code, 400)
        self.assertFalse(self.taskdb.exists())
        self.assertEqual(brain_store.get_goal(id,db_path=self.brain)["status"],
                         "APPROVED")

    def test_growth_event_pii_rejected_before_db_or_task_write(self):
        self.login()
        self.campaign()
        code, _, _ = self.req("POST", "/api/campaigns/event", {
            "ack": "RECORD_EVENT", "kind": "lead_new",
            "data": {"campaign":"nem-pilot","channel":"website",
                     "consent_confirmed":True, "phone":"+84123456789"}})
        self.assertEqual(code, 400)
        self.assertNotIn(b"+84123456789", self.growth.read_bytes())
        code, good, _ = self.req("POST", "/api/campaigns/event", {
            "ack":"RECORD_EVENT","kind":"lead_new",
            "data":{"campaign":"nem-pilot","channel":"website",
                    "consent_confirmed":True}})
        self.assertEqual(code, 200)
        self.assertTrue(good["personal_data_stored"] is False)
        code, data, _ = self.req("GET", "/api/bootstrap")
        self.assertEqual(data["growth"][0]["lead_total"],1)
        self.assertNotIn("lead_id", json.dumps(data))

    def test_schedule_readonly_api_and_standing_sha(self):
        self.login()
        self.campaign()
        due=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        code, created, _ = self.req("POST", "/api/schedules/create", {
            "ack":"SCHEDULE", "title":"Periodic growth review",
            "template":"growth.review", "inputs":{"campaign":"nem-pilot"},
            "frequency_minutes":60, "next_due":due})
        self.assertEqual(code,200)
        self.assertEqual(created["status"],"ACTIVE")
        code, _, _ = self.req("POST", "/api/schedules/create", {
            "ack":"SCHEDULE", "title":"Dangerous browser schedule",
            "template":"website.browser", "inputs":{"slug":"nem-tu-van"},
            "frequency_minutes":60, "next_due":due})
        self.assertEqual(code,400)
        code, updated, _ = self.req(
            "POST",f"/api/schedules/{created['schedule_id']}/status",
            {"ack":"PAUSED","status":"PAUSED"})
        self.assertEqual(code,200)
        self.assertEqual(updated["status"],"PAUSED")
        code, tick, _ = self.req("POST","/api/schedules/tick",{"ack":"TICK"})
        self.assertEqual(code,200)
        self.assertEqual(len(tick["claimed"]),0)

    def test_website_draft_contract_and_proposal_apply_requires_prior_review(self):
        from agentforge import brain_planner
        with self.assertRaisesRegex(brain_store.BrainError, "cap"):
            brain_planner.propose(
                "Create test website", "website.draft", {
                    "slug": "nem-test", "brief": "Tạo landing page tư vấn nệm Việt Nam."
                }, db_path=self.brain)
        self.assertFalse(self.brain.exists())
        plan = brain_planner.propose(
            "Create test website", "website.draft", {
                "slug": "nem-test", "brief": "Tạo landing page tư vấn nệm Việt Nam."
            }, max_model_calls=1, db_path=self.brain)
        self.assertEqual(plan["step_count"], 1)
        self.assertEqual(plan["plan"][0]["skill_id"], "web.create")
        self.login()
        fake_id, fake_sha = "b" * 32, "c" * 64
        task_id = task_history.create_task(
            "skill", "web.create", {"slug": "nem-test"},
            db_path=self.taskdb)
        task_history.transition(task_id, "RUNNING", db_path=self.taskdb)
        task_history.transition(task_id, "SUCCEEDED", result={
            "proposal_id": fake_id, "sha256": fake_sha,
            "project_slug": "nem-test",
        }, db_path=self.taskdb)
        code, data, _ = self.req("GET", "/api/bootstrap")
        self.assertEqual(code, 200)
        self.assertEqual(data["tasks"][0]["web_proposal"]["proposal_id"], fake_id)
        document = {
            "proposal_id": fake_id, "status": "PROPOSED_NOT_APPLIED",
            "project_slug": "nem-test", "sha256": fake_sha,
            "summary": "Local static website for owner review",
            "files": [{"path": "index.html",
                       "content": "<html><body>Untrusted source</body></html>"}],
        }
        with patch("agentforge.product_builder._read_proposal",
                   return_value=(document, self.root / "proposal.json")):
            with patch("agentforge.product_builder.inspect",
                       return_value={"sha256": fake_sha}) as inspect:
                with patch("agentforge.product_builder.apply",
                           return_value={"status": "FILES_WRITTEN_NOT_EXECUTED",
                                         "files":["index.html"],
                                         "project_path": "workspace/products/nem-test"}) as apply:
                    action = "/api/proposals/" + fake_id + "/apply"
                    code, _, _ = self.req("POST", action, {
                        "ack": "APPLY_PROPOSAL", "sha256": fake_sha})
                    self.assertEqual(code, 400)
                    apply.assert_not_called()
                    code, proposal, _ = self.req("GET", "/api/proposals/"+fake_id)
                    self.assertEqual(code, 200)
                    self.assertEqual(proposal["sha256"], fake_sha)
                    self.assertIn("Untrusted source", proposal["files"][0]["content"])
                    code, _, _ = self.req("POST", action, {
                        "ack": "APPLY_PROPOSAL", "sha256": "0" * 64})
                    self.assertEqual(code, 400)
                    apply.assert_not_called()
                    code, result, _ = self.req("POST", action, {
                        "ack": "APPLY_PROPOSAL", "sha256": fake_sha})
                    self.assertEqual(code, 200)
                    self.assertEqual(result["status"], "FILES_WRITTEN_NOT_EXECUTED")
                    inspect.assert_called()
                    apply.assert_called_once_with(
                        fake_id, confirm_write=True, sha256=fake_sha)

    def test_maximum_json_body_and_no_arbitrary_routes(self):
        self.login()
        code, _, _ = self.req(
            "POST","/api/goals/propose",{"ack":"PROPOSE","unused":"x"*8500})
        self.assertEqual(code,400)
        code, _, _ = self.req("POST","/api/arbitrary_execute",
                              {"ack":"EXEC"})
        self.assertEqual(code,400)
        self.assertFalse(self.taskdb.exists())
        self.assertFalse(self.brain.exists())


class TestLocalDaemon(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.beat=self.root/"heartbeat.json"
        self.lock=self.root/"daemon.lock"
        self.db=self.root/"schedules.sqlite3"
        self.tasks=self.root/"tasks.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_readonly_daemon_optin_and_observable_health(self):
        with self.assertRaises(PermissionError):
            ops_daemon.run_loop(interval_seconds=30, lock_path=self.lock,
                                heartbeat_path=self.beat)
        result=ops_daemon.tick_once(
            db_path=self.db,task_db_path=self.tasks,heartbeat_path=self.beat)
        self.assertEqual(result["status"],"NO_DUE_SCHEDULES")
        health=ops_daemon.read_heartbeat(path=self.beat)
        self.assertTrue(health["fresh"])
        self.assertFalse(health["trusted_pid_verification"])
        self.assertFalse(self.db.exists())
        stopped=threading.Event()
        stopped.set()
        done=ops_daemon.run_loop(interval_seconds=30,confirm_unattended=True,
                                 stop_event=stopped,lock_path=self.lock,
                                 heartbeat_path=self.beat,db_path=self.db,
                                 task_db_path=self.tasks)
        self.assertEqual(done["cycles"],0)
        self.assertFalse(ops_daemon.read_heartbeat(path=self.beat)["fresh"])

    def test_os_exclusive_daemon_lock_prevents_second_runner(self):
        with ops_daemon.exclusive_instance(self.lock):
            with self.assertRaisesRegex(RuntimeError,"Another AgentForge"):
                with ops_daemon.exclusive_instance(self.lock):
                    pass


if __name__=="__main__":
    unittest.main()
