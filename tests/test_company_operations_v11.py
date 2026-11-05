"""Company Operations V1.1: real localhost HTTP preflight and safe reports."""
import http.client
import json
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from agentforge import analytics_store, goal_preflight, result_view, task_history
from agentforge import control_center_v1 as cc

CODE = "testing-owner-company-ops-2026"


class TestCompanyOperationsV11(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.task_db = root / "tasks.sqlite3"
        self.brain_db = root / "brain.sqlite3"
        self.analytics_db = root / "analytics.sqlite3"
        self.growth_db = root / "growth.sqlite3"
        self.server = cc.create_server(
            0, owner_code=CODE, task_db_path=self.task_db,
            brain_db_path=self.brain_db, analytics_db_path=self.analytics_db,
            growth_db_path=self.growth_db)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = "127.0.0.1:" + str(self.server.server_port)
        self.cookie = None
        self.csrf = None

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.tmp.cleanup()

    def req(self, method, route, data=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=8)
        headers = {"Host": self.host}
        if method == "POST":
            headers.update({"Origin": "http://" + self.host,
                            "Content-Type": "application/json"})
        if self.cookie:
            headers["Cookie"] = self.cookie
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        conn.request(method, route, body=json.dumps(data) if data is not None else None,
                     headers=headers)
        reply = conn.getresponse()
        code = reply.status
        cookies = reply.getheader("Set-Cookie")
        body = reply.read()
        conn.close()
        return code, json.loads(body), cookies

    def login(self):
        code, response, cookie = self.req("POST", "/api/login", {"code": CODE})
        self.assertEqual(code, 200)
        self.csrf = response["csrf"]
        self.cookie = cookie.split(";", 1)[0]

    def dataset(self, identifier="demo-valid-001"):
        with closing(analytics_store._connect(self.analytics_db, create=True)) as db, db:
            db.execute("INSERT INTO datasets(dataset,synthetic) VALUES (?,1)",
                       (identifier,))
        return identifier

    def propose(self, dataset):
        return self.req("POST", "/api/goals/propose", {
            "ack": "PROPOSE", "title": "Review data", "template": "campaign.review",
            "inputs": {"dataset": dataset}, "max_model_calls": 0,
            "max_external_runs": 0})

    def test_preflight_requires_session_csrf_and_does_not_create_database(self):
        code, _, _ = self.req("POST", "/api/goals/preflight", {
            "ack": "PREFLIGHT", "template": "campaign.review",
            "inputs": {"dataset": "demo-bogus"}})
        self.assertEqual(code, 401)
        self.login()
        code, out, _ = self.req("POST", "/api/goals/preflight", {
            "ack": "PREFLIGHT", "template": "campaign.review",
            "inputs": {"dataset": "demo-bogus"}})
        self.assertEqual(code, 200)
        self.assertFalse(out["ready"])
        self.assertEqual(out["issues"][0]["code"], "DATASET_NOT_FOUND")
        self.assertFalse(self.analytics_db.exists())
        self.assertFalse(self.brain_db.exists())
        code, out, _ = self.propose("demo-bogus")
        self.assertEqual(code, 400)
        self.assertIn("DATASET_NOT_FOUND", out["message"])
        self.assertFalse(self.brain_db.exists())

    def test_valid_dataset_can_be_planned_and_missing_dataset_blocks_approval(self):
        self.dataset()
        self.login()
        code, ready, _ = self.req("POST", "/api/goals/preflight", {
            "ack": "PREFLIGHT", "template": "campaign.review",
            "inputs": {"dataset": "demo-valid-001"}})
        self.assertEqual(code, 200)
        self.assertTrue(ready["ready"])
        code, proposed, _ = self.propose("demo-valid-001")
        self.assertEqual(code, 200)
        self.assertEqual(proposed["status"], "PLANNED")
        with closing(analytics_store._connect(self.analytics_db)) as db, db:
            db.execute("DELETE FROM datasets WHERE dataset='demo-valid-001'")
        code, blocked, _ = self.req(
            "POST", "/api/goals/" + proposed["goal_id"] + "/approve",
            {"ack": "APPROVE", "plan_sha256": proposed["plan_sha256"]})
        self.assertEqual(code, 400)
        self.assertIn("DATASET_NOT_FOUND", blocked["message"])
        code, detail, _ = self.req("GET", "/api/goals/" + proposed["goal_id"])
        self.assertEqual(code, 200)
        self.assertEqual(detail["status"], "PLANNED")
        self.assertFalse(self.task_db.exists())

    def test_dataset_lost_after_approval_cannot_launch_failed_child_tasks(self):
        self.dataset()
        self.login()
        code, proposed, _ = self.propose("demo-valid-001")
        self.assertEqual(code, 200)
        code, _, _ = self.req(
            "POST", "/api/goals/" + proposed["goal_id"] + "/approve",
            {"ack": "APPROVE", "plan_sha256": proposed["plan_sha256"]})
        self.assertEqual(code, 200)
        with closing(analytics_store._connect(self.analytics_db)) as db, db:
            db.execute("DELETE FROM datasets")
        code, blocked, _ = self.req(
            "POST", "/api/goals/" + proposed["goal_id"] + "/run",
            {"ack": "RUN", "plan_sha256": proposed["plan_sha256"], "grants": []})
        self.assertEqual(code, 400)
        self.assertIn("DATASET_NOT_FOUND", blocked["message"])
        self.assertFalse(self.task_db.exists())

    def test_unknown_growth_campaign_blocked_without_mutation(self):
        self.login()
        code, result, _ = self.req("POST", "/api/goals/preflight", {
            "ack": "PREFLIGHT", "template": "growth.review",
            "inputs": {"campaign": "missing-campaign"}})
        self.assertEqual(code, 200)
        self.assertEqual(result["issues"][0]["code"], "CAMPAIGN_NOT_FOUND")
        self.assertFalse(self.growth_db.exists())
        self.assertFalse(self.brain_db.exists())

    def test_only_curated_analytics_result_reaches_task_api(self):
        self.login()
        tid = task_history.create_task(
            "skill", "analytics.content_report", {"dataset": "demo-valid-001"},
            db_path=self.task_db)
        task_history.transition(tid, "RUNNING", db_path=self.task_db)
        task_history.transition(tid, "SUCCEEDED", result={
            "status": "ANALYZED_WITH_UNCERTAINTY",
            "dataset": "demo-valid-001", "synthetic": True,
            "metrics": {"views": 120, "clicks": 9, "unknown_secret": "do-not-show"},
            "by_channel": {"youtube": {"views": 120, "clicks": 9,
                                       "token": "hidden"}},
            "diagnostics": ["CTR is low."],
            "sources": {"source_count": 2,
                        "source_files": [{"filename": "C:/PRIVATE/contact-list.csv"}]},
            "customer_email": "private@example.com", "prompt": "confidential"
        }, db_path=self.task_db)
        code, output, _ = self.req("GET", "/api/tasks/" + tid)
        self.assertEqual(code, 200)
        self.assertNotIn("request", output)
        self.assertNotIn("result", output)
        self.assertEqual(output["report"]["metrics"]["views"], 120)
        self.assertTrue(output["report"]["fields"]["synthetic"])
        self.assertEqual(output["report"]["source_count"], 2)
        joined = json.dumps(output)
        for forbidden in ("private@example.com", "contact-list.csv",
                          "do-not-show", "confidential", "hidden"):
            self.assertNotIn(forbidden, joined)
        self.assertFalse(output["report"]["business_verified"])

    def test_report_projection_never_falls_back_to_arbitrary_model_output(self):
        self.assertIsNone(result_view.present("web.create", {
            "prompt": "secret", "model_output": "private"}))
        self.assertIsNone(result_view.present("analytics.content_report", "text"))
        view = result_view.present("analytics.finance_report", {
            "status": "OWNER_RECORDED_NOT_VERIFIED",
            "synthetic": False, "verified_net_profit_vnd": None,
            "owner_recorded_net_cash_vnd": 95000,
            "uncertainty": ["Owner-recorded, not bank verified."]
        })
        self.assertEqual(view["fields"]["owner_recorded_net_cash_vnd"], 95000)
        self.assertIsNone(view["fields"]["verified_net_profit_vnd"])
        self.assertFalse(view["business_verified"])


if __name__ == "__main__":
    unittest.main()
