"""C7B: owner-confirmed interview claims are still not decision evidence."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from agentforge import customer_validation as cv
from agentforge import customer_evidence_review as review


class TestCustomerEvidenceReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "customer_validation"
        self.patcher = patch.object(cv, "DATA_DIR", self.root)
        self.patcher.start()
        self.opp = "research-d3188c6a"
        self.alias = "shop_01"
        self.note = "I checked the context and kept this statement as an unverified claim."

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def capture(self, *, payment="VERBAL_INTEREST"):
        draft = cv.new_draft(self.opp, self.alias)
        doc = json.loads(draft.read_text(encoding="utf-8"))
        doc.update({
            "interview_date": date.today().isoformat(),
            "source_channel": "CALL",
            "business_context": "Small online store tracking stock and payments manually.",
            "problem_quote": "I spend hours every week reconciling order records.",
            "current_workaround": "Export CSV files and use custom spreadsheet formulas.",
            "frequency": "WEEKLY",
            "payment_signal": payment,
            "owner_note": "Interview recorded as first-hand claim, not proof of payment.",
        })
        draft.write_text(json.dumps(doc), encoding="utf-8")
        return cv.capture(self.opp, self.alias, confirm_consent=True)

    def retain(self):
        return review.decide(
            self.opp, self.alias, "retain", self.note,
            confirm_firsthand_interview=True, confirm_quote_context=True,
        )

    def test_empty_summary_is_not_demand_proof(self):
        s = review.summary(self.opp)
        self.assertEqual(s["captured_count"], 0)
        self.assertEqual(s["unreviewed_count"], 0)
        self.assertFalse(s["customer_problem_verified"])
        self.assertFalse(s["evidence_registered"])

    def test_draft_cannot_be_reviewed(self):
        cv.new_draft(self.opp, self.alias)
        with self.assertRaises(FileNotFoundError):
            review.inspect(self.opp, self.alias)

    def test_inspect_does_not_create_decision(self):
        self.capture()
        result = review.inspect(self.opp, self.alias)
        self.assertEqual(result["review_status"], "NOT_REVIEWED")
        self.assertEqual(result["payment_signal"], "VERBAL_INTEREST")
        self.assertIsNone(result["review_path"])
        self.assertFalse((self.root / "reviews").exists())

    def test_retain_requires_both_manual_confirmations(self):
        self.capture()
        for a, b in ((False, False), (True, False), (False, True)):
            with self.assertRaises(PermissionError):
                review.decide(
                    self.opp, self.alias, "retain", self.note,
                    confirm_firsthand_interview=a, confirm_quote_context=b,
                )
        self.assertFalse((self.root / "reviews").exists())

    def test_retain_is_claim_and_not_evaluation_evidence(self):
        source = self.capture(payment="PAST_PAYMENT_CLAIM")
        before = source.read_bytes()
        path = self.retain()
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["decision"], "RETAINED_FIRSTHAND_CLAIM")
        self.assertEqual(doc["source_payment_signal"], "PAST_PAYMENT_CLAIM")
        self.assertTrue(doc["owner_reviewed"])
        self.assertTrue(doc["firsthand_interview_confirmed_by_owner"])
        self.assertTrue(doc["quote_context_confirmed_by_owner"])
        self.assertTrue(doc["retained_as_claim"])
        for field in ("independently_verified", "customer_problem_verified",
                      "willingness_to_pay_verified", "payment_verified",
                      "evidence_eligible", "execution_authorized", "spending_authorized"):
            self.assertFalse(doc[field], field)
        self.assertEqual(doc["supports"], [])
        self.assertEqual(doc["evidence_refs"], [])
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse((Path(self.tmp.name) / "opportunities" / "evidence_index.json").exists())

    def test_retain_verbal_interest_never_verifies_payment(self):
        self.capture(payment="VERBAL_INTEREST")
        self.retain()
        s = review.summary(self.opp)
        self.assertEqual(s["review_counts"]["RETAINED_FIRSTHAND_CLAIM"], 1)
        self.assertFalse(s["payment_verified"])
        self.assertFalse(s["willingness_to_pay_verified"])

    def test_followup_is_pending_not_evidence(self):
        self.capture()
        path = review.decide(self.opp, self.alias, "followup", self.note)
        d = json.loads(path.read_text())
        self.assertEqual(d["decision"], "NEEDS_FOLLOWUP")
        self.assertFalse(d["retained_as_claim"])
        self.assertFalse(d["firsthand_interview_confirmed_by_owner"])
        self.assertFalse(d["evidence_eligible"])

    def test_reject_simulated_sample_does_not_register(self):
        self.capture()
        path = review.decide(self.opp, self.alias, "reject", "This entry is a test sample, not a real interview.")
        self.assertEqual(json.loads(path.read_text())["decision"], "REJECTED")
        self.assertFalse(review.summary(self.opp)["evidence_registered"])

    def test_reject_and_followup_refuse_confirmation_flags(self):
        self.capture()
        for decision in ("reject", "followup"):
            with self.assertRaises(ValueError):
                review.decide(self.opp, self.alias, decision, self.note,
                              confirm_firsthand_interview=True)

    def test_immutable_review_decision(self):
        self.capture()
        path = self.retain()
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            review.decide(self.opp, self.alias, "reject", self.note)
        self.assertEqual(path.read_bytes(), original)

    def test_record_changed_after_review_fails_closed(self):
        record = self.capture()
        self.retain()
        doc = json.loads(record.read_text())
        doc["problem_quote"] = "I was not the person who said this earlier."
        record.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ValueError):
            review.inspect(self.opp, self.alias)
        with self.assertRaises(ValueError):
            review.summary(self.opp)

    def test_tampered_review_evidence_flag_rejected(self):
        self.capture()
        path = self.retain()
        doc = json.loads(path.read_text())
        doc["evidence_eligible"] = True
        path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            review.summary(self.opp)

    def test_tampered_capture_consent_rejected(self):
        record = self.capture()
        doc = json.loads(record.read_text())
        doc["consent_confirmed_by_owner"] = False
        record.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            self.retain()

    def test_tampered_capture_claimed_approval_rejected(self):
        record = self.capture()
        doc = json.loads(record.read_text())
        doc["willingness_to_pay_verified"] = True
        record.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            review.inspect(self.opp, self.alias)

    def test_tampered_capture_extra_fields_rejected(self):
        record = self.capture()
        doc = json.loads(record.read_text())
        doc["email"] = "do-not-keep"
        record.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            self.retain()

    def test_review_with_missing_source_rejected(self):
        self.capture()
        self.retain()
        record = self.root / "records" / self.opp / f"{self.alias}.json"
        record.unlink()
        with self.assertRaises(ValueError):
            review.summary(self.opp)

    def test_unsafe_identifiers_rejected(self):
        self.capture()
        for opp, alias in (("../foo", self.alias), (self.opp, "../../escape"),
                           (self.opp, "john@example.com")):
            with self.assertRaises(ValueError):
                review.inspect(opp, alias)

    def test_note_with_email_rejected(self):
        self.capture()
        with self.assertRaises(ValueError):
            review.decide(self.opp, self.alias, "reject",
                          "Interview of customer at john@example.com is fake.")

    def test_summary_detects_unreviewed_and_reviewed(self):
        self.capture()
        self.assertEqual(review.summary(self.opp)["unreviewed_count"], 1)
        self.retain()
        s = review.summary(self.opp)
        self.assertEqual(s["captured_count"], 1)
        self.assertEqual(s["unreviewed_count"], 0)
        self.assertEqual(s["review_counts"]["RETAINED_FIRSTHAND_CLAIM"], 1)
        self.assertFalse(s["execution_authorized"])
        self.assertFalse(s["spending_authorized"])

    def test_review_does_not_require_model_or_network(self):
        self.capture()
        with patch("urllib.request.urlopen") as net:
            self.retain()
            net.assert_not_called()


if __name__ == "__main__":
    unittest.main()
