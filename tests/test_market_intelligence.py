"""C6C: market intelligence is not GO/KILL evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import evidence_registration, owner_review, task_inbox
from agentforge.evaluation import default_inputs, evaluate


class TestMarketIntelligence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.company = self.root / "company"
        self.opportunities = self.root / "opportunities"
        self.task_id = "a" * 32 + "-source-review"
        self.url = "https://example.org/services"
        self.patches = [
            patch.object(task_inbox, "DATA_DIR", self.company),
            patch.object(evidence_registration, "OPPORTUNITIES", self.opportunities),
        ]
        for p in self.patches:
            p.start()
        self.candidates = [
            {
                "candidate_id": cid,
                "source_url": self.url,
                "field": field,
                "statement": statement,
                "quote": quote,
                "quote_status": "MATCHED_IN_PAGE",
                "independently_verified": False,
                "owner_reviewed": False,
                "supports": [],
            }
            for cid, field, statement, quote in [
                ("C1", "customer_pain", "Vendor claims customers struggle",
                 "Manual re-entry of orders is tiring and may cause errors."),
                ("C2", "price", "Vendor lists Basic price",
                 "Basic spreadsheet service is listed at 1.5m to 3m VND."),
                ("C3", "paid_alternative", "Vendor advertises paid automation",
                 "We sell a paid automation service for online businesses."),
            ]
        ]
        task = {
            "task_id": self.task_id,
            "opportunity_id": "research-aaaaaaaa",
            "kind": "SOURCE_REVIEW",
            "status": "PROPOSED",
            "source_urls": [self.url],
            "execution_authorized": False,
            "spending_authorized": False,
        }
        self.handoff = {
            "task_id": self.task_id,
            "opportunity_id": "research-aaaaaaaa",
            "status": "PENDING_OWNER_REVIEW",
            "owner_reviewed": False,
            "execution_authorized": False,
            "spending_authorized": False,
            "source_review_file": f"reviews/{self.task_id}.json",
            "candidates": self.candidates,
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
                "observations": [
                    {key: item[key] for key in (
                        "field", "statement", "quote", "quote_status",
                        "independently_verified",
                    )} for item in self.candidates
                ],
            }],
        }
        task_path = task_inbox.task_path(self.task_id)
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(json.dumps(task), encoding="utf-8")
        self.handoff_path = self.company / "evidence_candidates" / f"{self.task_id}.json"
        self.report_path = self.company / "reviews" / f"{self.task_id}.json"
        self.handoff_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.save()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def save(self):
        self.handoff_path.write_text(json.dumps(self.handoff), encoding="utf-8")
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")

    def catalog(self, cid, classification):
        return owner_review.decide(
            self.task_id, cid, "catalog", "Reviewed page and classified as market data.",
            classification=classification, confirm=True,
        )

    def test_advertised_price_is_archived_without_evidence_registration(self):
        decision_file = self.catalog("C2", "ADVERTISED_PRICE")
        saved = json.loads(decision_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["decision"], "CATALOGUED_MARKET_INTELLIGENCE")
        self.assertEqual(saved["classification"], "ADVERTISED_PRICE")
        self.assertEqual(saved["quote"], self.candidates[1]["quote"])
        self.assertEqual(saved["opportunity_id"], "research-aaaaaaaa")
        self.assertEqual(saved["supports"], [])
        self.assertFalse(saved["evidence_eligible"])
        self.assertFalse(saved["independently_verified"])
        self.assertFalse(saved["customer_demand_verified"])
        self.assertFalse(saved["revenue_verified"])
        self.assertFalse(saved["execution_authorized"])
        self.assertFalse(saved["spending_authorized"])
        self.assertFalse((self.opportunities / "evidence_index.json").exists())

    def test_vendor_claim_is_archived_without_evidence_registration(self):
        path = self.catalog("C1", "VENDOR_CLAIM")
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["classification"], "VENDOR_CLAIM")
        self.assertFalse(saved["evidence_eligible"])

    def test_catalog_requires_manual_confirmation(self):
        with self.assertRaises(PermissionError):
            owner_review.decide(
                self.task_id, "C2", "catalog", "Review note with sufficient length.",
                classification="ADVERTISED_PRICE",
            )

    def test_price_cannot_be_labeled_vendor_claim(self):
        with self.assertRaises(ValueError):
            self.catalog("C2", "VENDOR_CLAIM")

    def test_vendor_claim_cannot_be_labeled_price(self):
        with self.assertRaises(ValueError):
            self.catalog("C1", "ADVERTISED_PRICE")

    def test_customer_evidence_not_available_from_quote_only_source(self):
        with self.assertRaises(ValueError):
            self.catalog("C1", "CUSTOMER_EVIDENCE")

    def test_catalog_forbids_evaluation_scope(self):
        with self.assertRaises(ValueError):
            owner_review.decide(
                self.task_id, "C2", "catalog", "Review note with sufficient length.",
                scope="unit_economics", classification="ADVERTISED_PRICE", confirm=True,
            )

    def test_price_cannot_use_legacy_approval_path(self):
        with self.assertRaises(ValueError):
            owner_review.decide(
                self.task_id, "C2", "approve", "Reviewed listed prices in page.",
                scope="unit_economics", confirm=True,
            )

    def test_vendor_pain_cannot_use_customer_problem_approval(self):
        with self.assertRaises(ValueError):
            owner_review.decide(
                self.task_id, "C1", "approve", "Reviewed vendor marketing page.",
                scope="customer_problem", confirm=True,
            )

    def test_existing_rejection_is_not_overwritten(self):
        path = owner_review.decide(
            self.task_id, "C1", "reject", "Vendor marketing is not customer proof.",
        )
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.catalog("C1", "VENDOR_CLAIM")
        self.assertEqual(path.read_bytes(), original)

    def test_catalogued_candidate_cannot_be_registered(self):
        self.catalog("C2", "ADVERTISED_PRICE")
        with self.assertRaises(ValueError):
            evidence_registration.register_evidence(self.task_id, "C2")
        self.assertFalse((self.opportunities / "evidence_index.json").exists())

    def test_tampered_catalog_decision_cannot_register_price(self):
        path = self.catalog("C2", "ADVERTISED_PRICE")
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc.update({"decision": "APPROVED_FOR_REGISTRATION", "scope": "unit_economics"})
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ValueError):
            evidence_registration.register_evidence(self.task_id, "C2")

    def test_tampered_quote_is_rejected_before_catalog(self):
        self.report["source_reviews"][0]["observations"][1]["quote"] = (
            "Invented quote that is not in the original source report."
        )
        self.save()
        with self.assertRaises(ValueError):
            self.catalog("C2", "ADVERTISED_PRICE")

    def test_catalog_does_not_affect_evaluation(self):
        self.catalog("C2", "ADVERTISED_PRICE")
        inputs = default_inputs()
        inputs["opportunity_id"] = "research-aaaaaaaa"
        inputs["checks"]["willingness_to_pay"] = {
            "status": "SUPPORTED", "evidence_refs": ["owner-reviewed:fake-price"],
        }
        result = evaluate(
            inputs, {"competitors": []}, {"records": {}}, self.opportunities / "evidence",
        )
        self.assertEqual(result["decision"], "RESEARCH_MORE")
        self.assertIn("willingness_to_pay", result["missing_requirements"])
        self.assertFalse(result["execution_authorized"])

    def test_valid_quote_only_legacy_path_still_available(self):
        path = owner_review.decide(
            self.task_id, "C3", "approve", "Reviewed original paid vendor offering.",
            scope="differentiation", confirm=True,
        )
        self.assertEqual(json.loads(path.read_text())["decision"],
                         "APPROVED_FOR_REGISTRATION")


if __name__ == "__main__":
    unittest.main()
