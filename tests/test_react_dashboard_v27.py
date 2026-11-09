"""Canonical React Dashboard routes never expose source files or legacy assets."""
import http.client
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import control_center_v1 as cc


class ReactDashboardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.dist = self.root / "dist"
        (self.dist / "assets").mkdir(parents=True)
        (self.dist / "index.html").write_text('<html><div id="root">react</div></html>',
                                              encoding="utf-8")
        (self.dist / "assets" / "main-abc123.js").write_text(
            'console.log("safe react bundle")', encoding="utf-8")
        (self.dist / "assets" / "main-abc123.css").write_text(
            'body{color:#000}', encoding="utf-8")
        self.patch = patch.object(cc, "REACT_DIST", self.dist)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.server = cc.create_server(port=0, owner_code="test-owner-code-1234",
                                       task_db_path=self.root / "tasks.db",
                                       brain_db_path=self.root / "goals.db",
                                       analytics_db_path=self.root / "analytics.db",
                                       growth_db_path=self.root / "growth.db")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def get(self, route):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=6)
        conn.request("GET", route, headers={"Host": f"127.0.0.1:{self.server.server_port}"})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_dashboard_and_hashed_assets_serve_without_auth_and_keep_csp(self):
        code, headers, body = self.get("/dashboard/")
        self.assertEqual(200, code)
        self.assertIn(b'id="root"', body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertIn("style-src 'self' 'unsafe-inline'", headers["Content-Security-Policy"])
        self.assertEqual("DENY", headers["X-Frame-Options"])
        code, headers, body = self.get("/dashboard/assets/main-abc123.js")
        self.assertEqual(200, code)
        self.assertIn(b"safe react bundle", body)
        self.assertEqual("text/javascript; charset=utf-8", headers["Content-Type"])
        code, _, body = self.get("/dashboard/assets/main-abc123.css")
        self.assertEqual(200, code)
        self.assertIn(b"color", body)

    def test_root_redirects_to_react_and_legacy_assets_are_removed(self):
        code, headers, body = self.get("/")
        self.assertEqual(302, code)
        self.assertEqual("/dashboard/", headers["Location"])
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertEqual(b"", body)
        for route in ("/app.js", "/app.css", "/app.html"):
            code, headers, _ = self.get(route)
            self.assertEqual(404, code)
            self.assertEqual("nosniff", headers["X-Content-Type-Options"])

    def test_no_source_file_or_traversal_access(self):
        for route in (
            "/dashboard/assets/../../data/secret.sqlite3",
            "/dashboard/assets/.env",
            "/dashboard/src/App.jsx",
            "/dashboard/vite.config.js",
            "/dashboard/node_modules/react/index.js",
            "/dashboard/assets/a.js/../../.env",
        ):
            with self.subTest(route=route):
                code, _, _ = self.get(route)
                self.assertIn(code, (401, 404))

    def test_missing_build_and_symlink_fail_closed(self):
        (self.dist / "index.html").unlink()
        status, _, _ = self.get("/dashboard/")
        self.assertEqual(404, status)
        (self.dist / "index.html").write_text("ok", encoding="utf-8")
        with patch.object(cc, "REACT_ASSET_RE") as matcher:
            matcher.fullmatch.return_value = None
            status, _, _ = self.get("/dashboard/assets/main-abc123.js")
            self.assertEqual(404, status)


if __name__ == "__main__":
    unittest.main()
