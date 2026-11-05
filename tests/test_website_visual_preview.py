"""Website visual preview — real isolated localhost route, no mutation/no script."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import control_center_v1 as cc
from agentforge import product_builder as b
from agentforge.website_preview import from_proposal

OWNER = "test-owner-code-for-preview"
GOOD = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<style>body{background:#eef1e8;color:#123;font-family:Arial}</style>'
        '<title>Nệm êm nhà</title></head><body><main>'
        '<h1>Nệm êm nhà</h1><p>Gọi 0879547988 để được tư vấn.</p>'
        '</main></body></html>')


class WebsiteVisualPreviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patchers = [
            patch.object(b, "ROOT", self.root),
            patch.object(b, "WORKSPACE", self.root / "workspace"),
            patch.object(b, "PRODUCTS", self.root / "workspace" / "products"),
            patch.object(b, "PROPOSALS", self.root / "data" / "company" / "product_builder" / "proposals"),
        ]
        for entry in patchers:
            entry.start()
            self.addCleanup(entry.stop)
        self.brief = "Trang giới thiệu nệm cho gia đình với hotline 0879547988."
        self.proposal = b.propose("nem-em-nha", self.brief,
                                  model_client=lambda *_a, **_k: {
                                      "summary": "Safe local website draft",
                                      "files": [{"path": "index.html", "content": GOOD}]
                                  })
        self.server = cc.create_server(
            0, owner_code=OWNER,
            task_db_path=self.root / "tasks.db",
            brain_db_path=self.root / "brain.db",
            analytics_db_path=self.root / "analytics.db",
            growth_db_path=self.root / "growth.db")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.route = "/api/proposals/" + self.proposal["proposal_id"] + "/preview"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(4)

    def request(self, path, cookie=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=8)
        headers = {"Host": self.host}
        if cookie:
            headers["Cookie"] = cookie
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        status, meta, body = resp.status, dict(resp.getheaders()), resp.read()
        conn.close()
        return status, meta, body

    def login(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=8)
        conn.request("POST", "/api/login", body=json.dumps({"code": OWNER}),
                     headers={"Host": self.host,
                              "Origin": "http://" + self.host,
                              "Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(200, resp.status)
        cookie = resp.getheader("Set-Cookie").split(";", 1)[0]
        resp.read()
        conn.close()
        return cookie

    def test_preview_is_auth_required_and_not_applied(self):
        code, _, _ = self.request(self.route)
        self.assertEqual(401, code)
        cookie = self.login()
        code, headers, body = self.request(self.route, cookie)
        self.assertEqual(200, code)
        self.assertEqual("text/html; charset=utf-8", headers["Content-Type"])
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        self.assertIn("script-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("connect-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'self'", headers["Content-Security-Policy"])
        self.assertNotIn("X-Frame-Options", headers)
        self.assertIn("0879547988", body.decode("utf-8"))
        self.assertIn("<style>", body.decode("utf-8"))
        self.assertFalse(b.PRODUCTS.exists())
        self.assertEqual(body, from_proposal(self.proposal["proposal_id"]))
        other_status, _, _ = self.request("/api/proposals/" + "c" * 32 + "/preview", cookie)
        self.assertEqual(404, other_status)

    def test_unchanged_normal_csp(self):
        cookie = self.login()
        _, headers, _ = self.request("/", cookie)
        self.assertEqual("DENY", headers["X-Frame-Options"])
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn("frame-src 'self'", headers["Content-Security-Policy"])

    def test_digest_change_refuses_preview(self):
        path = Path(self.proposal["proposal_path"])
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["files"][0]["content"] = doc["files"][0]["content"].replace("0879547988", "0000000000")
        path.write_text(json.dumps(doc), encoding="utf-8")
        cookie = self.login()
        status, _, _ = self.request(self.route, cookie)
        self.assertEqual(404, status)
        self.assertFalse(b.PRODUCTS.exists())


if __name__ == "__main__":
    unittest.main()
