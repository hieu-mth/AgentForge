"""Independent checks: no reachable historical business module or skill engine."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED = (
    "agentforge.core", "agentforge.features.websites",
    "agentforge.features.webapps", "agentforge.features.growth",
    "agentforge.ops_backup", "agentforge.model",
    "agentforge.brain_planner", "agentforge.skill_registry",
    "agentforge.analytics_store", "agentforge.media_assets",
)


class VideoBoundaryTests(unittest.TestCase):
    def test_retired_packages_and_registry_are_absent(self):
        for path in ("skills", "workers", "sandbox/webapp", "agentforge/core",
                     "agentforge/features/websites", "agentforge/features/webapps",
                     "agentforge/features/growth", "config/opportunities.json"):
            with self.subTest(path=path):
                self.assertFalse((ROOT / path).exists())

    def test_every_runtime_python_module_is_parseable_and_imports_no_retired_code(self):
        for path in sorted((ROOT / "agentforge").rglob("*.py")):
            with self.subTest(module=path.relative_to(ROOT).as_posix()):
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        names = [node.module or ""]
                    else:
                        continue
                    for name in names:
                        self.assertFalse(any(name == banned or name.startswith(banned+".")
                                             for banned in RETIRED), name)

    def test_only_film_model_and_operations_routes_remain(self):
        text = (ROOT / "config/task_routes.toml").read_text(encoding="utf-8")
        self.assertIn('[routes."film.motion"]', text)
        self.assertNotIn('[routes."growth.report"]', text)


if __name__ == "__main__":
    unittest.main()
