import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import evidence_registration, owner_review, task_inbox
from agentforge.evidence_registry import valid_references
from agentforge.evaluation import default_inputs, evaluate


class TestEvidenceRegistration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.company = self.root / "company"
        self.opportunities = self.root / "opportunities"
        self.task_id = "a" * 32 + "-source-review"
        self.url = "https://example.org/article"
        self.quote = "A paid Excel service is advertised for local shops."

        self.patches = [
            patch.object(task_inbox, "DATA_DIR", self.company),
            patch.object(evidence_registration, "OPPORTUNITIES", self.opportunities),
        ]
        for item in self.patches:
            item.start()

        self.task = {
            "task_id": self.task_id,
            "opportunity_id": "research-aaaaaaaa",
            "kind": "SOURCE_REVIEW",
            "status": "PROPOSED",
            "source_urls": [self.url],
            "execution_authorized": False,
            "spending_authorized": False,
        }
        self.candidate = {
            "candidate_id": "C1",
            "source_url": self.url,
            "field": "paid_alternative",
            "statement": "An online business advertises a paid service",
            "quote": self.quote,
            "quote_status": "MATCHED_IN_PAGE",
            "independently_verified": False,
            "owner_reviewed": False,
            "supports": [],
        }
        self.handoff = {
            "task_id": self.task_id,
            "opportunity_id": "research-aaaaaaaa",
            "status": "PENDING_OWNER_REVIEW",
            "owner_reviewed": False,
            "execution_authorized": False,
            "spending_authorized": False,
            "source_review_file": f"reviews/{self.task_id}.json",
            "candidates": [self.candidate],
        }
        self.report = {
            "task_id": self.task_id,
            "opportunity_id": "research-aaaaaaaa",
            "review_status": "QUOTE_REVIEW_ONLY",
            "customer_demand_verified": False,
            "revenue_verified": False,
            "execution_authorized": False,
            "spending_authorized": False,
            "source_reviews": [{
                "url": self.url,
                "status": "QUOTES_CHECKED_NOT_FACT_CHECKED",
                "observations": [{
                    "field": self.candidate["field"],
                    "statement": self.candidate["statement"],
                    "quote": self.quote,
                    "quote_status": "MATCHED_IN_PAGE",
                    "independently_verified": False,
                }],
            }],
        }
        self.task_path = task_inbox.task_path(self.task_id)
        self.task_path.parent.mkdir(parents=True, exist_ok=True)
        self.handoff_path = self.company / "evidence_candidates" / f"{self.task_id}.json"
        self.handoff_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path = self.company / "reviews" / f"{self.task_id}.json"
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.save()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def save(self):
        for path, document in (
            (self.task_path, self.task),
            (self.handoff_path, self.handoff),
            (self.report_path, self.report),
        ):
            path.write_text(json.dumps(document), encoding="utf-8")

    def approve(self):
        return owner_review.decide(
            self.task_id, "C1", "approve",
            "I inspected the original source text and its context.",
            scope="differentiation", confirm=True,
        )

    def register(self):
        return evidence_registration.register_evidence(self.task_id, "C1")

    def test_registration_creates_valid_local_evidence(self):
        decision_path = self.approve()
        decision_original = decision_path.read_bytes()
        result = self.register()
        index = json.loads((self.opportunities / "evidence_index.json").read_text())
        evidence_path = Path(result["source_file"])
        artifact = json.loads(evidence_path.read_text())

        self.assertTrue(valid_references(
            [result["reference"]], "differentiation", index,
            self.opportunities / "evidence",
        ))
        self.assertEqual(artifact["quote"], self.quote)
        self.assertFalse(artifact["independently_verified"])
        self.assertTrue(artifact["manual_review_confirmed"])
        self.assertFalse(artifact["execution_authorized"])
        self.assertFalse(artifact["spending_authorized"])
        self.assertEqual(decision_path.read_bytes(), decision_original)

    def test_registration_never_triggers_go(self):
        self.approve()
        result = self.register()
        index = json.loads((self.opportunities / "evidence_index.json").read_text())
        inputs = default_inputs()
        inputs["checks"]["differentiation"] = {
            "status": "SUPPORTED", "evidence_refs": [result["reference"]],
        }
        decision = evaluate(
            inputs, {"competitors": []}, index,
            self.opportunities / "evidence",
        )
        self.assertEqual(decision["decision"], "RESEARCH_MORE")
        self.assertFalse(decision["execution_authorized"])

    def test_rejected_decision_cannot_register(self):
        owner_review.decide(self.task_id, "C1", "reject", "Not enough evidence available.")
        with self.assertRaises(ValueError):
            self.register()

    def test_missing_decision_cannot_register(self):
        with self.assertRaises(FileNotFoundError):
            self.register()

    def test_manual_confirmation_cannot_be_removed(self):
        path = self.approve()
        doc = json.loads(path.read_text())
        doc["manual_review_confirmed"] = False
        path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            self.register()

    def test_weak_quote_cannot_be_reclassified_as_payment_proof(self):
        path = self.approve()
        doc = json.loads(path.read_text())
        doc["scope"] = "willingness_to_pay"
        path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            self.register()

    def test_changed_candidate_quote_cannot_register(self):
        self.approve()
        self.candidate["quote"] = "A modified quote intended to replace the approved source."
        self.save()
        with self.assertRaises(ValueError):
            self.register()

    def test_changed_review_quote_cannot_register(self):
        self.approve()
        self.report["source_reviews"][0]["observations"][0]["quote"] = (
            "This different quote was never approved by the owner."
        )
        self.save()
        with self.assertRaises(ValueError):
            self.register()

    def test_duplicate_registration_never_overwrites(self):
        self.approve()
        result = self.register()
        source = Path(result["source_file"])
        index = self.opportunities / "evidence_index.json"
        initial = (source.read_bytes(), index.read_bytes())
        with self.assertRaises(FileExistsError):
            self.register()
        self.assertEqual((source.read_bytes(), index.read_bytes()), initial)

    def test_existing_registry_entries_are_preserved(self):
        self.approve()
        self.opportunities.mkdir(parents=True)
        old_record = {"owner_reviewed": True, "supports": ["distribution"], "source_file": "prior.json"}
        (self.opportunities / "evidence_index.json").write_text(
            json.dumps({"records": {"owner-reviewed:prior": old_record}}),
            encoding="utf-8",
        )
        self.register()
        index = json.loads((self.opportunities / "evidence_index.json").read_text())
        self.assertEqual(index["records"]["owner-reviewed:prior"], old_record)
        self.assertEqual(len(index["records"]), 2)

    def test_invalid_existing_registry_fails_without_writing(self):
        self.approve()
        self.opportunities.mkdir(parents=True)
        (self.opportunities / "evidence_index.json").write_text(
            '{"records": []}', encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(list((self.opportunities / "evidence").glob("*.json")), [])

    def test_invalid_candidate_id_cannot_escape_directory(self):
        with self.assertRaises(ValueError):
            evidence_registration.register_evidence(self.task_id, "../C1")

    def test_report_cannot_claim_verified_customer_demand(self):
        self.approve()
        self.report["customer_demand_verified"] = True
        self.save()
        with self.assertRaises(ValueError):
            self.register()

    def test_invalid_source_review_provenance_is_rejected(self):
        self.approve()
        self.report["execution_authorized"] = True
        self.save()
        with self.assertRaises(ValueError):
            self.register()


if __name__ == "__main__":
    unittest.main()
