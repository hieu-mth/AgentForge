"""Preflight checks only the current Video Studio source footprint."""
import tempfile
import unittest
from pathlib import Path
from agentforge.ops import preflight


class EnvironmentPreflightTests(unittest.TestCase):
    def test_no_worker_or_skill_registry_requirement(self):
        ids = {item[0] for item in preflight.CHECKS}
        self.assertNotIn("worker_manifests", ids)
        self.assertNotIn("skill_registry", ids)
        self.assertNotIn("model_defaults", ids)
        self.assertNotIn("task_routes", ids)
        self.assertIn("model_hub", ids)
        self.assertIn("policy", ids)

    def test_missing_checkout_is_blocked_without_creating_files(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            result = preflight.inspect(root=root, version=(3, 13, 0), which=lambda name: None)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertFalse(result["installation_performed"])
            self.assertEqual(list(root.iterdir()), [])

    def test_python_too_old_is_blocked(self):
        report = preflight.inspect(version=(3, 12, 0), which=lambda name: None)
        self.assertEqual(next(x for x in report["checks"] if x["id"] == "python")["status"],
                         "BLOCKED")


if __name__ == "__main__":
    unittest.main()
