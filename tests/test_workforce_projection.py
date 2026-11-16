"""The Dashboard workforce is derived from the existing policy and registries."""
from pathlib import Path
import tempfile
import unittest

from agentforge.ai import workforce
from agentforge.core import brain_planner, skill_registry
from tests import test_control_center_v1


class WorkforceProjectionTests(unittest.TestCase):
    def test_reverse_dependencies_and_no_model_for_local_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "brain.db"
            brain_planner.propose("Workspace report", "filesystem.report",
                                  {"path": "reports/test.md", "content": "test"}, db_path=database)
            report = workforce.inspect(brain_db_path=database, task_db_path=Path(directory) / "tasks.db")
            self.assertFalse((Path(directory) / "tasks.db").exists())
        skills = {skill["id"]: skill for skill in report["skills"]}
        self.assertEqual(set(skills), set(skill_registry.load_registry()))
        skill = skills["filesystem.report"]
        self.assertIsNone(skill["model_ref"])
        self.assertEqual(skill["observed_workflows"], ["filesystem.report"])
        self.assertEqual(skill["adapter_status"], "REGISTERED")
        self.assertIn("filesystem.report", next(t for t in report["tools"] if t["id"] == "filesystem")["skills"])
        self.assertTrue(all("instructions" not in agent for agent in report["agents"]))

    def test_owner_http_only(self):
        test = test_control_center_v1.TestControlCenterV1()
        test.setUp()
        try:
            self.assertEqual(test.req("GET", "/api/workforce", cookie=False)[0], 401)
            test.login()
            code, data, _ = test.req("GET", "/api/workforce")
            self.assertEqual(code, 200)
            self.assertEqual(set(data) & {"agents", "models", "rules", "skills", "tools"},
                             {"agents", "models", "rules", "skills", "tools"})
        finally:
            test.tearDown()
