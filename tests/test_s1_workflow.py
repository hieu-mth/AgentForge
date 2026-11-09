"""S1 end-to-end website audit and source checkpoint tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import product_builder, task_history, workflow_runner


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
        self.assertTrue(any(t["skill_id"] == "web.quality_check"
                            and t["status"] == "SUCCEEDED" for t in children))

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




if __name__ == "__main__":
    unittest.main()
