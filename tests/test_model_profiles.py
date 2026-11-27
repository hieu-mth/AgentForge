"""Owner explicitly registers profiles; no TOML defaults, secrets or hidden provider calls."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from agentforge.ai import model_hub


class ModelProfileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "models.sqlite3"

    def local(self, **overrides):
        return {**{"id":"studio_local", "provider":"ollama", "model":"my-local:8b",
                   "enabled":True, "base_url":"http://127.0.0.1:11434"}, **overrides}

    def save(self, profile, revision=0):
        return model_hub.change("SAVE_MODEL_PROFILE", db_path=self.db,
                                expected_revision=revision, profile=profile)

    def test_empty_registry_has_no_implicit_local_or_cloud_model(self):
        self.assertEqual(model_hub.catalog(db_path=self.db)["profiles"], [])
        self.assertEqual(model_hub.effective_models(db_path=self.db), {})
        self.assertFalse(self.db.exists())

    def test_owner_can_add_edit_and_remove_model_without_touching_weights(self):
        first = self.save(self.local())
        self.assertEqual(len(first["profiles"]), 1)
        updated = self.save(self.local(model="another:8b", enabled=False), revision=1)
        self.assertFalse(updated["profiles"][0]["enabled"])
        removed = model_hub.change("DELETE_MODEL_PROFILE", db_path=self.db,
                                   expected_revision=2, profile_id="studio_local")
        self.assertEqual(removed["profiles"], [])
        self.assertEqual(model_hub.catalog(db_path=self.db), removed)
        self.assertTrue(self.db.exists())
        with self.assertRaisesRegex(PermissionError, "Unknown Model Hub action"):
            model_hub.change("ROLLBACK_MODEL_HUB", db_path=self.db, expected_revision=3)
        self.assertEqual(model_hub.catalog(db_path=self.db), removed)

    def test_assigned_model_cannot_be_deleted_until_unassigned(self):
        self.save(self.local())
        model_hub.change("SET_MODEL_ROUTE", db_path=self.db, expected_revision=1,
                         task_id="general.text", model_ref="studio_local")
        with self.assertRaisesRegex(ValueError, "unassign"):
            model_hub.change("DELETE_MODEL_PROFILE", db_path=self.db,
                             expected_revision=2, profile_id="studio_local")
        self.assertEqual(model_hub.catalog(db_path=self.db)["revision"], 2)
        model_hub.change("RESET_MODEL_ROUTE", db_path=self.db, expected_revision=2,
                         task_id="general.text")
        removed = model_hub.change("DELETE_MODEL_PROFILE", db_path=self.db,
                                   expected_revision=3, profile_id="studio_local")
        self.assertEqual(removed["profiles"], [])

    def test_orchestrator_reference_prevents_orphan_and_failed_delete_is_atomic(self):
        self.save(self.local())
        model_hub.change("SET_MODEL_ROUTE", db_path=self.db, expected_revision=1,
                         task_id="character.select", model_ref="studio_local")
        with self.assertRaisesRegex(ValueError, "unassign"):
            model_hub.change("DELETE_MODEL_PROFILE", db_path=self.db,
                             expected_revision=2, profile_id="studio_local")
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT max(revision) FROM hub_history").fetchone()[0], 2)
        reset = model_hub.change("RESET_ORCHESTRATOR", db_path=self.db, expected_revision=2)
        self.assertEqual(next(row for row in reset["routes"] if row["id"] == "character.select")["model_ref"], "studio_local")
        model_hub.change("RESET_MODEL_ROUTE", db_path=self.db, expected_revision=3,
                         task_id="character.select")
        self.assertEqual(model_hub.change("DELETE_MODEL_PROFILE", db_path=self.db,
                                          expected_revision=4,
                                          profile_id="studio_local")["profiles"], [])

    def test_profile_validation_rejects_secret_and_invalid_cloud_url(self):
        for profile in (
            self.local(api_key="plaintext-secret"),
            self.local(base_url="http://192.168.1.10:11434"),
            self.local(provider="openai"),
            self.local(model=""),
            {"id": "cloud_local", "provider": "anthropic", "model": "test-cloud",
             "enabled": True, "api_key_env": "not-valid",
             "base_url_env": "ANTHROPIC_BASE_URL"},
            {"id": "cloud_local", "provider": "anthropic", "model": "test-cloud",
             "enabled": True, "api_key_env": "ANTHROPIC_API_KEY",
             "base_url": "https://not-local.example"},
        ):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                self.save(profile)
        self.assertEqual(model_hub.catalog(db_path=self.db)["profiles"], [])
        self.assertEqual(model_hub.catalog(db_path=self.db)["revision"], 0)

    def test_cloud_profile_is_metadata_only_and_never_implicitly_selected(self):
        cloud = {"id": "cloud_local", "provider": "anthropic",
                 "model": "claude-test", "enabled": True,
                 "base_url_env": "ANTHROPIC_BASE_URL",
                 "api_key_env": "ANTHROPIC_AUTH_TOKEN"}
        saved = self.save(cloud)
        self.assertEqual(saved["profiles"][0]["provider"], "anthropic")
        self.assertNotIn("primary", saved["orchestrator"]["policy"])
        self.assertTrue(all(row["model_ref"] is None for row in saved["routes"]))
        self.assertFalse(saved["cloud_fallback"])
        self.assertNotIn("api_key", saved["profiles"][0])
