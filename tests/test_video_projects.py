import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from agentforge.video_projects import list_projects


class VideoProjectTests(unittest.TestCase):
    def test_film_studio_only(self):
        with TemporaryDirectory() as tmp, patch("agentforge.features.film_studio.draft_pipeline.list_drafts", return_value=[]), patch(
            "agentforge.features.film_studio.production.list_episodes",
            return_value=[{"film_slug":"cats","episode_id":"ep1","state":"PREPARED_NOT_RENDERED"}],
        ) as listing:
            result=list_projects(film_root=Path(tmp))
        listing.assert_called_once()
        self.assertEqual(result["projects"][0]["project_id"],"film:cats:ep1")
        self.assertEqual(result["canonical_engine"],"film_studio")
        self.assertFalse(result["auto_publish"])

    def test_empty_and_bounded(self):
        with (patch("agentforge.features.film_studio.production.list_episodes",return_value=[]),
              patch("agentforge.features.film_studio.draft_pipeline.list_drafts",return_value=[])):
            self.assertEqual(list_projects()["projects"],[])
        for value in (0,31,True,"10"):
            with self.assertRaises(ValueError):
                list_projects(limit=value)

    def test_current_draft_and_manual_episode_share_inventory(self):
        with (patch("agentforge.features.film_studio.production.list_episodes", return_value=[
                  {"film_slug": "cats", "episode_id": "ep1", "state": "PREPARED_NOT_RENDERED"}]),
              patch("agentforge.features.film_studio.draft_pipeline.list_drafts", return_value=[
                  {"id": "a"*32, "status": "APPROVED", "storyboard_version": 2, "board": {"title": "Mèo"}}])):
            result = list_projects()
            self.assertEqual([row["source"] for row in result["projects"]], ["studio_draft", "film_studio"])
            self.assertEqual(result["projects"][0]["film_slug"], "Mèo")
            self.assertEqual(len(list_projects(limit=1)["projects"]), 1)
