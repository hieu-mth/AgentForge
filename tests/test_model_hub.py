"""DB-only model profiles, source-owned capabilities and backward compatibility."""
from pathlib import Path
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch

from agentforge.ai import model_hub


class ModelHubTests(unittest.TestCase):
    def test_capability_catalog_is_video_first_without_model_defaults(self):
        routes = model_hub.route_catalog()
        self.assertEqual(set(routes), {
            "general.text", "film.storyboard", "film.motion",
            "image.generate", "ops.monitor"})
        self.assertTrue(all("worker" not in item and
                            "default_model" not in item for item in routes.values()))
        self.assertTrue(all(item["execution"] in {"config_only", "rules"}
                            for item in routes.values()))
        self.assertEqual(routes["film.motion"]["kind"], "video")

    def test_read_only_empty_catalog_does_not_create_owner_sqlite_or_invoke_model(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "model_hub.sqlite3"
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                result = model_hub.catalog(db_path=db)
            self.assertEqual(result["revision"], 0)
            self.assertFalse(db.exists())
            self.assertEqual(result["profiles"], [])
            self.assertEqual(result["orchestrator"]["policy"]["primary"], None)
            self.assertTrue(all(row["model_ref"] is None for row in result["routes"]))
            self.assertEqual(result["routes"][-1]["status"], "DETERMINISTIC")
            self.assertFalse(result["cloud_fallback"])

    def test_adapter_catalog_matches_persisted_profile_validation(self):
        expected = {"ollama": "local", "comfyui": "local", "anthropic": "cloud"}
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "hub.sqlite3"
            catalog = model_hub.catalog(db_path=db)["adapters"]
            self.assertFalse(db.exists())
            self.assertEqual({row["id"]: row["connection"] for row in catalog}, expected)
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                for revision, adapter in enumerate(catalog):
                    profile = {"id": f"owner_{revision}", "provider": adapter["id"],
                               "model": "fixture-model", "enabled": True, **adapter["defaults"]}
                    model_hub.change("SAVE_MODEL_PROFILE", expected_revision=revision,
                                     db_path=db, profile=profile)
                    with self.assertRaises(model_hub.ModelConfigError):
                        model_hub.validate_profile({**profile, "api_key": "secret"})
            self.assertEqual(len(model_hub.catalog(db_path=db)["profiles"]), 3)
            with self.assertRaises(model_hub.ModelConfigError):
                model_hub.validate_profile({**profile, "api_key_env": "Bearer actual-key"})

    def test_registered_model_and_route_exist_only_in_sqlite(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "hub.sqlite3"
            profile = {"id": "studio_local", "provider": "ollama",
                       "model": "example-local:8b", "enabled": True,
                       "base_url": "http://127.0.0.1:11434"}
            saved = model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0,
                                     db_path=db, profile=profile)
            self.assertEqual(saved["revision"], 1)
            self.assertEqual([p["id"] for p in saved["profiles"]], ["studio_local"])
            self.assertEqual(saved["profiles"][0]["source"], "owner")
            route = model_hub.change("SET_MODEL_ROUTE", expected_revision=1,
                                     db_path=db, task_id="general.text",
                                     model_ref="studio_local")
            self.assertEqual(next(r for r in route["routes"] if r["id"] == "general.text")["model_ref"],
                             "studio_local")
            self.assertEqual(route, model_hub.catalog(db_path=db))
            self.assertTrue(db.is_file())
            with closing(sqlite3.connect(db)) as conn:
                record = json.loads(conn.execute("SELECT payload FROM hub_state").fetchone()[0])
            self.assertEqual(record["profiles"]["studio_local"]["model"], "example-local:8b")
            with self.assertRaisesRegex(ValueError, "REVISION_CONFLICT"):
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0,
                                 db_path=db, profile=profile)

    def test_historical_unknown_route_is_inert_and_deterministic_remains_protected(self):
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
