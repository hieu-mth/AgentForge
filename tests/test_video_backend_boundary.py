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
                     "agentforge/features/growth", "config"):
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

    def test_active_capabilities_live_in_source_not_config_files(self):
        from agentforge.ai.model_hub import route_catalog
        routes = route_catalog()
        self.assertIn("film.motion", routes)
        self.assertNotIn("growth.report", routes)
        self.assertFalse((ROOT / "config").exists())
        self.assertFalse((ROOT / "agentforge/ai/model_registry.py").exists())


if __name__ == "__main__":
    unittest.main()
