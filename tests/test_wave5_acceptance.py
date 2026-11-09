"""Wave 5 Base acceptance checks never give mocked CI a false production GO."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge.ops import base_acceptance


def environment(status="READY_LOCAL_UNVERIFIED"):
    return {"status": status}


def health(status="PASS"):
    return {"status": status, "registry_valid": True, "backup_count": 1}


def models(status="ROUTED"):
    return {"routes": [
        {"kind": "text", "execution": "wired", "status": status},
        {"kind": "video", "execution": "config_only", "status": "CONFIG_ONLY"},
    ]}


class Wave5BaseAcceptanceTests(unittest.TestCase):
    def test_configured_local_baseline_never_claims_real_model_or_prod_go(self):
        record = base_acceptance.inspect(
            environment=environment(), health=health(), models=models())
        self.assertEqual(record["status"], "OWNER_REVIEW_REQUIRED")
        self.assertEqual(record["text_routes_configured"], 1)
        self.assertEqual(record["text_routes_expected"], 1)
        self.assertEqual(record["backup_count"], 1)
        self.assertFalse(record["production_go"])
        self.assertFalse(record["owner_machine_verified"])
        self.assertFalse(record["generated_artifact_qa_verified"])
        self.assertFalse(record["network_called"])
        self.assertFalse(record["local_data_modified"])
        self.assertEqual(
            {r["id"] for r in record["checks"] if r["status"] == "UNVERIFIED"},
            {"owner_login_dashboard_real_machine", "model_inference_real_machine",
             "task_approval_artifact_real_machine", "backup_restore_real_machine"})

    def test_missing_configs_or_bad_database_block_readiness(self):
        for setup, doctor, route in [
            (environment("BLOCKED"), health(), models()),
            (environment(), health("FAIL"), models()),
            (environment(), health(), models("INVALID_CONFIG")),
            (environment(), health(), {"routes": []}),
        ]:
            with self.subTest(setup=setup, doctor=doctor, route=route):
                result = base_acceptance.inspect(
                    environment=setup, health=doctor, models=route)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertTrue(any(x["status"] == "FAIL" for x in result["checks"]))
                self.assertFalse(result["production_go"])

    def test_missing_backup_is_review_not_false_failure(self):
        result = base_acceptance.inspect(
            environment=environment("REVIEW_REQUIRED"),
            health={"status": "REVIEW_REQUIRED", "backup_count": 0},
            models=models())
        self.assertEqual(result["status"], "OWNER_REVIEW_REQUIRED")
        self.assertEqual(result["backup_count"], 0)
        self.assertEqual(result["checks"][1]["status"], "REVIEW_REQUIRED")

    def test_exceptions_hide_runtime_errors_and_never_emit_secrets(self):
        with patch.object(base_acceptance.preflight, "inspect",
                          side_effect=ValueError("owner private data")):
            with patch.object(base_acceptance.ops_doctor, "inspect",
                              side_effect=ValueError("local password")):
                with patch.object(base_acceptance.model_hub, "catalog",
                                  side_effect=ValueError("secret")):
                    result = base_acceptance.inspect()
        self.assertEqual(result["status"], "BLOCKED")
        serialized = json.dumps(result)
        for sensitive in ("owner private data", "local password", "secret"):
            self.assertNotIn(sensitive, serialized)

    def test_corrupt_sqlite_state_degrades_to_fail_closed_report(self):
        import sqlite3
        with patch.object(base_acceptance.preflight, "inspect",
                          return_value=environment()), \
             patch.object(base_acceptance.ops_doctor, "inspect",
                          side_effect=sqlite3.DatabaseError("private sqlite contents")), \
             patch.object(base_acceptance.model_hub, "catalog",
                          side_effect=sqlite3.DatabaseError("private model path")):
            result = base_acceptance.inspect()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertNotIn("private", json.dumps(result))

    def test_readonly_cli_works_with_cp1252_stdout(self):
        record = base_acceptance.inspect(
            environment=environment(), health=health(), models=models())
        stream = io.BytesIO()
        writer = io.TextIOWrapper(stream, encoding="cp1252", write_through=True)
        with patch.object(base_acceptance, "inspect", return_value=record), \
             patch.object(sys, "argv", ["base_acceptance"]), \
             patch.object(sys, "stdout", writer):
            base_acceptance.main()
        self.assertEqual(json.loads(stream.getvalue().decode("ascii")), record)

    def test_analytics_cli_datasets_cp1252_non_ascii_names(self):
        from agentforge import analytics_pipeline
        stream = io.BytesIO()
        writer = io.TextIOWrapper(stream, encoding="cp1252", write_through=True)
        with patch.object(analytics_pipeline.store, "list_datasets",
                          return_value=[{"dataset": "kế hoạch nội địa"}]), \
             patch.object(sys, "argv", ["analytics_pipeline", "datasets"]), \
             patch.object(sys, "stdout", writer):
            analytics_pipeline.main()
        body = json.loads(stream.getvalue().decode("ascii"))
        self.assertEqual(body["datasets"][0]["dataset"], "kế hoạch nội địa")

    def test_owner_api_requires_real_session_for_health_and_models(self):
        from tests.test_webapp_revision_http_v41 import WebappRevisionHttpTests
        fixture = WebappRevisionHttpTests(
            "test_get_requires_login_and_allows_signed_source_review")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        for endpoint in ("/api/bootstrap", "/api/model-hub",
                         "/api/ops/health", "/api/ops/preflight",
                         "/api/ops/acceptance"):
            self.assertEqual(fixture.req("GET", endpoint)[0], 401)
        fixture.login()
        with patch("agentforge.ops_doctor.inspect",
                   return_value={"status": "PASS", "backup_count": 1}):
            for endpoint in ("/api/bootstrap", "/api/model-hub",
                             "/api/ops/health", "/api/ops/preflight"):
                status, payload, _ = fixture.req("GET", endpoint)
                self.assertEqual(status, 200, (endpoint, payload))
        csrf_bad, _, _ = fixture.req(
            "POST", "/api/ops/control", {"mode": "PAUSED",
                                         "ack": "PAUSE_OPERATIONS"}, csrf=False)
        self.assertEqual(csrf_bad, 403)
        bad_ack, _, _ = fixture.req(
            "POST", "/api/ops/control", {"mode": "PAUSED", "ack": "nope"})
        self.assertEqual(bad_ack, 400)


if __name__ == "__main__":
    unittest.main()
