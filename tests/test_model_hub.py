"""DB-only model profiles, source-owned capabilities and backward compatibility."""
from pathlib import Path
import json
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import sys
import threading
import unittest
from unittest.mock import patch

from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_motion, motion_ltx
from agentforge.features.media import flux_runtime
from tests.owner_http_fixture import OwnerHttpFixture
from tests.test_flux_runtime import profile as flux_profile


class ModelHubTests(unittest.TestCase):
    def test_ollama_metadata_preflight_rejects_redirects(self):
        paths = []

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                paths.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/unexpected")
                self.end_headers()

        with ThreadingHTTPServer(("127.0.0.1", 0), Redirect) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                result = model_hub._check_ollama({"id": "local", "model": "sample:latest",
                    "base_url": f"http://127.0.0.1:{server.server_port}"})
            finally:
                server.shutdown()
                worker.join()
        self.assertEqual(result["status"], "HTTP_ERROR")
        self.assertEqual(paths, ["/api/tags"])

    def test_legacy_comfy_routes_read_but_unsupported_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "hub.sqlite3"
            profile = {**flux_profile(), "id": "legacy_wan", "model": "wan2.2_ti2v_5B_fp16"}
            profile.pop("flux")
            model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, db_path=db, profile=profile)
            with closing(sqlite3.connect(db)) as conn, conn:
                payload = json.loads(conn.execute("SELECT payload FROM hub_state").fetchone()[0])
                payload["routes"] = {"film.motion": "legacy_wan"}
                conn.execute("UPDATE hub_state SET payload=?", (json.dumps(payload),))
            before = db.read_bytes()
            catalog = model_hub.catalog(db_path=db)
            route = next(r for r in catalog["routes"] if r["id"] == "film.motion")
            self.assertEqual((route["model_ref"], route["status"]), ("legacy_wan", "INCOMPATIBLE"))
            with self.assertRaises(ValueError):
                model_hub.change("SET_MODEL_ROUTE", expected_revision=1, db_path=db,
                                 task_id="image.generate", model_ref="legacy_wan")
            with patch.object(draft_motion, "registry_readiness") as probe:
                result = model_hub.capability_readiness("legacy_wan", "film.motion",
                                                       expected_revision=1, db_path=db)
            probe.assert_not_called()
            self.assertTrue(result["configuration_valid"])
            self.assertIsNone(result["runtime_available"])
            self.assertEqual(result["reason"], "MOTION_PROFILE_INCOMPATIBLE")
            self.assertEqual(db.read_bytes(), before)

    def test_capability_readiness_routes_by_registered_workflow(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "hub.sqlite3"
            flux = flux_profile()
            motion = {"id": "ltx", "provider": "comfyui", "enabled": True,
                      "base_url": f"http://127.0.0.1:{draft_motion.motion_comfy.PORT}",
                      "model": motion_ltx.CHECKPOINT, "motion_encoder": str(Path(folder) / motion_ltx.ENCODER)}
            ollama = {"id": "local_text", "provider": "ollama", "enabled": True,
                      "model": "fixture:latest", "base_url": "http://127.0.0.1:11434"}
            for revision, profile in enumerate((flux, motion, ollama)):
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=revision, db_path=db, profile=profile)
            before = db.read_bytes()

            def check(profile, capability):
                return model_hub.capability_readiness(profile["id"], capability, expected_revision=3, db_path=db)

            with patch.object(flux_runtime, "readiness", return_value="WORKFLOW_NODE_UNAVAILABLE") as probe:
                image = check(flux, "image.generate")
                self.assertTrue(image["local_runtime_compatible"])
                self.assertTrue(image["runtime_available"])
                self.assertFalse(image["endpoint_metadata_compatible"])
                self.assertEqual(image["readiness"], "MISSING_DEPENDENCY")
                self.assertEqual(image["reason"], "WORKFLOW_NODE_UNAVAILABLE")
                self.assertEqual(image["output_limits"]["max_resolution"], 1024)
                updated = flux_profile()
                updated["flux"]["workflow"]["6"]["inputs"]["text"] = "Changed workflow"
                self.assertNotEqual(image["workflow_sha256"],
                                    model_hub.capability_contract("image.generate", updated)["workflow_sha256"])
                probe.assert_called_once_with(flux["flux"], 12345, inspect_all_nodes=True)
                self.assertEqual(check(flux, "film.motion")["status"], "UNSUPPORTED")
                with self.assertRaisesRegex(ValueError, "REVISION_CONFLICT"):
                    model_hub.capability_readiness(flux["id"], "image.generate", expected_revision=2, db_path=db)
                self.assertEqual(probe.call_count, 1)

            with (patch.object(draft_motion.comfy_service, "_settings", return_value={
                      "port": draft_motion.motion_comfy.PORT, "install_root": folder}) as settings,
                  patch.object(draft_motion.comfy_service, "ensure_running", side_effect=AssertionError("start")),
                  patch.object(draft_motion.render, "find_media_tool", return_value="tool"),
                  patch.object(motion_ltx, "verify_weights") as weights,
                  patch.object(motion_ltx, "check_runtime") as nodes,
                  patch.object(draft_motion.comfyui, "request_json",
                               return_value={"devices": [{"type": "cuda"}]}) as request):
                result = check(motion, "film.motion")
                self.assertEqual(result["status"], "METADATA_COMPATIBLE")
                self.assertTrue(result["runtime_available"])
                self.assertTrue(result["endpoint_metadata_compatible"])
                self.assertFalse(result["inference_verified"])
                self.assertEqual(result["endpoint_ownership"], "NOT_CHECKED")
                self.assertEqual(result["workflow_sha256"], draft_motion.workflow_sha())
                self.assertEqual(result["output_limits"],
                                 {"format": "mp4", "fps": 24, "max_frames": 49, "resolution": [512, 288]})
                weights.assert_called_once_with(folder, motion["motion_encoder"], metadata_only=True)
                nodes.assert_called_once_with(draft_motion.motion_comfy.PORT, require_models=True, frames=49)
                self.assertEqual(request.call_args.args, ("/system_stats",))
                self.assertEqual(check(motion, "image.generate")["status"], "UNSUPPORTED")
                settings.return_value = None
                external = check(motion, "film.motion")
                self.assertEqual(external["status"], "MISSING_DEPENDENCY")
                self.assertEqual(external["reason"], "MOTION_LAUNCHER_REQUIRED")
                self.assertTrue(external["endpoint_metadata_compatible"])
                before_calls = request.call_count
                self.assertEqual(draft_motion.registry_readiness({
                    **motion, "base_url": "http://127.0.0.1:8192"}), "MOTION_ENDPOINT_MISMATCH")
                self.assertEqual(draft_motion.registry_readiness({
                    **motion, "base_url": f"http://[::1]:{draft_motion.motion_comfy.PORT}"}),
                    "MOTION_ENDPOINT_MISMATCH")
                self.assertEqual(request.call_count, before_calls)
                request.side_effect = ConnectionRefusedError()
                offline = check(motion, "film.motion")
                self.assertEqual(offline["status"], "UNAVAILABLE")
                self.assertEqual(offline["reason"], "COMFYUI_UNAVAILABLE")
                self.assertFalse(offline["runtime_available"])
                self.assertIsNone(offline["endpoint_metadata_compatible"])
                request.side_effect = None
                request.return_value = {"unrelated": []}
                self.assertEqual(check(motion, "film.motion")["reason"], "INVALID_RESPONSE")
                request.return_value = {"devices": [{"type": "cuda"}]}
                nodes.side_effect = ValueError("missing sampler")
                self.assertEqual(check(motion, "film.motion")["reason"], "MOTION_WORKFLOW_UNAVAILABLE")
            with patch.object(model_hub, "_check_ollama", return_value={"status": "LOCAL_MODEL_FOUND"}):
                self.assertEqual(check(ollama, "film.storyboard")["status"], "METADATA_COMPATIBLE")
            self.assertEqual(db.read_bytes(), before)

    def test_disabled_and_cloud_preflight_do_not_probe_providers(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "hub.sqlite3"
            profiles = (
                {"id": "disabled", "provider": "ollama", "enabled": False,
                 "model": "fixture:latest", "base_url": "http://localhost:11434"},
                {"id": "cloud", "provider": "anthropic", "enabled": True, "model": "fixture",
                 **model_hub.ADAPTERS["anthropic"]["legacy_defaults"]},
            )
            for revision, profile in enumerate(profiles):
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=revision, db_path=db, profile=profile)
            with patch.object(model_hub, "_check_ollama", side_effect=AssertionError("unexpected probe")):
                disabled, cloud = [model_hub.capability_readiness(
                    profile["id"], "general.text", expected_revision=2, db_path=db) for profile in profiles]
            self.assertEqual((disabled["status"], disabled["reason"]), ("NOT_CHECKED", "DISABLED"))
            self.assertEqual(cloud["status"], "NOT_CHECKED")
            self.assertEqual(cloud["reason"], "CLOUD_PREFLIGHT_UNSUPPORTED")
            self.assertTrue(cloud["route_configurable"])
            self.assertFalse(cloud["local_runtime_compatible"])
            self.assertEqual(cloud["route_configurable"],
                             model_hub.orchestrator_policy.compatible("text", profiles[1]))
            self.assertTrue(all(not result["inference_invoked"] and result["runtime_available"] is None
                                for result in (disabled, cloud)))

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
                               "model": "fixture-model", "enabled": True,
                               **adapter.get("legacy_defaults", adapter["defaults"])}
                    model_hub.change("SAVE_MODEL_PROFILE", expected_revision=revision,
                                     db_path=db, profile=profile)
                    with self.assertRaises(model_hub.ModelConfigError):
                        model_hub.validate_profile({**profile, "api_key": "secret"})
            self.assertEqual(len(model_hub.catalog(db_path=db)["profiles"]), 3)
            with self.assertRaises(model_hub.ModelConfigError):
                model_hub.validate_profile({**profile, "api_key_env": "Bearer actual-key"})

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI")
    def test_direct_cloud_key_is_encrypted_and_not_returned(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "hub.sqlite3"
            key = "test-credential-not-a-real-key"
            profile = {"id": "cloud_test", "provider": "anthropic", "enabled": True,
                       "model": "fixture-model", "base_url": "https://api.example.com/anthropic"}
            saved = model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0,
                                     db_path=db, profile=profile, api_key=key)
            self.assertTrue(saved["profiles"][0]["has_api_key"])
            self.assertNotIn("api_key_protected", saved["profiles"][0])
            self.assertNotIn(key.encode(), db.read_bytes())
            model_hub.change("SAVE_MODEL_PROFILE", expected_revision=1, db_path=db,
                             profile={**profile, "model": "updated-model"})
            with self.assertRaisesRegex(ValueError, "API key"):
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=2, db_path=db,
                                 profile={**profile, "base_url": "https://other.example.com"})

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


class ModelHubReadinessHttpTests(OwnerHttpFixture):
    def test_readiness_requires_owner_and_exact_metadata_request(self):
        path = "/api/model-hub/readiness"
        body = {"ack": "CHECK_CAPABILITY_READINESS", "profile_id": "owner_text",
                "expected_revision": 1, "capability": "general.text"}
        with patch.object(model_hub, "capability_readiness", return_value={"scope": "METADATA_ONLY"}) as check:
            self.assertEqual(self.req("POST", path, body)[0], 401)
            self.login()
            self.assertEqual(self.req("POST", path, body, csrf=False)[0], 403)
            self.assertEqual(self.req("POST", path, {**body, "endpoint": "https://example.com"})[0], 400)
            check.assert_not_called()
            self.assertEqual(self.req("POST", path, body)[:2], (200, {"scope": "METADATA_ONLY"}))
            check.assert_called_once_with("owner_text", "general.text", expected_revision=1)


if __name__ == "__main__":
    unittest.main()
