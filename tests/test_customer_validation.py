"""C7A: Customer interview notes remain unverified and local."""
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from agentforge import customer_validation as cv


class TestCustomerValidation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patcher = patch.object(cv, "DATA_DIR", self.root / "customer_validation")
        self.patcher.start()
        self.opp = "research-d3188c6a"
        self.alias = "shop_01"

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def draft(self):
        path = cv.new_draft(self.opp, self.alias)
        obj = json.loads(path.read_text(encoding="utf-8"))
        obj.update({
            "interview_date": date.today().isoformat(),
            "source_channel": "CALL",
            "business_context": "Small online shop with orders on several platforms.",
            "problem_quote": "Each week I have to reconcile transactions manually in spreadsheets.",
            "current_workaround": "Exports CSV files and combines with manual formulas.",
            "frequency": "WEEKLY",
            "payment_signal": "VERBAL_INTEREST",
            "owner_note": "Personal interview, quote anonymized; not sales proof.",
        })
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def test_new_draft_has_empty_fields_and_unverified_status(self):
        path = cv.new_draft(self.opp, self.alias)
        d = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(d["status"], "DRAFT")
        self.assertEqual(d["problem_quote"], "")

    def test_duplicate_draft_is_not_overwritten(self):
        path = cv.new_draft(self.opp, self.alias)
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            cv.new_draft(self.opp, self.alias)
        self.assertEqual(path.read_bytes(), before)

    def test_ids_forbid_path_traversal_and_contact_address(self):
        for opp, alias in (("../outside", self.alias), (self.opp, "../escape"),
                           (self.opp, "john@example.com"), (self.opp, "aa")):
            with self.assertRaises(ValueError):
                cv.new_draft(opp, alias)

    def test_check_validates_without_writing_record(self):
        self.draft()
        self.assertEqual(cv.check_draft(self.opp, self.alias)["status"], "READY_TO_CAPTURE")
        self.assertFalse((self.root / "customer_validation" / "records").exists())

    def test_capture_requires_explicit_consent(self):
        self.draft()
        with self.assertRaises(PermissionError):
            cv.capture(self.opp, self.alias)
        self.assertFalse((self.root / "customer_validation" / "records").exists())

    def test_capture_is_not_evaluation_evidence(self):
        self.draft()
        path = cv.capture(self.opp, self.alias, confirm_consent=True)
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["status"], "CAPTURED_UNVERIFIED")
        self.assertEqual(doc["payment_signal"], "VERBAL_INTEREST")
        self.assertFalse(doc["customer_problem_verified"])
        self.assertFalse(doc["willingness_to_pay_verified"])
        self.assertFalse(doc["evidence_eligible"])
        self.assertFalse(doc["owner_reviewed"])
        self.assertEqual(doc["supports"], [])
        self.assertFalse(doc["execution_authorized"])
        self.assertFalse(doc["spending_authorized"])
        self.assertFalse((self.root / "opportunities" / "evidence_index.json").exists())

    def test_capture_is_immutable(self):
        self.draft()
        path = cv.capture(self.opp, self.alias, confirm_consent=True)
        content = path.read_bytes()
        with self.assertRaises(FileExistsError):
            cv.capture(self.opp, self.alias, confirm_consent=True)
        self.assertEqual(path.read_bytes(), content)

    def test_mismatched_opportunity_does_not_capture(self):
        path = self.draft()
        d = json.loads(path.read_text(encoding="utf-8"))
        d["opportunity_id"] = "research-aaaaaaaa"
        path.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(ValueError):
            cv.capture(self.opp, self.alias, confirm_consent=True)

    def test_extra_fields_are_rejected_to_limit_sensitive_data(self):
        path = self.draft()
        d = json.loads(path.read_text(encoding="utf-8"))
        d["customer_phone"] = "do-not-collect"
        path.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(ValueError):
            cv.capture(self.opp, self.alias, confirm_consent=True)

    def test_invalid_channel_and_payment_signal_rejected(self):
        for key, value in (("source_channel", "WEB_SCRAPE"),
                           ("payment_signal", "PAID_VERIFIED")):
            path = self.draft()
            d = json.loads(path.read_text(encoding="utf-8"))
            d[key] = value
            path.write_text(json.dumps(d), encoding="utf-8")
            with self.assertRaises(ValueError):
                cv.check_draft(self.opp, self.alias)
            path.unlink()

    def test_future_interview_date_rejected(self):
        path = self.draft()
        d = json.loads(path.read_text(encoding="utf-8"))
        d["interview_date"] = (date.today() + timedelta(days=1)).isoformat()
        path.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(ValueError):
            cv.check_draft(self.opp, self.alias)

    def test_pii_like_email_in_note_rejected(self):
        path = self.draft()
        d = json.loads(path.read_text(encoding="utf-8"))
        d["owner_note"] = "The customer email was john@example.com"
        path.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(ValueError):
            cv.check_draft(self.opp, self.alias)

    def test_empty_summary_is_not_validation(self):
        obj = cv.summary(self.opp)
        self.assertEqual(obj["interview_count"], 0)
        self.assertFalse(obj["customer_demand_verified"])
        self.assertFalse(obj["evidence_registered"])

    def test_summary_counts_signals_but_never_verifies_payments(self):
        self.draft()
        cv.capture(self.opp, self.alias, confirm_consent=True)
        obj = cv.summary(self.opp)
        self.assertEqual(obj["interview_count"], 1)
        self.assertEqual(obj["payment_signal_counts"]["VERBAL_INTEREST"], 1)
        self.assertFalse(obj["willingness_to_pay_verified"])
        self.assertFalse(obj["execution_authorized"])

    def test_invalid_record_is_not_silently_counted(self):
        self.draft()
        path = cv.capture(self.opp, self.alias, confirm_consent=True)
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["evidence_eligible"] = True
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ValueError):
            cv.summary(self.opp)


if __name__ == "__main__":
    unittest.main()
