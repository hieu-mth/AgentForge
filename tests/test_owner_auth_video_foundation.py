"""Owner HTTP security regression independent of removed Webapp/NovaMart fixtures."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge.api.server import create_server


class OwnerAuthVideoFoundationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.code = "owner-video-foundation-test-secret"
        self.root = root
        self.server = create_server(0, owner_code=self.code)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 3)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.cookie = ""
        self.csrf = ""

    def request(self, method, path, payload=None, *, csrf=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=8)
        headers = {"Host": self.host}
        if method == "POST":
            headers.update({"Origin": f"http://{self.host}", "Content-Type": "application/json"})
        if self.cookie:
            headers["Cookie"] = self.cookie
        if csrf and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        try:
            conn.request(method, path,
                         body=json.dumps(payload or {}) if method == "POST" else None,
                         headers=headers)
            response = conn.getresponse()
            raw = response.read()
            try:
                body = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                body = raw
            return response.status, body, dict(response.getheaders())
        finally:
            conn.close()

    def test_owner_session_csrf_and_logout(self):
        self.assertEqual(self.request("GET", "/api/session")[0], 401)
        self.assertEqual(self.request("GET", "/api/video-studio/projects")[0], 401)
        status, result, headers = self.request("POST", "/api/login", {"code": self.code})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = result["csrf"]
        status, session, _ = self.request("GET", "/api/session")
        self.assertEqual(status, 200)
        self.assertEqual(session["csrf"], self.csrf)
        self.assertEqual(self.request("POST", "/api/logout", {}, csrf=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/logout", {})[0], 200)
        self.assertEqual(self.request("GET", "/api/session")[0], 401)

    def test_flux_profile_api_persists_only_valid_comfy_configuration(self):
        from agentforge.ai import model_hub
        from tests.test_flux_runtime import profile

        _, login, headers = self.request("POST", "/api/login", {"code": self.code})
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = login["csrf"]
        row = profile()
        row.update(id="flux_schnell_gguf", model="flux1-schnell-Q4_K_S.gguf")
        row["flux"]["workflow"]["38"]["inputs"]["unet_name"] = row["model"]
        endpoint = "/api/model-hub/profile"
        body = {"ack": "SAVE_MODEL_PROFILE", "expected_revision": 0, "profile": row}
        db = self.root / "hub.sqlite3"
        with patch.object(model_hub, "DB_PATH", db):
            for fields in ({"workflow": {}}, {"api_key": "fixture-private"},
                           {"api_key_protected": "opaque"}, {"provider": "ollama"}):
                status, _, _ = self.request("POST", endpoint, body | {"profile": row | fields})
                self.assertEqual(status, 400, fields.keys())
            status, created, _ = self.request("POST", endpoint, body)
            self.assertEqual(status, 200, created)
            self.assertEqual(created["profiles"][0]["flux"], row["flux"])
            revised = row | {"flux": row["flux"] | {"timeout_seconds": 45}}
            status, edited, _ = self.request("POST", endpoint, body | {
                "profile": revised, "expected_revision": 1})
            self.assertEqual(status, 200, edited)
            status, loaded, _ = self.request("GET", "/api/model-hub")
        self.assertTrue(db.is_file())
        self.assertEqual(status, 200)
        self.assertEqual(loaded["revision"], 2)
        self.assertEqual(loaded["profiles"][0]["flux"], revised["flux"])

    def test_draft_collection_missing_id_and_broken_sqlite_have_distinct_statuses(self):
        from agentforge.features.film_studio import draft_pipeline as drafts

        _, login, headers = self.request("POST", "/api/login", {"code": self.code})
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = login["csrf"]
        self.server.allow_external_actions = True
        endpoint = "/api/film/drafts"
        identifier = "a" * 32
        db = self.root / "drafts.sqlite3"
        brief = {"idea": "Mèo cam tìm đường về", "seconds": 6, "scene_count": 2, "ratio": "16:9"}
        with patch.object(drafts, "DB", db):
            self.assertEqual(self.request("GET", endpoint)[:2], (200, {"drafts": []}))
            self.assertFalse(db.exists())
            self.assertEqual(self.request("GET", endpoint + "/" + identifier)[:2],
                             (404, {"error": "draft_not_found"}))
            self.assertEqual(self.request("POST", endpoint + "/" + identifier + "/resume")[:2],
                             (404, {"error": "draft_not_found"}))
            self.assertEqual(self.request("GET", "/api/film/unknown")[:2], (404, {"error": "not_found"}))
            db.write_bytes(b"broken database fixture")
            status, error, _ = self.request("GET", endpoint)
            self.assertEqual((status, error["error"]), (503, "draft_storage_unavailable"))
            self.assertEqual(db.read_bytes(), b"broken database fixture")

        def checkpoint(job, slot):
            try:
                drafts._save({**job, "status": "FAILED", "stage": "STORYBOARD"})
            finally:
                slot.__exit__(None, None, None)
                done.set()

        done = threading.Event()
        with (patch.object(drafts, "DB", self.root / "fresh.sqlite3"),
              patch.object(drafts.model_hub, "draft_routes", return_value=(1, {})),
              patch.object(drafts.render, "_ffmpeg"),
              patch.object(drafts, "_work", side_effect=checkpoint),
              patch.object(drafts, "ACTIVE", None)):
            status, created, _ = self.request("POST", endpoint + "/start", {"id": identifier, **brief})
            self.assertEqual((status, created["status"]), (200, "RUNNING"))
            self.assertTrue(done.wait(3))
            restored = self.request("GET", endpoint)[1]["drafts"]
            self.assertEqual([(row["id"], row["stage"]) for row in restored], [(identifier, "STORYBOARD")])
            done.clear()
            status, resumed, _ = self.request("POST", endpoint + "/" + identifier + "/resume")
            self.assertEqual((status, resumed["id"], resumed["stage"]), (200, identifier, "STORYBOARD"))
            self.assertTrue(done.wait(3))

    def test_dashboard_redirect_and_retired_routes_are_not_exposed(self):
        status, _, headers = self.request("GET", "/")
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("Location"), "/dashboard/")
        status, result, headers = self.request("POST", "/api/login", {"code": self.code})
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = result["csrf"]
        for route in ("/api/mattress", "/api/growth/old",
                      "/api/webapps/old", "/api/proposals/old",
                      "/api/visuals/website/old"):
            with self.subTest(route=route):
                self.assertEqual(self.request("GET", route)[0], 404)

    def test_retired_goal_and_campaign_entrypoints_do_not_create_state(self):
        status, login, headers = self.request("POST", "/api/login", {"code": self.code})
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = login["csrf"]
        for path, data in (
            ("/api/goals/propose", {"ack": "PROPOSE", "title": "Old website",
                                    "template": "website.draft", "inputs": {}}),
            ("/api/goals/preflight", {"ack": "PREFLIGHT",
                                      "template": "growth.review", "inputs": {}}),
            ("/api/schedules/create", {"ack": "SCHEDULE", "title": "Legacy",
                                        "template": "media.produce", "inputs": {}}),
            ("/api/campaigns/create", {"ack": "CREATE_CAMPAIGN", "data": {}}),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.request("POST", path, data)[0], 400)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_composite_cannot_wrap_retired_website_step(self):
        status, login, headers = self.request("POST", "/api/login", {"code": self.code})
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = login["csrf"]
        body = {"ack": "PROPOSE", "title": "Hidden website builder",
                "template": "workflow.compose",
                "inputs": {"steps": [
                    {"template": "website.draft",
                     "inputs": {"slug": "legacy-site", "brief": "old builder"}}
                ]}}
        status, reply, _ = self.request("POST", "/api/goals/propose", body)
        self.assertEqual(status, 400)
        self.assertIn("Unknown mutation route", reply["message"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_character_registry_get_does_not_create_owner_database(self):
        db = self.root / "owner" / "characters.sqlite3"
        status, login, headers = self.request("POST", "/api/login", {"code": self.code})
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = login["csrf"]
        with patch.dict("os.environ", {"AGENTFORGE_CHARACTER_DB": str(db)}):
            status, response, _ = self.request("GET", "/api/characters")
        self.assertEqual(status, 200)
        self.assertEqual(response, {"characters": []})
        self.assertFalse(db.parent.exists())

    def test_film_inventory_requires_authentication(self):
        self.assertEqual(self.request("GET", "/api/film/productions")[0], 401)
        self.assertEqual(self.request("GET", "/api/characters")[0], 401)
        self.assertEqual(self.request("GET", "/api/model-hub")[0], 401)


if __name__ == "__main__":
    unittest.main()
