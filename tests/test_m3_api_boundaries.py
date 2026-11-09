"""M0/M3 freezes Owner HTTP behavior while server is split into modules."""
from __future__ import annotations

import ast
import http.client
import threading
import unittest
from pathlib import Path

from agentforge import control_center_v1 as legacy


ROOT = Path(__file__).resolve().parents[1]


class OwnerHttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.server = legacy.create_server(port=0, owner_code="a" * 24)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=4)

    def request(self, method, path, body=None, extra=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Origin": f"http://127.0.0.1:{self.port}"}
        if extra:
            headers.update(extra)
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        result = (response.status, dict(response.getheaders()),
                  response.read())
        conn.close()
        return result

    def test_server_remains_loopback_and_untrusted_routes_denied(self):
        self.assertEqual("127.0.0.1", self.server.server_address[0])
        code, headers, _ = self.request("GET", "/")
        self.assertEqual(302, code)
        self.assertEqual("/dashboard/", headers["Location"])
        code, headers, _ = self.request("GET", "/api/bootstrap")
        self.assertEqual(401, code)
        self.assertIn("Content-Security-Policy", headers)
        self.assertEqual("nosniff", headers["X-Content-Type-Options"])
        self.assertEqual(405, self.request("PUT", "/api/bootstrap")[0])
        self.assertEqual(403, self.request(
            "GET", "/api/session", extra={"Host": "attacker.example"})[0])

    def test_login_csrf_and_logout_contract(self):
        import json
        body = lambda obj: json.dumps(obj).encode("utf-8")
        hdr = {"Content-Type": "application/json"}
        bad = self.request("POST", "/api/login", body({"code": "wrong"}), hdr)
        self.assertEqual(401, bad[0])
        ok = self.request("POST", "/api/login", body({"code": "a" * 24}), hdr)
        self.assertEqual(200, ok[0])
        cookie = ok[1]["Set-Cookie"].split(";", 1)[0]
        csrf = json.loads(ok[2])["csrf"]
        self.assertIn("HttpOnly", ok[1]["Set-Cookie"])
        self.assertIn("SameSite=Strict", ok[1]["Set-Cookie"])
        self.assertEqual(403, self.request("POST", "/api/logout", b"{}", {
            **hdr, "Cookie": cookie})[0])
        self.assertEqual(403, self.request("POST", "/api/logout", b"{}", {
            **hdr, "Cookie": cookie, "X-CSRF-Token": csrf,
            "Origin": "http://attacker.example"})[0])
        self.assertEqual(200, self.request("GET", "/api/session", extra={
            "Cookie": cookie})[0])
        self.assertEqual(200, self.request("POST", "/api/logout", b"{}", {
            **hdr, "Cookie": cookie, "X-CSRF-Token": csrf})[0])
        self.assertEqual(401, self.request("GET", "/api/session", extra={
            "Cookie": cookie})[0])


class ApiImportBoundaryTests(unittest.TestCase):
    def test_business_modules_do_not_import_transport(self):
        for folder in ("core", "ai", "domains", "storage"):
            for path in (ROOT / "agentforge" / folder).rglob("*.py"):
                with self.subTest(path=str(path.relative_to(ROOT))):
                    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            names = [name.name for name in node.names]
                        elif isinstance(node, ast.ImportFrom):
                            names = [node.module or ""]
                        else:
                            continue
                        self.assertFalse(any(
                            name == "agentforge.api" or
                            name.startswith("agentforge.api.")
                            for name in names),
                            f"{path} imports the HTTP transport layer")

    def test_legacy_entrypoints_share_canonical_implementation(self):
        from agentforge.api import server
        from agentforge.api.routes import mutations
        self.assertIs(legacy.create_server, server.create_server)
        self.assertIs(legacy._owner_action, mutations._owner_action)


if __name__ == "__main__":
    unittest.main()
