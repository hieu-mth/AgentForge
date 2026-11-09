"""M4d1: media and film features preserve safe import, data and CLI contracts."""
import importlib
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import architecture, paths


MAP = {
    "assets": "media",
    "quality": "media",
    "render": "media",
    "workflow": "media",
    "long_form": "film_studio",
    "motion_comfy": "film_studio",
}


class MediaFilmFeatureMigrationTests(unittest.TestCase):
    def test_old_domain_aliases_resolve_exact_canonical_object(self):
        for name, group in MAP.items():
            with self.subTest(name=name):
                feature = importlib.import_module("agentforge.features." + group + "." + name)
                old = importlib.import_module("agentforge.domains.media." + name)
                self.assertIs(feature, old)
                self.assertIn("/features/" + group + "/", feature.__file__.replace("\\", "/"))

    def test_root_media_aliases_and_persistent_paths(self):
        names = {"agentforge.media_assets": "assets",
                 "agentforge.media_quality": "quality",
                 "agentforge.media_render": "render",
                 "agentforge.media_workflow_v15": "workflow"}
        for old, canonical in names.items():
            with self.subTest(name=old):
                self.assertIs(importlib.import_module(old),
                              importlib.import_module("agentforge.features.media." + canonical))
                self.assertEqual(architecture.BUSINESS_DOMAIN_IMPORTS[old],
                                 "agentforge.features.media." + canonical)
        assets = importlib.import_module("agentforge.features.media.assets")
        motion = importlib.import_module("agentforge.features.film_studio.motion_comfy")
        self.assertEqual(paths.WORKSPACE_DIR / "media", assets.OUTPUTS)
        self.assertEqual(paths.DATA_DIR / "film_studio" / "motion.sqlite3", motion.DB)
        self.assertEqual(paths.WORKSPACE_DIR / "films", motion.FILMS)
        self.assertEqual("agentforge/features/media", architecture.LAYOUT["media_feature"])
        self.assertEqual("agentforge/features/film_studio",
                         architecture.LAYOUT["film_studio_feature"])

    def test_existing_motion_http_mock_point_is_preserved(self):
        old = importlib.import_module("agentforge.domains.media.motion_comfy")
        new = importlib.import_module("agentforge.features.film_studio.motion_comfy")
        with patch.object(old, "_json_request", return_value={"devices": []}) as request:
            self.assertEqual(new.health()["status"], "GPU_NOT_DETECTED")
            request.assert_called_once_with("/system_stats")

    def test_feature_modules_never_import_old_media_domain(self):
        for group in ("media", "film_studio"):
            root = paths.REPOSITORY_ROOT / "agentforge" / "features" / group
            for source in root.glob("*.py"):
                self.assertNotIn("agentforge.domains.media",
                                 source.read_text(encoding="utf-8"))

    def test_legacy_cli_help_is_read_only(self):
        for name in ("long_form", "motion_comfy", "workflow"):
            with self.subTest(name=name):
                result = subprocess.run(
                    [sys.executable, "-m", "agentforge.domains.media." + name, "--help"],
                    cwd=paths.REPOSITORY_ROOT, capture_output=True, text=True, timeout=20)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
