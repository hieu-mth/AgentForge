"""Model Hub keeps only configured video capabilities and inert historical DB keys."""
import tempfile
import unittest
from pathlib import Path
from agentforge.ai import model_hub


class ModelHubTests(unittest.TestCase):
    def test_default_routes_are_video_first(self):
        routes = model_hub._defaults()
        self.assertEqual(set(routes), {
            "general.text", "film.storyboard", "film.motion",
            "image.generate", "ops.monitor"})
        self.assertTrue(all("worker" not in item for item in routes.values()))
        self.assertTrue(all(item["execution"] != "wired" for item in routes.values()))
        self.assertEqual(routes["film.motion"]["kind"], "video")

    def test_read_only_catalog_does_not_create_owner_sqlite(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "model_hub.sqlite3"
            result = model_hub.catalog(db_path=db)
            self.assertEqual(result["revision"], 0)
            self.assertFalse(db.exists())
            self.assertEqual({r["id"] for r in result["routes"]}, set(model_hub._defaults()))
            self.assertFalse(result["cloud_fallback"])
            self.assertTrue(all("runtime_wired" not in row for row in result["routes"]))

    def test_unknown_historical_route_is_inert_and_not_auto_migrated(self):
        model_hub._validate_state({
            "profiles": {}, "routes": {"retired.legacy_route": "local_primary"}})
        with self.assertRaises(model_hub.ModelConfigError):
            model_hub._validate_state({
                "profiles": {}, "routes": {"ops.monitor": "local_primary"}})

    def test_only_loopback_provider_urls_allowed(self):
        for url in ("https://example.com:11434", "http://192.168.1.2:11434",
                    "http://127.0.0.1:11434/private", "http://evil@127.0.0.1:11434"):
            with self.subTest(url=url), self.assertRaises(model_hub.ModelConfigError):
                model_hub._local_url(url)
        self.assertEqual(model_hub._local_url("http://127.0.0.1:11434"),
                         "http://127.0.0.1:11434")


if __name__ == "__main__":
    unittest.main()
