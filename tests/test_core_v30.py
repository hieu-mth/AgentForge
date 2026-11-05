"""V3.0 Core engine path and module monkeypatch compatibility."""
import importlib
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import paths

MOVED = ("brain_store", "task_history", "skill_registry",
         "skill_runner", "brain_planner", "brain_runner")

class CoreCompatibilityTests(unittest.TestCase):
    def test_legacy_core_is_same_module_object_as_canonical(self):
        for name in MOVED:
            with self.subTest(name=name):
                old = importlib.import_module("agentforge." + name)
                new = importlib.import_module("agentforge.core." + name)
                self.assertIs(old, new)
                self.assertEqual(old.__file__, new.__file__)

    def test_core_root_and_databases_are_stable(self):
        from agentforge import brain_store, task_history, skill_registry
        self.assertEqual(paths.REPOSITORY_ROOT, brain_store.ROOT)
        self.assertEqual(paths.REPOSITORY_ROOT, task_history.ROOT)
        self.assertEqual(paths.REPOSITORY_ROOT, skill_registry.ROOT)
        self.assertEqual(paths.COMPANY_DATA_DIR / "s4_brain.sqlite3", brain_store.DB)
        self.assertEqual(paths.COMPANY_DATA_DIR / "s1_tasks.sqlite3",
                         task_history.DEFAULT_DB)
        self.assertTrue((skill_registry.ROOT / "skills").is_dir())

    def test_legacy_module_patches_are_observed_by_core_engine(self):
        from agentforge import skill_runner, brain_store, brain_runner
        import agentforge.core.skill_runner as core_runner
        import agentforge.core.brain_store as core_store
        self.assertIs(skill_runner.invoke, core_runner.invoke)
        with patch.object(skill_runner, "invoke", return_value={"status":"SUCCEEDED"}) as mock:
            self.assertIs(core_runner.invoke, mock)
        with patch.object(brain_store, "DB", Path("synthetic-test.sqlite")):
            self.assertEqual(Path("synthetic-test.sqlite"), core_store.DB)
        self.assertIs(brain_runner.execute, importlib.import_module(
            "agentforge.core.brain_runner").execute)

    def test_planner_and_skill_contracts_remain_bounded(self):
        from agentforge import skill_registry, brain_planner
        registry = skill_registry.load_registry()
        self.assertGreaterEqual(len(registry), 1)
        self.assertIn("website.draft", brain_planner.TEMPLATES)
        self.assertIn("web.create", registry)

if __name__ == "__main__":
    unittest.main()
