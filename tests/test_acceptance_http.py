"""Authenticated Owner decisions, with no client-supplied QA bypass."""
import unittest
import tests.test_webapp_revision_http_v41 as http_fixture


class AcceptanceHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture = http_fixture.WebappRevisionHttpTests("test_get_requires_login_and_allows_signed_source_review")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.pid = self.fixture.proposal["proposal_id"]
        self.sha = self.fixture.proposal["sha256"]
        self.path = "/api/artifacts/webapps/" + self.pid + "/decision"

    def test_auth_review_csrf_and_no_static_only_acceptance(self):
        body = {"ack": "ACCEPT_ARTIFACT", "sha256": self.sha, "expected_revision": 0, "evidence_sha": "0" * 64}
        self.assertEqual(self.fixture.req("POST", self.path, body)[0], 401)
        self.fixture.login()
        self.assertEqual(self.fixture.req("POST", self.path, body, csrf=False)[0], 403)
        self.assertEqual(self.fixture.req("POST", self.path, body)[0], 400)  # No source inspection.
        status, proposal, _ = self.fixture.req("GET", "/api/webapps/" + self.pid)
        self.assertEqual(status, 200)
        view = proposal["artifact_acceptance"]
        body.update(expected_revision=view["revision"], evidence_sha=view["evidence_sha"])
        self.assertEqual(self.fixture.req("POST", self.path, body)[0], 400)  # Missing runtime QA.
        self.assertEqual(self.fixture.req("POST", self.path, {**body, "build_verified": True})[0], 400)
        body["ack"] = "REJECT_ARTIFACT"
        status, outcome, _ = self.fixture.req("POST", self.path, body)
        self.assertEqual(status, 200, outcome)
        self.assertEqual(outcome["status"], "REJECTED")
        self.assertEqual(self.fixture.req("POST", self.path, body)[0], 400)
        self.assertEqual(self.fixture.req("GET", "/api/webapps/" + self.pid)[1]["artifact_acceptance"]["status"], "REJECTED")

    def test_syntax_validation_is_source_bound_and_never_claims_runtime(self):
        self.fixture.login()
        self.fixture.req("GET", "/api/webapps/" + self.pid)
        path = "/api/artifacts/webapps/" + self.pid + "/syntax"
        self.assertEqual(self.fixture.req("POST", path, {"ack": "VALIDATE_SYNTAX", "sha256": "0" * 64})[0], 400)
        status, result, _ = self.fixture.req("POST", path, {"ack": "VALIDATE_SYNTAX", "sha256": self.sha})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["syntax"]["source_sha"], self.sha)
        self.assertFalse(result["syntax"]["build_verified"])
        self.assertFalse(result["syntax"]["browser_verified"])
        self.assertEqual(result["artifact_acceptance"]["status"], "NEEDS_VALIDATION")
