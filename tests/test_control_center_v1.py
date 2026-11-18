"""Control Center V1: real local HTTP authentication and mutation-policy tests."""
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agentforge import analytics_store, brain_planner, brain_scheduler, brain_store, growth_store, task_history
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

    def _seed_analytics(self):
        # A retained analytics goal needs an existing dataset at Owner preflight.
        # Create only isolated fixture metadata; no real Owner dataset is touched.
        with closing(analytics_store._connect(self.analytics, create=True)) as conn, conn:
            conn.execute("INSERT INTO datasets VALUES (?,?)", ("demo-test", 1))

    def campaign(self):
        # Historical goal concurrency fixtures use an isolated Growth record.
        # Campaign creation is no longer an Owner API capability.
        created = growth_store.create_campaign({
            "campaign": "nem-pilot", "title": "Tư vấn nệm",
            "analytics_dataset": "", "budget_vnd": 50000,
            "synthetic": False,
        }, confirm_write=True, db_path=self.growth, analytics_db_path=self.analytics)
        return 200, created, {}

    def test_react_dashboard_is_canonical_and_api_requires_session(self):
        code, _, headers = self.req("GET", "/")
        self.assertEqual(code, 302)
        self.assertEqual(headers["Location"], "/dashboard/")
        self.assertEqual(headers["Cache-Control"], "no-store")
        for path in ("/app.js", "/app.css", "/app.html"):
            code, _, _ = self.req("GET", path)
            self.assertEqual(code, 404)
        code, _, _ = self.req("GET", "/api/bootstrap")
        self.assertEqual(code, 401)
        code, _, _ = self.req("GET", "/api/goals/" + "a" * 32)
        self.assertEqual(code, 401)
        self.assertFalse(self.brain.exists())

    def test_authenticated_operations_health_is_read_only(self):
        code, payload, _ = self.req("GET", "/api/ops/health")
        self.assertEqual(code, 401)
        self.login()
        code, result, _ = self.req("GET", "/api/ops/health")
        self.assertEqual(code, 200)
        self.assertIn(result["status"], {"PASS", "REVIEW_REQUIRED"})
        self.assertTrue(result["local_only"])
        self.assertFalse(result["automatic_recovery_performed"])
        self.assertFalse(result["external_accounts_connected"])
        self.assertFalse(result["verified_revenue"])
        self.assertFalse(self.brain.exists())
        code, _, _ = self.req("GET", "/api/ops/health", host="evil.invalid")
        self.assertEqual(code, 403)
        code, _, _ = self.req("POST", "/api/ops/health", {})
        self.assertEqual(code, 400)

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
        self.assertEqual(payload["stats"]["skills"], 23)
        self.assertFalse(payload["external_actions_enabled"])
        self.assertEqual(len(payload["connectors"]), 2)
        self.assertFalse(payload["connectors"][0]["authenticated"])
        self.assertNotIn(CODE, json.dumps(payload))
        code, out, headers = self.req("POST", "/api/logout", {})
        self.assertEqual(code, 200)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        code, _, _ = self.req("GET", "/api/bootstrap")
        self.assertEqual(code, 401)

    def test_model_probe_requires_owner_csrf_external_mode_and_exact_revision(self):
        from agentforge.ai import model_hub
        from agentforge.ops import runtime_certification

        path = "/api/model-hub/probe"
        body = {"ack": "RUN_LOCAL_MODEL_PROBE", "profile_id": "local_primary",
                "expected_revision": 0}
        with (patch.object(model_hub, "DB_PATH", self.root / "model-hub.sqlite3"),
              patch.object(runtime_certification, "_ollama_inference",
                           return_value={"status": "PASS_RUNTIME", "inference_invoked": True}) as inference):
            self.assertEqual(self.req("POST", path, body)[0], 401)
            self.login()
            self.assertEqual(self.req("POST", path, body)[0], 400)
            self.server.allow_external_actions = True
            self.assertEqual(self.req("POST", path, body, csrf=False)[0], 403)
            self.assertEqual(self.req("POST", path, {**body, "ack": "CHECK"})[0], 400)
            self.assertIn(self.req("POST", path, {**body, "expected_revision": 1})[0], (400, 409))
            self.assertEqual(self.req("POST", path, {**body, "profile_id": "cloud_primary"})[0], 400)
            inference.assert_not_called()
            status, receipt, _ = self.req("POST", path, body)
            self.assertEqual((status, receipt["status"]), (200, "PASS_RUNTIME"), receipt)
            self.assertEqual(receipt["revision"], 0)
            self.assertIn("checked_at", receipt)
            inference.assert_called_once()

    def test_retired_workspace_intake_does_not_write_or_invoke_model(self):
        self.login()
        brief = "Tạo website " + "viết nội dung tiếng Việt " * 125
        with patch("agentforge.model.generate_json") as model:
            code, _, _ = self.req("POST", "/api/workspace/request", {
                "ack": "PLAN_ONLY", "prompt": brief, "max_model_calls": 1})
            self.assertEqual(code, 400)
            model.assert_not_called()
        self.assertFalse(self.brain.exists())
        self.assertFalse(self.taskdb.exists())

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

    def test_retired_growth_plan_cannot_dispatch_and_active_sha_gate_survives(self):
        self.login()
        from agentforge import brain_planner
        with self.assertRaises(PermissionError):
            brain_planner.propose("Retired growth", "growth.review",
                                  {"campaign": "archived"}, db_path=self.brain)
        self.assertFalse(self.brain.exists())
        self._seed_analytics()
        goal = brain_planner.propose(
            "Review local analytics", "campaign.review",
            {"dataset": "demo-test"}, db_path=self.brain)
        path = "/api/goals/" + goal["goal_id"]
        self.assertEqual(self.req("POST", path + "/approve", {
            "ack": "APPROVE", "plan_sha256": "0"*64})[0], 400)
        code, detail, _ = self.req("GET", path)
        self.assertEqual(code, 200)
        self.assertEqual(detail["plan_sha256"], goal["plan_sha256"])
        self.assertEqual(self.req("POST", path + "/approve", {
            "ack": "APPROVE", "plan_sha256": goal["plan_sha256"]})[0], 200)
        self.assertFalse(self.taskdb.exists())

    def test_retired_media_v15_goal_cannot_start_even_with_extra_grants(self):
        self.login()
        self.server.allow_external_actions = True
        request = {"ack": "PROPOSE", "title": "Retired media workflow",
                   "template": "media.produce", "inputs": {
                       "slug": "old-video", "title": "Old media",
                       "scenes": []}, "max_external_runs": 1}
        with patch("agentforge.media_assets.make_assets") as compose, \
             patch("agentforge.media_render.render_video") as render:
            status, _, _ = self.req("POST", "/api/goals/propose", request)
            self.assertEqual(status, 400)
            compose.assert_not_called()
            render.assert_not_called()
        self.assertFalse(self.brain.exists())
        self.assertFalse(self.taskdb.exists())

    def test_concurrent_initial_run_creates_only_one_parent(self):
        self.login()
        self._seed_analytics()
        goal = brain_planner.propose(
            "Review local analytics", "campaign.review",
            {"dataset": "demo-test"}, db_path=self.brain)
        path = "/api/goals/" + goal["goal_id"]
        approval = {"plan_sha256": goal["plan_sha256"]}
        self.assertEqual(self.req("POST", path + "/approve", {**approval, "ack": "APPROVE"})[0], 200)
        barrier = threading.Barrier(2)
        change_state = brain_store.change_state

        def synchronized_claim(*args, **kwargs):
            if kwargs.get("expected") == "APPROVED":
                barrier.wait(4)
            return change_state(*args, **kwargs)

        with patch.object(brain_store, "change_state", side_effect=synchronized_claim):
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(self.req, "POST", path + "/run", {**approval, "ack": "RUN"})
                        for _ in range(2)]
                self.assertEqual(sorted(job.result()[0] for job in jobs), [200, 400])
        parents = [row for row in task_history.list_tasks(db_path=self.taskdb)
                   if row["kind"] == "workflow"]
        self.assertEqual(len(parents), 1)
        self.assertIn(parents[0]["status"], {"SUCCEEDED", "FAILED"})
        self.assertEqual(self.req("GET", path)[1]["parent_task_id"], parents[0]["task_id"])

    def test_task_database_start_failure_interrupts_goal(self):
        self.login()
        self._seed_analytics()
        goal = brain_planner.propose(
            "Review local analytics", "campaign.review",
            {"dataset": "demo-test"}, db_path=self.brain)
        path = "/api/goals/" + goal["goal_id"]
        approval = {"plan_sha256": goal["plan_sha256"]}
        self.assertEqual(self.req("POST", path + "/approve", {**approval, "ack": "APPROVE"})[0], 200)
        with patch.object(task_history, "create_task", side_effect=OSError("disk unavailable")):
            self.assertEqual(self.req("POST", path + "/run", {**approval, "ack": "RUN"})[0], 400)
        self.assertEqual(self.req("GET", path)[1]["status"], "INTERRUPTED")
        self.assertEqual(self.req("POST", path + "/run", {**approval, "ack": "RUN"})[0], 400)
        self.assertFalse(self.taskdb.exists())

    def test_removed_workspace_intake_cannot_create_resumable_goal(self):
        self.login()
        self.server.allow_external_actions = True
        code, _, _ = self.req("POST", "/api/workspace/request", {
            "ack": "PLAN_ONLY", "prompt": "Tạo storyboard", "max_model_calls": 1})
        self.assertEqual(code, 400)
        self.assertFalse(self.brain.exists())

    def test_dashboard_read_routes_return_authenticated_json(self):
        self.login()
        for path, shape in (
            ("/api/visuals/jobs", dict), ("/api/ops/health", dict), ("/api/memory", list),
        ):
            with self.subTest(path=path):
                code, output, _ = self.req("GET", path)
                self.assertEqual(code, 200)
                self.assertIsInstance(output, shape)

    def test_non_ascii_auth_inputs_are_rejected_cleanly(self):
        self.assertEqual(self.req("POST", "/api/login", {"code": "mã sai"})[0], 401)
        self.login()
        self.csrf = "é"
        self.assertEqual(self.req("POST", "/api/logout")[0], 403)

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

    def test_retired_campaign_event_api_fails_closed_without_storing_pii(self):
        self.login()
        with patch("agentforge.growth_store.record_event") as record:
            for payload in (
                {"ack": "RECORD_EVENT", "kind": "lead_new",
                 "data": {"campaign": "nem-pilot", "channel": "website",
                          "consent_confirmed": True, "phone": "+84123456789"}},
                {"ack": "RECORD_EVENT", "kind": "lead_new",
                 "data": {"campaign": "nem-pilot", "channel": "website",
                          "consent_confirmed": True}},
            ):
                self.assertEqual(self.req("POST", "/api/campaigns/event", payload)[0], 400)
            record.assert_not_called()
        self.assertFalse(self.growth.exists())
        self.assertFalse(self.taskdb.exists())
        status, data, _ = self.req("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertNotIn("growth", data)
        self.assertNotIn("lead_id", json.dumps(data))

    def test_schedule_readonly_api_and_standing_sha(self):
        self.login()
        due=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        created = brain_scheduler.create_schedule(
            "Periodic local analytics review", "campaign.review",
            {"dataset": "demo-test"}, due, 60,
            confirm_schedule=True, db_path=self.brain)
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

    def test_retired_website_proposal_is_not_exposed_or_applied(self):
        self.login()
        ident = "b" * 32
        with patch("agentforge.product_builder.apply") as apply:
            self.assertEqual(self.req("GET", "/api/proposals/" + ident)[0], 404)
            self.assertEqual(self.req("POST", "/api/proposals/" + ident + "/apply",
                                      {"ack": "APPLY_PROPOSAL", "sha256": "c"*64})[0], 400)
            apply.assert_not_called()

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
