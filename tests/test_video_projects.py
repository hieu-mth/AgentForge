"""Video Studio unified read projection; no media generation required."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import video_projects


class VideoProjectTests(unittest.TestCase):
    def test_read_only_projection_and_distinct_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("agentforge.features.film_studio.production.list_episodes",
                       return_value=[{"film_slug": "cats", "episode_id": "ep1",
                                      "state": "PREPARED_NOT_RENDERED"}]):
                result = video_projects.list_projects(
                    film_root=Path(temp), legacy_db_path=Path(temp) / "missing.db")
        self.assertEqual(result["canonical_engine"], "film_studio")
        self.assertEqual(result["projects"][0]["project_id"], "film:cats:ep1")
        self.assertFalse(result["projects"][0]["legacy_read_only"])
        self.assertFalse(result["runtime_certified"])

    def test_legacy_records_are_visible_but_read_only(self):
        with patch("agentforge.features.film_studio.production.list_episodes", return_value=[]), \
             patch("agentforge.features.media.workflow.report",
                   return_value={"productions": [{"production_id": "abc", "status": "APPROVED"}]}):
            result = video_projects.list_projects()
        self.assertEqual(result["projects"][0]["project_id"], "legacy:abc")
        self.assertTrue(result["projects"][0]["legacy_read_only"])
        self.assertFalse(result["auto_publish"])

    def test_limit_is_bounded(self):
        for value in (0, 31, True, "10"):
            with self.assertRaises(ValueError):
                video_projects.list_projects(limit=value)


if __name__ == "__main__":
    unittest.main()
