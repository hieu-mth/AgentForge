"""C7C: two retained firsthand accounts can only support customer_problem."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from agentforge import customer_validation as cv
from agentforge import customer_evidence_review as review
from agentforge import customer_problem_evidence as cpe
from agentforge.evidence_registry import valid_references_for_opportunity
from agentforge.evaluation import default_inputs, evaluate


class TestCustomerProblemEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.opp = "research-d3188c6a"
        self.a = "shop_01"
        self.b = "shop_02"
        self.note = ("I compared two separate first-hand accounts of the same "
                     "manual order reconciliation problem; no payment was verified.")
        self.patches = [
            patch.object(cv, "DATA_DIR", self.root / "customer_validation"),
            patch.object(cpe, "OPPORTUNITIES", self.root / "opportunities"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def capture(self, code, payment="VERBAL_INTEREST"):
        path = cv.new_draft(self.opp, code)
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc.update({
            "interview_date": date.today().isoformat(),
            "source_channel": "CALL",
            "business_context": "Small shop reconciling order totals across channels.",
            "problem_quote": "Reconciling transactions manually takes several hours weekly.",
            "current_workaround": "I export spreadsheets and join them by hand every week.",
            "frequency": "WEEKLY",
            "payment_signal": payment,
            "owner_note": "Real participant interview context is checked manually by owner.",
        })
        path.write_text(json.dumps(doc), encoding="utf-8")
        return cv.capture(self.opp, code, confirm_consent=True)

    def retain(self, code):
        return review.decide(
            self.opp, code, "retain",
            "I checked the original interview and confirmed the quote in context.",
            confirm_firsthand_interview=True, confirm_quote_context=True,
        )

    def prepare(self):
        for code in (self.a, self.b):
            self.capture(code)
            self.retain(code)

    def register(self, **kwargs):
        return cpe.register(
            self.opp, [self.a, self.b], self.note,
            confirm_independent_interviews=True, confirm_same_problem=True,
            **kwargs,
        )

    def test_empty_summary_not_ready(self):
        result = cpe.inspect(self.opp)
        self.assertEqual(result["retained_count"], 0)
        self.assertFalse(result["ready_for_owner_corroboration"])
        self.assertFalse(result["payment_verified"])

    def test_two_retained_firsthand_claims_can_be_seen(self):
        self.prepare()
        result = cpe.inspect(self.opp)
        self.assertEqual(result["retained_participants"], [self.a, self.b])
        self.assertTrue(result["ready_for_owner_corroboration"])
        self.assertNotIn("problem_quote", result)
        self.assertFalse(result["independently_verified"])

    def test_registration_requires_two_manual_confirmations(self):
        self.prepare()
        for x, y in ((False, False), (True, False), (False, True)):
            with self.assertRaises(PermissionError):
                cpe.register(self.opp, [self.a, self.b], self.note,
                             confirm_independent_interviews=x, confirm_same_problem=y)
        self.assertFalse((self.root / "opportunities").exists())

    def test_two_retained_accounts_register_only_customer_problem(self):
        self.prepare()
        result = self.register()
        index = json.loads((self.root / "opportunities" / "evidence_index.json").read_text())
        artifact = json.loads(Path(result["source_file"]).read_text())
        self.assertEqual(artifact["source_type"], cpe.SOURCE_TYPE)
        self.assertEqual(artifact["scope"], "customer_problem")
        self.assertEqual(len(artifact["participants"]), 2)
        self.assertFalse(artifact["independently_verified"])
        self.assertFalse(artifact["payment_verified"])
        self.assertFalse(artifact["willingness_to_pay_verified"])
        self.assertFalse(artifact["execution_authorized"])
        self.assertTrue(valid_references_for_opportunity(
            [result["reference"]], "customer_problem", index,
            self.root / "opportunities" / "evidence", self.opp,
        ))
        self.assertFalse(valid_references_for_opportunity(
            [result["reference"]], "willingness_to_pay", index,
            self.root / "opportunities" / "evidence", self.opp,
        ))
        self.assertFalse(valid_references_for_opportunity(
            [result["reference"]], "customer_problem", index,
            self.root / "opportunities" / "evidence", "research-aaaaaaaa",
        ))

    def test_registration_does_not_trigger_go(self):
        self.prepare()
        result = self.register()
        index = json.loads((self.root / "opportunities" / "evidence_index.json").read_text())
        inputs = default_inputs()
        inputs["opportunity_id"] = self.opp
        inputs["checks"]["customer_problem"] = {
            "status": "SUPPORTED", "evidence_refs": [result["reference"]],
        }
        decision = evaluate(inputs, {"competitors": []}, index, self.root / "opportunities" / "evidence")
        self.assertEqual(decision["decision"], "RESEARCH_MORE")
        self.assertIn("willingness_to_pay", decision["missing_requirements"])
        self.assertNotIn("customer_problem", decision["missing_requirements"])
        self.assertFalse(decision["execution_authorized"])

    def test_one_retained_interview_is_not_enough(self):
        self.capture(self.a)
        self.retain(self.a)
        self.capture(self.b)
        self.assertFalse(cpe.inspect(self.opp)["ready_for_owner_corroboration"])
        with self.assertRaises(FileNotFoundError):
            self.register()

    def test_rejected_interview_cannot_register(self):
        self.prepare_first_only_then(self.b, "reject")
        with self.assertRaises(ValueError):
            self.register()

    def test_followup_interview_cannot_register(self):
        self.prepare_first_only_then(self.b, "followup")
        with self.assertRaises(ValueError):
            self.register()

    def prepare_first_only_then(self, code, decision):
        self.capture(self.a)
        self.retain(self.a)
        self.capture(code)
        review.decide(self.opp, code, decision,
                      "This interview cannot be accepted without more context.")

    def test_same_participant_twice_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError):
            cpe.register(self.opp, [self.a, self.a], self.note,
                         confirm_independent_interviews=True, confirm_same_problem=True)

    def test_cross_opportunity_registration_rejected(self):
        self.prepare()
        with self.assertRaises(FileNotFoundError):
            cpe.register("research-aaaaaaaa", [self.a, self.b], self.note,
                         confirm_independent_interviews=True, confirm_same_problem=True)

    def test_invalid_alias_and_note_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError):
            cpe.register(self.opp, ["../../etc", self.b], self.note,
                         confirm_independent_interviews=True, confirm_same_problem=True)
        with self.assertRaises(ValueError):
            cpe.register(self.opp, [self.a, self.b], "too short",
                         confirm_independent_interviews=True, confirm_same_problem=True)
        with self.assertRaises(ValueError):
            cpe.register(self.opp, [self.a, self.b],
                         "Participant email me@private.example told us about a problem.",
                         confirm_independent_interviews=True, confirm_same_problem=True)

    def test_source_record_modified_after_review_rejected(self):
        self.prepare()
        path = cv.DATA_DIR / "records" / self.opp / f"{self.a}.json"
        doc = json.loads(path.read_text())
        doc["problem_quote"] = "A different quoted problem statement was substituted here."
        path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            self.register()

    def test_review_changed_after_registration_is_refused_on_recheck(self):
        self.prepare()
        path = cv.DATA_DIR / "reviews" / self.opp / f"{self.a}.json"
        doc = json.loads(path.read_text())
        doc["payment_verified"] = True
        path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            self.register()

    def test_duplicate_registration_does_not_overwrite(self):
        self.prepare()
        result = self.register()
        i = Path(result["index_file"])
        a = Path(result["source_file"])
        before = (i.read_bytes(), a.read_bytes())
        with self.assertRaises(FileExistsError):
            self.register()
        self.assertEqual((i.read_bytes(), a.read_bytes()), before)

    def test_owner_review_records_remain_immutable(self):
        self.prepare()
        record = cv.DATA_DIR / "records" / self.opp / f"{self.a}.json"
        decision = cv.DATA_DIR / "reviews" / self.opp / f"{self.a}.json"
        before = record.read_bytes(), decision.read_bytes()
        self.register()
        self.assertEqual((record.read_bytes(), decision.read_bytes()), before)

    def test_corrupt_existing_index_fails_without_new_artifact(self):
        self.prepare()
        base = self.root / "opportunities"
        base.mkdir(parents=True)
        (base / "evidence_index.json").write_text('{"records": []}')
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(list((base / "evidence").glob("*.json")), [])

    def test_existing_index_records_remain(self):
        self.prepare()
        base = self.root / "opportunities"
        base.mkdir(parents=True)
        previous = {"records": {"owner-reviewed:old": {"owner_reviewed": True, "supports": ["distribution"], "source_file": "old.json"}}}
        (base / "evidence_index.json").write_text(json.dumps(previous))
        self.register()
        index = json.loads((base / "evidence_index.json").read_text())
        self.assertEqual(index["records"]["owner-reviewed:old"], previous["records"]["owner-reviewed:old"])

    def test_modifying_original_interview_invalidates_registered_reference(self):
        self.prepare()
        result = self.register()
        record = cv.DATA_DIR / "records" / self.opp / f"{self.a}.json"
        doc = json.loads(record.read_text())
        doc["owner_note"] = "A changed owner note after evidence registration."
        record.write_text(json.dumps(doc))
        index = json.loads((self.root / "opportunities" / "evidence_index.json").read_text())
        self.assertFalse(valid_references_for_opportunity(
            [result["reference"]], "customer_problem", index,
            self.root / "opportunities" / "evidence", self.opp,
        ))

    def test_modifying_review_invalidates_registered_reference(self):
        self.prepare()
        result = self.register()
        path = cv.DATA_DIR / "reviews" / self.opp / f"{self.b}.json"
        doc = json.loads(path.read_text())
        doc["review_note"] = "Tampered review note that changes the decision bytes."
        path.write_text(json.dumps(doc))
        index = json.loads((self.root / "opportunities" / "evidence_index.json").read_text())
        self.assertFalse(valid_references_for_opportunity(
            [result["reference"]], "customer_problem", index,
            self.root / "opportunities" / "evidence", self.opp,
        ))

    def test_changing_evidence_scope_in_index_cannot_prove_payment(self):
        self.prepare()
        result = self.register()
        index = json.loads((self.root / "opportunities" / "evidence_index.json").read_text())
        index["records"][result["reference"]]["supports"] = ["willingness_to_pay"]
        self.assertFalse(valid_references_for_opportunity(
            [result["reference"]], "willingness_to_pay", index,
            self.root / "opportunities" / "evidence", self.opp,
        ))

    def test_is_local_only_no_network_or_llm(self):
        self.prepare()
        with patch("urllib.request.urlopen") as net:
            self.register()
            net.assert_not_called()


if __name__ == "__main__":
    unittest.main()
