"""M6 Model Hub: real SQLite CAS, Owner API auth and zero inference side effects."""
import http.client
from contextlib import closing
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import model
from agentforge.ai import model_hub
from agentforge.api.server import create_server


def local_profile(**extra):
    value = {"id": "coding_local", "provider": "ollama",
             "model": "qwen3-coder:7b", "enabled": True,
             "base_url": "http://127.0.0.1:11434"}
    value.update(extra)
    return value


class ModelHubTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "data" / "company" / "model_hub.sqlite3"
        patcher = patch.object(model_hub, "DB_PATH", self.db)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_profiles_routes_and_rules_are_read_only(self):
        value = model_hub.catalog()
        self.assertEqual(0, value["revision"])
        self.assertFalse(self.db.exists())
        by_id = {v["id"]: v for v in value["routes"]}
        self.assertEqual("ROUTED", by_id["web.create"]["status"])
        self.assertEqual("local_primary", by_id["web.create"]["model_ref"])
        self.assertEqual("UNCONFIGURED", by_id["film.motion"]["status"])
        self.assertFalse(by_id["film.motion"]["runtime_wired"])
        self.assertEqual("DETERMINISTIC", by_id["ops.monitor"]["status"])
        self.assertIsNone(by_id["ops.monitor"]["model_ref"])
        self.assertFalse(value["cloud_fallback"])
        self.assertFalse(value["gpu_auto_start"])
        self.assertNotIn("secret", json.dumps(value).lower())

    def test_profile_validation_rejects_ssrf_secrets_and_unknown_providers(self):
        bad_profiles = [
            local_profile(base_url="https://example.com:11434"),
            local_profile(base_url="http://192.168.1.8:11434"),
            local_profile(base_url="http://localhost:11434@evil.example:8123"),
            local_profile(base_url="http://localhost:11434/api/chat"),
            local_profile(base_url="http://localhost:11434/?token=oops"),
            local_profile(base_url="http://localhost"),
            local_profile(api_key="secret"),
            local_profile(provider="openai"),
            local_profile(enabled=1),
            local_profile(id="../escape"),
            local_profile(model="bad model"),
        ]
        for item in bad_profiles:
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    model_hub.validate_profile(item)
        cloud = {"id": "cloud_route", "provider": "anthropic",
                 "model": "claude-test", "enabled": True,
                 "base_url_env": "ANTHROPIC_BASE_URL",
                 "api_key_env": "ANTHROPIC_AUTH_TOKEN"}
        self.assertEqual("anthropic", model_hub.validate_profile(cloud)["provider"])
        with self.assertRaises(ValueError):
            model_hub.validate_profile({**cloud, "base_url": "https://example.com"})

    def test_save_and_route_apply_to_live_llm_resolver(self):
        model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0,
                         profile=local_profile())
        data = model_hub.change("SET_MODEL_ROUTE", expected_revision=1,
                                task_id="webapp.develop", model_ref="coding_local")
        self.assertEqual(2, data["revision"])
        with patch.dict(os.environ, {"AGENTFORGE_MODEL_REF": ""}):
            with patch.object(model, "DOTENV_PATH", self.db.parent / "missing.env"):
                runtime = model.resolve_runtime("webapp_developer", model.DEFAULT_JSON_SYSTEM)
        self.assertEqual("coding_local", runtime["model_ref"])
        self.assertEqual("qwen3-coder:7b", runtime["model"])
        self.assertEqual(2, runtime["routing_revision"])
        self.assertEqual("owner", runtime["route_source"])
        self.assertTrue(self.db.is_file())
        with closing(sqlite3.connect(self.db)) as conn:
            row = conn.execute("SELECT revision FROM hub_state").fetchone()
            self.assertEqual((2,), row)

    def test_invalid_mutation_does_not_advance_revision(self):
        model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0,
                         profile=local_profile())
        for kwargs in (
            {"action": "SET_MODEL_ROUTE", "task_id": "ops.monitor",
             "model_ref": "local_primary"},
            {"action": "SET_MODEL_ROUTE", "task_id": "film.motion",
             "model_ref": "local_primary"},
            {"action": "SET_MODEL_ROUTE", "task_id": "web.create",
             "model_ref": "unknown"},
            {"action": "SAVE_MODEL_PROFILE", "profile":
                local_profile(id="local_primary", provider="comfyui")},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    model_hub.change(kwargs.pop("action"), expected_revision=1, **kwargs)
                self.assertEqual(1, model_hub.catalog()["revision"])
        with self.assertRaisesRegex(ValueError, "MODEL_HUB_REVISION_CONFLICT"):
            model_hub.change("RESET_MODEL_ROUTE", expected_revision=0,
                             task_id="web.create")

    def test_video_is_configurable_but_never_wired_as_text(self):
        p = {"id": "wan_video", "provider": "comfyui", "model": "wan2.2_5b",
             "base_url": "http://127.0.0.1:8188", "enabled": True}
        model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, profile=p)
        value = model_hub.change("SET_MODEL_ROUTE", expected_revision=1,
                                 task_id="film.motion", model_ref="wan_video")
        record = next(x for x in value["routes"] if x["id"] == "film.motion")
        self.assertEqual("CONFIG_ONLY", record["status"])
        self.assertFalse(record["runtime_wired"])
        self.assertNotIn("wan_video", model_hub.effective_models())
        with self.assertRaises(ValueError):
            model_hub.change("SET_MODEL_ROUTE", expected_revision=2,
                             task_id="web.create", model_ref="wan_video")

    def test_versioned_rollback_is_explicit_and_atomic(self):
        model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0,
                         profile=local_profile())
        model_hub.change("SET_MODEL_ROUTE", expected_revision=1,
                         task_id="web.create", model_ref="coding_local")
        restored = model_hub.change("ROLLBACK_MODEL_HUB", expected_revision=2,
                                    target_revision=1)
        self.assertEqual(3, restored["revision"])
        route = next(x for x in restored["routes"] if x["id"] == "web.create")
        self.assertEqual("local_primary", route["model_ref"])
        self.assertEqual("default", route["source"])
        with self.assertRaises(ValueError):
            model_hub.change("ROLLBACK_MODEL_HUB", expected_revision=3,
                             target_revision=9)
        self.assertEqual(3, model_hub.catalog()["revision"])

    def test_saved_cloud_selection_requires_separate_process_consent(self):
        model_hub.change("SET_MODEL_ROUTE", expected_revision=0,
                         task_id="research.opportunity", model_ref="cloud_primary")
        env = {"AGENTFORGE_MODEL_REF": "", "AGENTFORGE_CLOUD_MODEL_CONSENT": "",
               "ANTHROPIC_BASE_URL": "https://gateway.example/v1",
               "ANTHROPIC_AUTH_TOKEN": "never-store-this-in-sqlite"}
        with patch.dict(os.environ, env):
            with patch.object(model, "DOTENV_PATH", self.db.parent / "missing.env"):
                with self.assertRaisesRegex(PermissionError, "CLOUD_MODEL_CONSENT_REQUIRED"):
                    model.resolve_runtime("opportunity_researcher", model.DEFAULT_TEXT_SYSTEM)
                os.environ["AGENTFORGE_CLOUD_MODEL_CONSENT"] = "YES"
                resolved = model.resolve_runtime("opportunity_researcher", model.DEFAULT_TEXT_SYSTEM)
        self.assertEqual("cloud_primary", resolved["model_ref"])
        self.assertEqual("anthropic", resolved["provider"])
        self.assertNotIn("never-store-this", self.db.read_bytes().decode(errors="ignore"))

    def test_local_metadata_preflight_disables_proxy_and_http_redirects(self):
        import urllib.error
        import urllib.request
        with patch("urllib.request.build_opener") as build:
            build.return_value.open.side_effect = urllib.error.HTTPError(
                "http://127.0.0.1:11434/api/tags", 302,
                "Redirect refused", {}, None)
            result = model_hub.check_local_profile("local_primary")
        self.assertEqual("UNAVAILABLE", result["status"])
        handlers = build.call_args.args
        self.assertTrue(any(isinstance(h, urllib.request.ProxyHandler)
                            and h.proxies == {} for h in handlers))
        no_redirect = next(h for h in handlers
                           if isinstance(h, urllib.request.HTTPRedirectHandler))
        self.assertIsNone(no_redirect.redirect_request(
            None, None, 302, "Found", {}, "https://external.example/steal"))

    def test_metadata_check_only_uses_loopback_tags_and_never_generates(self):
        class Tags(io.BytesIO):
            status = 200
        def opener(request, timeout):
            self.assertEqual("GET", request.get_method())
            self.assertEqual("http://127.0.0.1:11434/api/tags", request.full_url)
            self.assertEqual(3, timeout)
            return Tags(b'{"models":[{"name":"qwen3:8b"}]}')
        result = model_hub.check_local_profile("local_primary", opener=opener)
        self.assertEqual("LOCAL_MODEL_FOUND", result["status"])
        self.assertFalse(result["inference_invoked"])
        with patch("urllib.request.urlopen") as net:
            result = model_hub.check_local_profile("cloud_primary")
            self.assertEqual("NOT_CHECKED", result["status"])
            net.assert_not_called()


class ModelHubHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Path(temp.name) / "owner" / "model_hub.sqlite3"
        mock = patch.object(model_hub, "DB_PATH", db)
        mock.start()
        self.addCleanup(mock.stop)
        self.server = create_server(0, owner_code="test-owner-hub-code-123")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        head = {"Origin": "http://127.0.0.1:"+str(self.server.server_port)}
        head.update(headers or {})
        payload = None
        if data is not None:
            payload = json.dumps(data).encode("utf-8")
            head["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=head)
        response = conn.getresponse()
        body = response.read()
        result = response.status, dict(response.getheaders()), json.loads(body)
        conn.close()
        return result

    def test_owner_only_json_api_with_csrf_and_cas(self):
        self.assertEqual(401, self.request("GET", "/api/model-hub")[0])
        login = self.request("POST", "/api/login", {"code": "test-owner-hub-code-123"})
        self.assertEqual(200, login[0])
        cookie = login[1]["Set-Cookie"].split(";", 1)[0]
        csrf = login[2]["csrf"]
        self.assertEqual(200, self.request("GET", "/api/model-hub",
                                           headers={"Cookie": cookie})[0])
        payload = {"ack": "SET_MODEL_ROUTE", "expected_revision": 0,
                   "task_id": "web.create", "model_ref": "local_primary"}
        self.assertEqual(403, self.request("POST", "/api/model-hub/route",
                                           payload, {"Cookie": cookie})[0])
        ok = self.request("POST", "/api/model-hub/route", payload, {
            "Cookie": cookie, "X-CSRF-Token": csrf})
        self.assertEqual(200, ok[0])
        self.assertEqual(1, ok[2]["revision"])
        stale = self.request("POST", "/api/model-hub/route", payload, {
            "Cookie": cookie, "X-CSRF-Token": csrf})
        self.assertEqual(400, stale[0])
        self.assertIn("REVISION_CONFLICT", stale[2]["message"])
        self.assertEqual(400, self.request("POST", "/api/model-hub/profile", {
            "ack": "SAVE_MODEL_PROFILE", "expected_revision": 1,
            "profile": {**local_profile(), "api_key": "must-not-save"}}, {
                "Cookie": cookie, "X-CSRF-Token": csrf})[0])


if __name__ == "__main__":
    unittest.main()
