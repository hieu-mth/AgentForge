"""Isolated localhost Owner HTTP fixture for retained platform and Film Studio tests.

Does not create a Webapp, depend on a React template, or mutate Owner state.
"""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from agentforge.api.server import create_server

CODE = "local-owner-fixture-secret-2026"


class OwnerHttpFixture(unittest.TestCase):
    def test_noop(self):
        pass

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.brain = self.root / "brain.sqlite3"
        self.tasks = self.root / "tasks.sqlite3"
        self.server = create_server(0, owner_code=CODE)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._shutdown)
        self.host = "127.0.0.1:" + str(self.server.server_port)
        self.cookie = None
        self.csrf = None

    def _shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=4)

    def req(self, method, path, data=None, *, csrf=True, cookie=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=8)
        headers = {"Host": self.host}
        if method == "POST":
            headers["Origin"] = "http://" + self.host
            headers["Content-Type"] = "application/json"
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        if csrf and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        try:
            conn.request(method, path,
                         body=json.dumps(data or {}) if method == "POST" else None,
                         headers=headers)
            response = conn.getresponse()
            status = response.status
            meta = dict(response.getheaders())
            raw = response.read()
            try:
                output = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                output = raw.decode("utf-8", errors="replace")
            return status, output, meta
        finally:
            conn.close()

    def login(self):
        status, body, headers = self.req("POST", "/api/login", {"code": CODE})
        self.assertEqual(status, 200, body)
        self.csrf = body["csrf"]
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
