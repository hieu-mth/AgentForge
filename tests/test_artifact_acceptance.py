"""Acceptance gates, provenance, legacy safety and concurrent Owner decisions."""
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from agentforge import webapp_developer as dev, task_history, brain_store, brain_runner
from agentforge.core import artifact_acceptance as acceptance
from tests.test_webapp_developer_v42b import MODEL, BRIEF
import tests.test_v5_company as v5


class ArtifactAcceptanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.db = self.folder / "tasks.db"
        for module, field, value in [(dev, "PROPOSALS", self.folder / "proposals"),
                                      (dev, "PROJECTS", self.folder / "projects")]:
            context = patch.object(module, field, value)
            context.start()
            self.addCleanup(context.stop)
        with patch("agentforge.model.generate_json", return_value=MODEL):
            self.proposal = dev.propose("acceptance-app", BRIEF)
        self.pid, self.sha = self.proposal["proposal_id"], self.proposal["sha256"]

    def report(self, kind, outcome="PASS", tag=None):
        acceptance.record_validation(self.pid, self.sha, "react_ai", kind, outcome,
                                     tag or kind + outcome, db_path=self.db)

    def view(self):
        return acceptance.inspect(self.pid, self.sha, db_path=self.db)

    def complete(self):
        for kind in acceptance.POLICIES["react_ai"]:
            self.report(kind)

    def decide(self, view, decision="ACCEPTED", confirm=True):
        return acceptance.decide(self.pid, self.sha, "webapps", decision, confirm=confirm,
                                 expected_revision=view["revision"], evidence_sha=view["evidence_sha"],
                                 db_path=self.db)

    def test_static_only_and_build_without_browser_never_accept(self):
        self.report("CONTRACT_VALID")
        self.report("SYNTAX_VALID")
        self.assertEqual(self.view()["status"], "NEEDS_VALIDATION")
        with self.assertRaisesRegex(PermissionError, "VALIDATION_REQUIRED"):
            self.decide(self.view())
        self.report("BUILD_VALID")
        self.assertIn("BROWSER_VALID", self.view()["missing_checks"])
        self.assertFalse(self.view()["owner_accepted"])

    def test_complete_reports_require_separate_owner_action(self):
        self.complete()
        current = self.view()
        self.assertEqual(current["status"], "READY_FOR_REVIEW")
        self.assertFalse(current["owner_accepted"])
        with self.assertRaises(PermissionError):
            self.decide(current, confirm=False)
        self.assertEqual(self.decide(current)["status"], "ACCEPTED")

    def test_revise_and_each_validation_failure_block_acceptance(self):
        self.complete()
        for kind in ("SYNTAX_VALID", "BUILD_VALID", "BROWSER_VALID"):
            self.report(kind, "FAIL")
            self.assertEqual(self.view()["status"], "NEEDS_REVISION")
            with self.assertRaises(PermissionError):
                self.decide(self.view())
            self.report(kind, "PASS", kind + "fixed")
        self.report("REVIEW", "REVISE")
        self.assertEqual(self.view()["status"], "NEEDS_REVISION")
        with self.assertRaises(PermissionError):
            self.decide(self.view())

    def test_source_mismatch_and_stale_report_rejected(self):
        with self.assertRaisesRegex(PermissionError, "SOURCE_STALE"):
            acceptance.record_validation(self.pid, "0" * 64, "react_ai", "BUILD_VALID", "PASS", "wrong", db_path=self.db)
        self.complete()
        before = self.view()
        self.report("REVIEW", "REVISE")
        with self.assertRaisesRegex(PermissionError, "REVIEW_STALE"):
            self.decide(before)

    def test_new_failure_invalidates_prior_acceptance(self):
        self.complete()
        self.decide(self.view())
