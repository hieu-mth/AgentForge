"""S1 end-to-end website audit, source checkpoint and local dashboard tests."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import dashboard_v0, product_builder, task_history, workflow_runner


SITE = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Tư vấn nệm</title><style>@media(max-width:600px){body{margin:0}}</style>'
        '</head><body><h1>Nệm phù hợp</h1><section id="lien-he">'
        '<h2>Liên hệ tư vấn</h2></section></body></html>')


class TestS1WorkflowDashboard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "s1_tasks.sqlite3"
        self.products = self.root / "workspace" / "products"
        self.source = self.products / "nem-tu-van" / "index.html"
        self.source.parent.mkdir(parents=True)
        self.source.write_text(SITE, encoding="utf-8")
        self.patches = [
            patch.object(product_builder, "ROOT", self.root),
            patch.object(product_builder, "WORKSPACE", self.root / "workspace"),
            patch.object(product_builder, "PRODUCTS", self.products),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_e2e_without_browser_cost_or_model(self):
        with patch("agentforge.model.generate") as model:
            workflow = workflow_runner.run_web_audit("nem-tu-van", db_path=self.db)
            model.assert_not_called()
        self.assertEqual(workflow["status"], "SUCCEEDED")
        self.assertEqual(workflow["quality"]["result"]["status"], "PASS")
        parent = task_history.get_task(workflow["task_id"], db_path=self.db)
        self.assertEqual(parent["status"], "SUCCEEDED")
        self.assertIn("QUALITY_DONE", [e["name"] for e in parent["events"]])
        children = task_history.list_tasks(db_path=self.db)
        self.assertEqual(len(children), 2)
        self.assertEqual(sum(t["parent_id"] == parent["task_id"] for t in children), 1)
        rendered = dashboard_v0.render_dashboard(db_path=self.db)
        self.assertIn("AgentForge Control Center", rendered)
        self.assertIn("web.quality_check", rendered)
        self.assertIn("SUCCEEDED", rendered)

    def test_optional_browser_approval_resume_no_recheck(self):
        with patch("agentforge.browser_validation.validate") as browser:
            workflow = workflow_runner.run_web_audit(
                "nem-tu-van", include_browser=True, db_path=self.db)
            browser.assert_not_called()
        self.assertEqual(workflow["status"], "WAITING_APPROVAL")
        self.assertIn("browser.run", workflow["missing"])
        self.assertEqual(len(task_history.list_tasks(db_path=self.db)), 2)
        with patch("agentforge.browser_validation.validate", return_value={
            "run_id": "a" * 32, "status": "PASS", "report_path": "local-report",
        }) as browser:
            resumed = workflow_runner.run_web_audit(
                task_id=workflow["task_id"], db_path=self.db,
                grants=("browser.run",), confirm_browser_run=True)
            browser.assert_called_once()
        self.assertEqual(resumed["status"], "SUCCEEDED")
        tasks = task_history.list_tasks(db_path=self.db)
        self.assertEqual(len(tasks), 3)  # parent, quality, browser
        parent = task_history.get_task(workflow["task_id"], db_path=self.db)
        self.assertEqual([e["name"] for e in parent["events"]],
                         ["CREATED", "RUNNING", "QUALITY_DONE", "WAITING_APPROVAL",
                          "RUNNING", "BROWSER_DONE", "SUCCEEDED"])
        with self.assertRaises(ValueError):
            workflow_runner.run_web_audit(task_id=workflow["task_id"], db_path=self.db)

    def test_changed_site_blocks_resume_without_browser(self):
        workflow = workflow_runner.run_web_audit(
            "nem-tu-van", include_browser=True, db_path=self.db)
        self.source.write_text(SITE.replace("Nệm phù hợp", "Một mẫu nệm khác"),
                               encoding="utf-8")
        with patch("agentforge.browser_validation.validate") as browser:
            result = workflow_runner.run_web_audit(
                task_id=workflow["task_id"], grants=("browser.run",),
                confirm_browser_run=True, db_path=self.db)
            browser.assert_not_called()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(task_history.get_task(workflow["task_id"], db_path=self.db)["status"],
                         "FAILED")

    def test_quality_fail_blocks_browser(self):
        self.source.write_text(SITE.replace(
            '<h1>Nệm phù hợp</h1>',
            '<button onclick="alert(1)">Bad</button><h1>Nệm phù hợp</h1>'),
            encoding="utf-8")
        with patch("agentforge.browser_validation.validate") as browser:
            result = workflow_runner.run_web_audit(
                "nem-tu-van", include_browser=True,
                grants=("browser.run",), confirm_browser_run=True,
                db_path=self.db)
            browser.assert_not_called()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["quality"]["result"]["status"], "FAIL")

    def test_dashboard_http_loopback_is_read_only(self):
        workflow_runner.run_web_audit("nem-tu-van", db_path=self.db)
        server = dashboard_v0.create_server(0, db_path=self.db)
        self.assertEqual(server.server_address[0], "127.0.0.1")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("GET", "/api/tasks")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            tasks = json.loads(response.read())
            self.assertEqual(len(tasks), 2)
            self.assertTrue(all("request" not in task for task in tasks))
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            conn.close()

            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("GET", "/api/skills")
            self.assertEqual(len(json.loads(conn.getresponse().read())), 11)
            conn.close()

            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("POST", "/api/tasks", body="{}")
            response = conn.getresponse()
            self.assertEqual(response.status, 405)
            response.read()
            conn.close()

            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("GET", "/api/skills", headers={"Host": "evil.invalid"})
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)

    def test_dashboard_escapes_html_and_exposes_no_prompt(self):
        task_id = task_history.create_task(
            "skill", "web.create",
            {"brief": "<img src=x onerror=alert(1)>", "slug": "nem-tu-van"},
            db_path=self.db)
        result = dashboard_v0.render_dashboard(db_path=self.db, selected=task_id)
        self.assertNotIn("<img src=x onerror=", result)
        self.assertNotIn("alert(1)", result)
        self.assertIn("web.create", result)
        self.assertIn("product_builder", result)
        self.assertIn("CREATED", result)

    def test_dashboard_only_renders_artifact_basename(self):
        task_id = task_history.create_task(
            "skill", "web.create", {"slug": "nem-tu-van"},
            db_path=self.db)
        task_history.transition(task_id, "RUNNING", db_path=self.db)
        task_history.transition(task_id, "SUCCEEDED", result={
            "proposal_path": r"D:\Private\Customer\proposal.json",
        }, db_path=self.db)
        result = dashboard_v0.render_dashboard(db_path=self.db, selected=task_id)
        self.assertIn("proposal.json", result)
        self.assertNotIn("D:\\Private", result)
        self.assertNotIn("Customer", result)


if __name__ == "__main__":
    unittest.main()
