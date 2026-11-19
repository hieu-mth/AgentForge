"""DB-only policy persistence, guardrails, compatibility and rollback."""
import copy
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from agentforge.ai import model_hub, orchestrator_policy as policy


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "hub.sqlite3"

    def seed(self):
        """Create Owner models explicitly: no Git model defaults."""
        profiles = [
            {"id": "local_primary", "provider": "ollama", "model": "test-local:8b",
             "enabled": True, "base_url": "http://127.0.0.1:11434"},
            {"id": "cloud_primary", "provider": "anthropic", "model": "test-cloud",
             "enabled": True, "base_url_env": "ANTHROPIC_BASE_URL",
             "api_key_env": "ANTHROPIC_AUTH_TOKEN"},
        ]
        for i, profile in enumerate(profiles):
            model_hub.change("SAVE_MODEL_PROFILE", expected_revision=i,
                             db_path=self.db, profile=profile)
        return 2

    def save(self, values, changes=None, revision=0):
        return model_hub.change(
            "SAVE_ORCHESTRATOR", expected_revision=revision, db_path=self.db,
            policy=values, route_changes=changes or {})

    def test_default_catalog_is_read_only_and_never_calls_provider(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            result = model_hub.catalog(db_path=self.db)
        config = result["orchestrator"]
        self.assertFalse(self.db.exists())
        self.assertEqual(result["profiles"], [])
        self.assertEqual(config["status"], "CONFIG_ONLY")
        self.assertEqual(config["policy"]["mode"], "SUPERVISED")
        self.assertEqual(len(config["capabilities"]), 9)
        self.assertFalse(config["owner_override"])

    def test_schema_rejects_unsafe_or_unsupported_settings(self):
        for change in (
            {"schema_version": 2}, {"mode": "legacy"}, {"gpu_concurrency": 2},
            {"retry_limit": True}, {"retry_unknown_submit": True},
            {"reconcile_comfyui": False}, {"selection": "SUGGEST"},
            {"approvals": {key: False for key in policy.APPROVALS}},
            {"mappings": {"ops.monitor": "local_primary"}}, {"token": "unexpected"},
            {"fallbacks": {"general.text": "cloud_primary"}},
            {"primary": "missing"}, {"mappings": {"vision.qa": "local_primary"}},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.save({**policy.defaults(), **change})
        self.seed()
        with self.assertRaisesRegex(ValueError, "tương thích"):
            self.save(policy.defaults(), {"film.motion": "local_primary"}, revision=2)

    def test_save_reset_and_rollback_share_existing_route_and_revision(self):
        self.seed()
        values = {**policy.defaults(), "primary": "cloud_primary",
                  "fallbacks": {"general.text": "local_primary"}, "fallback": "LOCAL"}
        result = self.save(values, {"general.text": "cloud_primary"}, revision=2)
        same_route = next(row for row in result["routes"] if row["id"] == "general.text")
        self.assertEqual(same_route["model_ref"], "cloud_primary")
        self.assertNotIn("general.text", result["orchestrator"]["policy"]["mappings"])
        with self.assertRaisesRegex(ValueError, "REVISION_CONFLICT"):
            self.save(values, revision=2)
        reset = model_hub.change("RESET_ORCHESTRATOR", expected_revision=3, db_path=self.db)
        self.assertFalse(reset["orchestrator"]["owner_override"])
        restored = model_hub.change("ROLLBACK_MODEL_HUB", expected_revision=4,
                                    target_revision=3, db_path=self.db)
        self.assertEqual(restored["orchestrator"]["policy"], values)
        self.assertEqual(model_hub.catalog(db_path=self.db), restored)

    def test_invalid_later_binding_rolls_back_policy_and_first_binding(self):
        self.seed()
        original = self.save(policy.defaults(), revision=2)
        with self.assertRaises(ValueError):
            self.save({**policy.defaults(), "decompose": True},
                      {"general.text": "cloud_primary", "film.motion": "local_primary"},
                      revision=3)
        self.assertEqual(model_hub.catalog(db_path=self.db), original)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT max(revision) FROM hub_history").fetchone()[0], 3)

    def test_disabled_reference_and_legacy_snapshots_are_readable(self):
        self.seed()
        legacy = model_hub.change("SET_MODEL_ROUTE", expected_revision=2, db_path=self.db,
                                  task_id="general.text", model_ref="cloud_primary")
        self.assertFalse(legacy["orchestrator"]["owner_override"])
        cloud = copy.deepcopy(model_hub._profiles(state=legacy_state(legacy))["cloud_primary"])
        self.save({**policy.defaults(), "primary": "cloud_primary"}, revision=3)
        cloud["enabled"] = False
        result = model_hub.change("SAVE_MODEL_PROFILE", expected_revision=4,
                                  db_path=self.db, profile=cloud)
        row = next(row for row in result["orchestrator"]["capabilities"]
                   if row["id"] == "general.text")
        self.assertEqual(row["status"], "UNAVAILABLE")
        self.assertNotIn("cloud_primary", row["options"])

    def test_resolver_is_pure_and_explicitly_refuses_cloud_fallback(self):
        profiles = {"local": {"provider": "ollama", "enabled": True},
                    "cloud": {"provider": "anthropic", "enabled": True}}
        config = {**policy.defaults(), "fallback": "LOCAL",
                  "fallbacks": {"general.text": "cloud"}}
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            self.assertEqual(policy.resolve("general.text", config, profiles, None,
                                            allow_fallback=True)["status"], "UNAVAILABLE")
            selected = policy.resolve("general.text", config, profiles, "cloud")
            self.assertTrue(selected["requires_owner_approval"])
            self.assertFalse(selected["execution_allowed"])
            config["fallbacks"]["general.text"] = "local"
            self.assertEqual(policy.resolve("general.text", config, profiles, None,
                                            allow_fallback=True)["source"], "LOCAL_FALLBACK")
            config.update(selection="SUGGEST", allowed_profiles=["local", "cloud"])
            suggested = policy.resolve("general.text", config, profiles, None)
            self.assertEqual(suggested["candidates"], ["local", "cloud"])
            self.assertFalse(suggested["execution_allowed"])


def legacy_state(snapshot):
    return {"profiles": {p["id"]: p for p in snapshot["profiles"]}, "routes": {}}
