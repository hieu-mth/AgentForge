"""V2.9 root invariants and stable registry import contracts."""
import unittest
from pathlib import Path
from agentforge import paths
from agentforge import model_registry, worker_registry
from agentforge.ai import model_registry as model_ai, worker_registry as worker_ai

class PathAndRegistryTests(unittest.TestCase):
    def test_root_points_to_real_source_tree(self):
        root = paths.REPOSITORY_ROOT
        self.assertTrue((root / "pyproject.toml").is_file())
        self.assertEqual(root / "data", paths.DATA_DIR)
        self.assertEqual(root / "workspace", paths.WORKSPACE_DIR)
        self.assertEqual(root / "ui" / "dashboard", paths.UI_DASHBOARD_DIR)
        self.assertEqual(model_ai.ROOT, root)
        self.assertEqual(worker_ai.ROOT, root)

    def test_legacy_imports_keep_callable_and_types(self):
        self.assertIs(model_registry.load_models, model_ai.load_models)
        self.assertIs(worker_registry.load_worker, worker_ai.load_worker)
        self.assertIs(model_registry.ModelConfigError, model_ai.ModelConfigError)
        self.assertIs(worker_registry.WorkerConfigError, worker_ai.WorkerConfigError)
        self.assertEqual(model_ai.load_models()["local_primary"]["model"], "qwen3:8b")
        self.assertEqual(worker_ai.load_worker("opportunity_researcher")["runtime"], "langgraph")

    def test_symlink_refusal(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp) / "real"
            real.mkdir()
            link = Path(temp) / "alias"
            try: link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError): self.skipTest("No symlink privileges")
            with self.assertRaises(PermissionError):
                paths.ensure_local_root(link / "data" / "project.db")

if __name__ == "__main__":
    unittest.main()
