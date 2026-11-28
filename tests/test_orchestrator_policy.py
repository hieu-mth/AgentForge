"""Current DB policy persistence and guardrails."""
import copy
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from agentforge.ai import model_hub, orchestrator_policy as policy
from tests.test_flux_runtime import profile as flux_profile


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

    def save(self, values, revision=0):
        return model_hub.change(
            "SAVE_ORCHESTRATOR", expected_revision=revision, db_path=self.db, policy=values)

    def assign(self, task, ref, revision):
        return model_hub.change("SET_MODEL_ROUTE", expected_revision=revision,
                                db_path=self.db, task_id=task, model_ref=ref)

    def test_default_catalog_is_read_only_and_never_calls_provider(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            result = model_hub.catalog(db_path=self.db)
        config = result["orchestrator"]
        self.assertFalse(self.db.exists())
        self.assertEqual(result["profiles"], [])
        self.assertEqual(config["status"], "CONFIG_ONLY")
        self.assertEqual(config["policy"]["mode"], "SUPERVISED")
        self.assertEqual(config["policy"], policy.defaults())
        self.assertEqual(len(config["capabilities"]), 11)
        self.assertFalse(config["owner_override"])

    def test_draft_routes_use_configured_motion_profile_by_registry_id(self):
        file = self.db.parent / "encoder.safetensors"
        motion = model_hub.validate_profile({"id": "custom_motion_id", "provider": "comfyui",
            "model": "ltxv-2b-0.9.8-distilled-fp8.safetensors", "enabled": True,
            "base_url": "http://127.0.0.1:8188", "motion_encoder": str(file)})
        profiles = {"custom_motion_id": motion,
                    "planner": {"provider": "ollama", "enabled": True},
                    "painter": flux_profile()}
        settings = {**policy.defaults(), "permissions": dict.fromkeys(policy.defaults()["permissions"], True),
                    "tools": ["ffmpeg"]}
        state = {"routes": {"general.text": "planner", "film.storyboard": "planner",
                            "image.generate": "painter", "film.motion": "custom_motion_id"}, "orchestrator": settings}
        with (patch.object(model_hub, "_read_state", return_value=(20, state)),
              patch.object(model_hub, "_profiles", return_value=profiles)):
            revision, bindings = model_hub.draft_routes(db_path=self.db)
        self.assertEqual(revision, 20)
        self.assertEqual(bindings["film.motion"], motion)

    def test_schema_rejects_unsafe_or_unsupported_settings(self):
        for change in (
            {"schema_version": 2}, {"mode": "legacy"}, {"gpu_concurrency": 2},
            {"retry_limit": True}, {"retry_unknown_submit": True},
            {"reconcile_comfyui": False}, {"selection": "SUGGEST"},
            {"approvals": {"cloud": False}},
            {"mappings": {"ops.monitor": "local_primary"}}, {"token": "unexpected"},
            {"fallbacks": {"general.text": "cloud_primary"}},
            {"primary": "missing"}, {"mappings": {"vision.qa": "local_primary"}},
            {"paid_api_daily_limit": -1}, {"paid_api_daily_limit": 1.5},
            {"paid_api_daily_limit": True},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.save({**policy.defaults(), **change})
        self.seed()
        with self.assertRaisesRegex(ValueError, "does not support task"):
            self.assign("film.motion", "local_primary", revision=2)

    def test_save_reset_and_resave_share_existing_route_and_revision(self):
        self.seed()
        values = {**policy.defaults(), "permissions": {**policy.defaults()["permissions"], "plan": True}}
        self.assign("general.text", "cloud_primary", revision=2)
        result = self.save(values, revision=3)
        same_route = next(row for row in result["routes"] if row["id"] == "general.text")
        self.assertEqual(same_route["model_ref"], "cloud_primary")
        self.assertNotIn("mappings", result["orchestrator"]["policy"])
        with self.assertRaisesRegex(ValueError, "REVISION_CONFLICT"):
            self.save(values, revision=2)
        reset = model_hub.change("RESET_ORCHESTRATOR", expected_revision=4, db_path=self.db)
        self.assertFalse(reset["orchestrator"]["owner_override"])
        self.assertEqual(reset["routes"], result["routes"])
        resaved = self.save(values, revision=5)
        self.assertEqual(resaved["orchestrator"]["policy"], values)
        self.assertEqual(model_hub.catalog(db_path=self.db), resaved)

    def test_obsolete_policy_is_rejected_without_rewriting_database(self):
        self.seed()
        _, state = model_hub._read_state(db_path=self.db)
        state["orchestrator"] = {**policy.defaults(), "mappings": {}}
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE hub_state SET payload=?", (json.dumps(state),))
        before = self.db.read_bytes()
        with self.assertRaises(ValueError):
            model_hub.catalog(db_path=self.db)
        self.assertEqual(self.db.read_bytes(), before)

    def test_invalid_policy_write_is_atomic(self):
        self.seed()
        original = self.save(policy.defaults(), revision=2)
        with self.assertRaises(ValueError):
            self.save({**policy.defaults(), "mappings": {}}, revision=3)
        self.assertEqual(model_hub.catalog(db_path=self.db), original)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT max(revision) FROM hub_history").fetchone()[0], 3)

    def test_disabled_reference_is_reported_unavailable(self):
        self.seed()
        legacy = model_hub.change("SET_MODEL_ROUTE", expected_revision=2, db_path=self.db,
                                  task_id="general.text", model_ref="cloud_primary")
        self.assertFalse(legacy["orchestrator"]["owner_override"])
        cloud = copy.deepcopy(model_hub._profiles(
            state=model_hub._read_state(db_path=self.db)[1])["cloud_primary"])
        self.save(policy.defaults(), revision=3)
        cloud["enabled"] = False
        result = model_hub.change("SAVE_MODEL_PROFILE", expected_revision=4,
                                  db_path=self.db, profile=cloud)
        row = next(row for row in result["orchestrator"]["capabilities"]
                   if row["id"] == "general.text")
        self.assertEqual(row["status"], "UNAVAILABLE")
        self.assertNotIn("cloud_primary", row["options"])

    def test_resolver_is_pure_and_does_not_fallback(self):
        profiles = {"local": {"provider": "ollama", "enabled": True},
                    "cloud": {"provider": "anthropic", "enabled": True}}
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            self.assertEqual(policy.resolve("general.text", profiles, None)["status"], "UNAVAILABLE")
            selected = policy.resolve("general.text", profiles, "cloud")
            self.assertTrue(selected["requires_owner_approval"])
            self.assertFalse(selected["execution_allowed"])
            self.assertEqual(policy.resolve("general.text", profiles, "local")["model_ref"], "local")

    def test_casting_uses_the_same_route_api_and_reset_preserves_it(self):
        self.seed()
        self.assign("character.select", "local_primary", revision=2)
        saved = self.save(policy.defaults(), revision=3)
        self.assertEqual(next(row for row in saved["routes"] if row["id"] == "character.select")["model_ref"], "local_primary")
        self.assertNotIn("mappings", saved["orchestrator"]["policy"])
        reset = model_hub.change("RESET_ORCHESTRATOR", expected_revision=4, db_path=self.db)
        self.assertEqual(reset["routes"], saved["routes"])

    def test_production_options_are_pure_and_reflect_admission(self):
        self.seed()
        snapshot = model_hub.catalog(db_path=self.db)
        methods = {row["id"]: row["available"] for row in snapshot["production_options"]["methods"]}
        self.assertEqual(methods, {"assigned": True, "auto": False, "local": False, "hybrid": False, "cloud": False})
        video = {"id": "cloud_video", "provider": "ltx_cloud", "model": "ltx-2-3-fast",
                 "enabled": True, **model_hub.ADAPTERS["ltx_cloud"]["environment_defaults"]}
        model_hub.change("SAVE_MODEL_PROFILE", expected_revision=2, db_path=self.db, profile=video)
        p = policy.defaults()
        p["permissions"].update(plan=True, assign_models=True, call_cloud=True, run_tools=True)
        p["tools"] = ["ffmpeg"]
        self.assign("general.text", "cloud_primary", revision=3)
        self.assign("film.storyboard", "cloud_primary", revision=4)
        self.assign("film.motion", "cloud_video", revision=5)
        snapshot = self.save(p, revision=6)
        self.assertEqual({row["id"]: row["available"] for row in snapshot["production_options"]["methods"]},
                         {"assigned": False, "auto": True, "local": False, "hybrid": True, "cloud": True})
        self.assertEqual(snapshot["production_options"]["auto_min_cloud_seconds"], 12)

    def test_video_routes_follow_declared_input_modes(self):
        from agentforge.features.film_studio import studio_ltx_cloud

        self.seed()
        base = {"provider": "ltx_cloud", "enabled": True,
                **model_hub.ADAPTERS["ltx_cloud"]["environment_defaults"]}
        text_video = {**base, "id": "text_video", "model": "ltx-2-3-fast"}
        image_video = {**base, "id": "image_video", "model": "ltx-2-3-pro"}

        def modes(profile):
            return ("text-to-video",) if profile["model"] == text_video["model"] else ("image-to-video",)

        with patch.object(studio_ltx_cloud, "input_modes", side_effect=modes):
            for revision, profile in enumerate((text_video, image_video), 2):
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=revision, db_path=self.db, profile=profile)
            self.assertEqual(model_hub.capability_contract("film.motion", text_video)["input_modes"], ["text-to-video"])
            _, candidates = model_hub.production_candidates("auto", db_path=self.db)
            self.assertEqual({(c["id"], c["method"]) for c in candidates},
                             {("text_video", "cloud"), ("image_video", "hybrid")})
            for profile, bad in ((text_video, "hybrid"), (image_video, "cloud")):
                with self.assertRaises(ValueError):
                    model_hub.production_profile(profile["id"], bad, db_path=self.db)
            self.assertEqual(model_hub.production_profile("text_video", "cloud", db_path=self.db), text_video)
            self.assertEqual(model_hub.production_profile("image_video", "hybrid", db_path=self.db), image_video)
            self.assign("general.text", "cloud_primary", revision=4)
            self.assign("film.storyboard", "cloud_primary", revision=5)
            p = policy.defaults()
            p.update(permissions=dict.fromkeys(p["permissions"], True), tools=["ffmpeg"])
            self.save(p, revision=6)
            _, bindings = model_hub.draft_routes(db_path=self.db, moving=True, motion_ref="text_video", direct_cloud=True)
            self.assertNotIn("image.generate", bindings)
            with self.assertRaisesRegex(ValueError, "text-to-video"):
                model_hub.draft_routes(db_path=self.db, moving=True, motion_ref="image_video", direct_cloud=True)

    def test_local_t2v_admission_does_not_require_an_image_route(self):
        from agentforge.features.film_studio import motion_ltx

        self.seed()
        record = motion_ltx.text_workflow()
        record["weights_sha256"] = {"checkpoint": "a"*64, "encoder": "b"*64}
        video = {"id": "local_video", "provider": "comfyui", "model": motion_ltx.CHECKPOINT,
                 "enabled": True, "base_url": "http://127.0.0.1:8188",
                 "motion_encoder": str(self.db.parent / motion_ltx.ENCODER), "comfy_video": record}
        model_hub.change("SAVE_MODEL_PROFILE", expected_revision=2, db_path=self.db, profile=video)
        self.assign("general.text", "local_primary", revision=3)
        self.assign("film.storyboard", "local_primary", revision=4)
        self.assign("film.motion", "local_video", revision=5)
        p = policy.defaults()
        p.update(permissions=dict.fromkeys(p["permissions"], True), tools=["ffmpeg"])
        self.save(p, revision=6)
        _, bindings = model_hub.draft_routes(db_path=self.db, moving=True)
        self.assertNotIn("image.generate", bindings)
        self.assertEqual(bindings["film.motion"]["id"], "local_video")
        _, candidates = model_hub.production_candidates("local", db_path=self.db)
        self.assertEqual([(c["id"], c["execution_ready"], c["input_modes"]) for c in candidates],
                         [("local_video", True, ["text-to-video"])])
        with self.assertRaises(ValueError):
            model_hub.draft_routes(db_path=self.db, moving=True, motion_ref="local_video", direct_cloud=True)

    def test_planning_candidates_do_not_require_media_permissions(self):
        self.seed()
        video = {"id": "cloud_video", "provider": "ltx_cloud", "model": "ltx-2-3-fast",
                 "enabled": True, **model_hub.ADAPTERS["ltx_cloud"]["environment_defaults"]}
        model_hub.change("SAVE_MODEL_PROFILE", expected_revision=2, db_path=self.db, profile=video)
        self.assign("general.text", "local_primary", revision=3)
        self.assign("film.storyboard", "local_primary", revision=4)
        p = policy.defaults()
        p["permissions"].update(plan=True, assign_models=True, call_local=True)
        snapshot = self.save(p, revision=5)
        cloud = next(row for row in snapshot["production_options"]["methods"] if row["id"] == "cloud")
        self.assertTrue(cloud["available"])
        self.assertFalse(cloud["execution_ready"])
        _, candidates = model_hub.production_candidates("cloud", db_path=self.db)
        self.assertEqual([c["id"] for c in candidates], ["cloud_video"])
        self.assertFalse(candidates[0]["execution_ready"])
        self.assertEqual(model_hub.production_profile("cloud_video", "cloud", db_path=self.db)["model"], video["model"])
        with self.assertRaises(PermissionError):
            model_hub.draft_routes(db_path=self.db, moving=True, motion_ref="cloud_video", direct_cloud=True)
