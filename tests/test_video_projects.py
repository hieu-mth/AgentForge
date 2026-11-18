import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from agentforge.video_projects import list_projects


class VideoProjectTests(unittest.TestCase):
    def test_film_studio_only(self):
        with TemporaryDirectory() as tmp, patch(
            "agentforge.features.film_studio.production.list_episodes",
            return_value=[{"film_slug":"cats","episode_id":"ep1","state":"PREPARED_NOT_RENDERED"}],
        ) as listing:
            result=list_projects(film_root=Path(tmp))
        listing.assert_called_once()
        self.assertEqual(result["projects"][0]["project_id"],"film:cats:ep1")
        self.assertEqual(result["canonical_engine"],"film_studio")
        self.assertFalse(result["auto_publish"])

    def test_empty_and_bounded(self):
        with patch("agentforge.features.film_studio.production.list_episodes",return_value=[]):
            self.assertEqual(list_projects()["projects"],[])
        for value in (0,31,True,"10"):
            with self.assertRaises(ValueError):
                list_projects(limit=value)
