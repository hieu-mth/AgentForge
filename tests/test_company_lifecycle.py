"""Offline integration tests for the research-to-evaluation handoff."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import (
    company_flow,
    evidence_registration,
    owner_review,
    review_handoff,
    source_reader,
    source_review,
    task_inbox,
)
from agentforge.evidence_registry import valid_references_for_opportunity
from agentforge.evaluation import default_inputs, evaluate


class TestCompanyLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.reports = self.root / "research"
        self.company = self.root / "company"
        self.opportunities = self.root / "opportunities"
        self.reports.mkdir()
        self.research_id = "a" * 32
        self.url = "https://example.org/market-report"
        self.quote = "A paid Excel automation service is offered to local shops."
        self.statement = "A vendor advertises a paid automation service"
        self.patches = [
            patch.object(company_flow, "REPORTS", self.reports),
            patch.object(task_inbox, "DATA_DIR", self.company),
        ]
        for p in self.patches:
            p.start()
        report = {
            "research_id": self.research_id,
            "topic": "Excel automation opportunity",
            "status": "LEADS_ONLY_NOT_VERIFIED",
            "sources": [{"source_id": "S1", "url": self.url}],
        }
        (self.reports / f"{self.research_id}.json").write_text(
            json.dumps(report), encoding="utf-8"
        )

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def _create_review_and_stage(self):
        task = company_flow.propose_review(self.research_id, ["S1"])
        page = {
            "title": "Vendor page",
            "text_excerpt": "About our service. " + self.quote + " Contact sales.",
            "extracted_characters": 100,
        }
        output = {"observations": [
            {"field": "paid_alternative", "statement": self.statement,
             "quote": self.quote}
        ]}
        with (
            patch.object(source_review, "fetch_for_one_host", return_value=page) as fetch,
            patch.object(source_review, "generate_json", return_value=output) as model,
            patch.object(source_reader.OPENER, "open") as network,
        ):
            review = source_review.run_review(
                task["task_id"], ["example.org"],
                max_pages=1, approve_read_only=True,
            )
            fetch.assert_called_once()
            model.assert_called_once()
            network.assert_not_called()
        self.assertEqual(review["matched_quotes"], 1)
        handoff_path = review_handoff.prepare_candidates(task["task_id"])
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        self.assertEqual(handoff["status"], "PENDING_OWNER_REVIEW")
        self.assertFalse(handoff["owner_reviewed"])
        return task

    def _register(self):
        task = self._create_review_and_stage()
        decision_path = owner_review.decide(
            task["task_id"], "C1", "approve",
            "I checked the original page and the claim in context.",
            scope="differentiation", confirm=True,
        )
        decision_before = decision_path.read_bytes()
        registration = evidence_registration.register_evidence(
            task["task_id"], "C1", opportunities_dir=self.opportunities,
        )
        self.assertEqual(decision_path.read_bytes(), decision_before)
        return task, registration

    def _evaluation(self, task, registration, opportunity_id):
        index = json.loads(
            (self.opportunities / "evidence_index.json").read_text(encoding="utf-8")
        )
        inputs = default_inputs()
        inputs["opportunity_id"] = opportunity_id
        inputs["checks"]["differentiation"] = {
            "status": "SUPPORTED", "evidence_refs": [registration["reference"]],
        }
        inputs["experiment"] = {
            "budget_cap_vnd": 100_000, "owner_approved": True,
        }
        result = evaluate(
            inputs, {"competitors": []}, index,
            self.opportunities / "evidence",
        )
        return index, result

    def test_full_offline_lifecycle_still_requires_more_evidence(self):
        task, registration = self._register()
        index, result = self._evaluation(
            task, registration, task["opportunity_id"]
        )
        self.assertTrue(valid_references_for_opportunity(
            [registration["reference"]], "differentiation", index,
            self.opportunities / "evidence", task["opportunity_id"],
        ))
        self.assertEqual(result["decision"], "RESEARCH_MORE")
        self.assertNotIn("differentiation", result["missing_requirements"])
        self.assertIn("willingness_to_pay", result["missing_requirements"])
        self.assertFalse(result["execution_authorized"])
        artifact = json.loads(Path(registration["source_file"]).read_text())
        self.assertFalse(artifact["independently_verified"])
        self.assertFalse(artifact["spending_authorized"])

    def test_evidence_cannot_cross_opportunities(self):
        task, registration = self._register()
        _, result = self._evaluation(task, registration, "research-bbbbbbbb")
        self.assertEqual(result["decision"], "RESEARCH_MORE")
        self.assertIn("differentiation", result["missing_requirements"])

    def test_missing_opportunity_id_cannot_use_evidence(self):
        task, registration = self._register()
        _, result = self._evaluation(task, registration, None)
        self.assertEqual(result["decision"], "RESEARCH_MORE")
        self.assertIn("differentiation", result["missing_requirements"])

    def test_read_only_review_requires_explicit_approval(self):
        task = company_flow.propose_review(self.research_id, ["S1"])
        with patch.object(source_review, "fetch_for_one_host") as fetch:
            with self.assertRaises(PermissionError):
                source_review.run_review(task["task_id"], ["example.org"])
            fetch.assert_not_called()

    def test_registration_requires_owner_decision(self):
        task = self._create_review_and_stage()
        with self.assertRaises(FileNotFoundError):
            evidence_registration.register_evidence(
                task["task_id"], "C1", opportunities_dir=self.opportunities,
            )
        self.assertFalse((self.opportunities / "evidence_index.json").exists())


if __name__ == "__main__":
    unittest.main()
