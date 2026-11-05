"""Regression tests for owner-delegated proposal-only Autopilot V1.3.

No live model/provider credentials; all external model dispatch is mocked.
"""
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from agentforge import autopilot_v13 as ap


MEDIA = {"topic": "Chon nem", "audience": "Nguoi mua nem", "goal": "Tu van"}
WEB = {"slug": "nem-v13", "brief": "Trang tu van nem co tinh tham khao, khong tu dong dang."}


class AutopilotV13Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "autopilot.sqlite3"

    def enable(self, cap=2):
        return ap.configure(daily_cap=cap, enabled=True, confirm=True, db_path=self.db)

    def submit(self, skill="media.copy_draft", payload=None):
        return ap.submit(skill, payload or MEDIA, db_path=self.db)

    def test_disabled_by_default_and_explicit_delegation(self):
        self.assertFalse(ap.policy(db_path=self.db)["enabled"])
        with self.assertRaises(PermissionError):
            ap.configure(daily_cap=2, enabled=True, db_path=self.db)
        with self.assertRaises(ValueError):
            ap.configure(daily_cap=11, enabled=True, confirm=True, db_path=self.db)
        with self.assertRaises(ValueError):
            ap.configure(daily_cap=True, enabled=True, confirm=True, db_path=self.db)
        self.enable()
        self.assertEqual(2, ap.policy(db_path=self.db)["daily_cap"])
        ap.configure(daily_cap=0, enabled=False, confirm=True, db_path=self.db)
        self.assertFalse(ap.policy(db_path=self.db)["enabled"])

    def test_risky_skills_and_extra_payload_fields_rejected(self):
        for name in ("research.opportunity", "growth.record_event", "media.video_render",
                     "analytics.import", "web.browser_test"):
            with self.subTest(name=name), self.assertRaises(PermissionError):
                self.submit(name)
        with self.assertRaises(ValueError):
            self.submit(payload={**MEDIA, "confirm_external_run": True})
        with self.assertRaises(ValueError):
            self.submit("web.create", {**WEB, "publish": True})

    def test_requires_explicit_process_opt_in_and_pause(self):
        self.enable()
        self.submit()
        with self.assertRaises(PermissionError):
            ap.tick(db_path=self.db)
        with patch("agentforge.ops_control.require_active", side_effect=PermissionError("PAUSED")):
            with self.assertRaises(PermissionError):
                ap.tick(allow_model=True, db_path=self.db)
        self.assertEqual("QUEUED", ap.report(db_path=self.db)["jobs"][0]["status"])

    def test_quota_reservation_no_replay_after_failed_model(self):
        self.enable(cap=1)
        first = self.submit()
        self.submit()
        with patch("agentforge.skill_runner.invoke", return_value={
            "status": "FAILED", "task_id": "a" * 32}) as invoke:
            result = ap.tick(allow_model=True, db_path=self.db)
        self.assertEqual("FAILED", result["status"])
        self.assertEqual(1, invoke.call_count)
        self.assertEqual("DAILY_QUOTA_REACHED",
                         ap.tick(allow_model=True, db_path=self.db)["status"])
        report = ap.report(db_path=self.db)
        self.assertEqual(1, report["used_today"])
        self.assertEqual(1, sum(x["status"] == "QUEUED" for x in report["jobs"]))
        self.assertEqual(first["job_id"], result["job_id"])
        self.assertNotIn("payload_json", json.dumps(report))
        self.assertNotIn("Nguoi mua", json.dumps(report))

    def test_ambiguous_exception_remains_dispatched_without_retry(self):
        self.enable(cap=1)
        self.submit()
        with patch("agentforge.skill_runner.invoke", side_effect=RuntimeError("secret prompt leaked")):
            result = ap.tick(allow_model=True, db_path=self.db)
        self.assertEqual("INTERRUPTED_REVIEW_REQUIRED", result["status"])
        self.assertNotIn("secret", json.dumps(result))
        row = ap.report(db_path=self.db)["jobs"][0]
        self.assertEqual("DISPATCHING", row["status"])
        self.assertEqual(1, ap.report(db_path=self.db)["used_today"])
        self.assertEqual("QUEUE_EMPTY", ap.tick(allow_model=True, db_path=self.db)["status"])

    def test_only_exact_scoped_grants_model_confirmation(self):
        self.enable(cap=1)
        self.submit()
        with patch("agentforge.skill_runner.invoke", return_value={
            "status": "SUCCEEDED", "task_id": "b" * 32}) as invoked:
            result = ap.tick(allow_model=True, db_path=self.db)
        self.assertEqual("SUCCEEDED", result["status"])
        kwargs = invoked.call_args.kwargs
        self.assertEqual({"model.invoke", "workspace.propose"}, set(kwargs["grants"]))
        self.assertIs(True, kwargs["confirm_model_call"])
        self.assertNotIn("network.search", kwargs["grants"])
        self.assertNotIn("process.run", kwargs["grants"])
        self.assertTrue(result["requires_owner_review_of_output"])

    def test_two_workers_claim_distinct_jobs_without_double_spend(self):
        self.enable(cap=1)
        self.submit()
        self.submit()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: ap._claim(db_path=self.db), range(2)))
        claimed = [x for x in results if "job_id" in x]
        self.assertEqual(1, len(claimed))
        self.assertEqual(1, ap.report(db_path=self.db)["used_today"])
        self.assertEqual("DAILY_QUOTA_REACHED",
                         next(x["status"] for x in results if "job_id" not in x))

    def test_contract_drift_fails_before_reservation(self):
        self.enable(cap=1)
        self.submit()
        with patch("agentforge.skill_runner._contract",
                   side_effect=PermissionError("manifest changed")):
            with self.assertRaises(PermissionError):
                ap.tick(allow_model=True, db_path=self.db)
        report = ap.report(db_path=self.db)
        self.assertEqual(0, report["used_today"])
        self.assertEqual("QUEUED", report["jobs"][0]["status"])

    def test_waiting_owner_review_never_autoresumes(self):
        self.enable(cap=1)
        self.submit()
        with patch("agentforge.skill_runner.invoke", return_value={
            "status": "WAITING_APPROVAL", "task_id": "c" * 32}):
            result = ap.tick(allow_model=True, db_path=self.db)
        self.assertEqual("WAITING_OWNER_REVIEW", result["status"])
        self.assertEqual("QUEUE_EMPTY", ap.tick(allow_model=True, db_path=self.db)["status"])


if __name__ == "__main__":
    unittest.main()
