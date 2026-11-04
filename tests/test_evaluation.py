import tempfile
import unittest
from pathlib import Path

from agentforge.evaluation import (
    default_inputs,
    evaluate,
    REQUIRED,
)


class TestEvaluation(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.evidence_dir = Path(self.temp.name)
        self.refs = {}
        self.registry = {"records": {}}

        for check in REQUIRED:
            slug = check.replace("_", "-")
            ref = f"owner-reviewed:{slug}-001"
            filename = f"{slug}-001.txt"

            (self.evidence_dir / filename).write_text(
                f"Fixture evidence for {check}",
                encoding="utf-8",
            )

            self.registry["records"][ref] = {
                "owner_reviewed": True,
                "supports": [check],
                "source_file": filename,
            }
            self.refs[check] = ref

        (self.evidence_dir / "blocker-001.txt").write_text(
            "Fixture hard blocker evidence",
            encoding="utf-8",
        )

        self.blocker_ref = "owner-reviewed:blocker-001"
        self.registry["records"][self.blocker_ref] = {
            "owner_reviewed": True,
            "supports": ["hard_blocker"],
            "source_file": "blocker-001.txt",
        }

        self.competitors = {
            "competitors": [{
                "name": "Example Vendor",
                "facts": [{
                    "field": "price",
                    "statement": "Paid product advertised",
                    "quote": "Example vendor price listing",
                    "quote_status": "MATCHED_IN_PAGE",
                }],
            }]
        }

    def tearDown(self):
        self.temp.cleanup()

    def check(self, inputs, registry=None):
        return evaluate(
            inputs,
            self.competitors,
            self.registry if registry is None else registry,
            self.evidence_dir,
        )

    def go_inputs(self):
        inputs = default_inputs()

        for check in REQUIRED:
            inputs["checks"][check] = {
                "status": "SUPPORTED",
                "evidence_refs": [self.refs[check]],
            }

        inputs["experiment"] = {
            "budget_cap_vnd": 100000,
            "owner_approved": True,
        }
        return inputs

    def test_vendor_price_alone_is_not_go(self):
        result = self.check(default_inputs())

        self.assertEqual(result["decision"], "RESEARCH_MORE")
        self.assertEqual(len(result["vendor_price_quotes"]), 1)
        self.assertFalse(result["execution_authorized"])

    def test_evidenced_hard_blocker_kills(self):
        inputs = default_inputs()
        inputs["hard_blocker"] = {
            "confirmed": True,
            "evidence_refs": [self.blocker_ref],
        }

        result = self.check(inputs)
        self.assertEqual(result["decision"], "KILL")

    def test_go_requires_all_checks_and_approval(self):
        result = self.check(self.go_inputs())

        self.assertEqual(result["decision"], "GO_TO_EXPERIMENT")
        self.assertFalse(result["execution_authorized"])

    def test_fabricated_reference_cannot_go(self):
        inputs = self.go_inputs()
        inputs["checks"]["customer_problem"]["evidence_refs"] = [
            "owner-reviewed:does-not-exist"
        ]

        result = self.check(inputs)

        self.assertEqual(result["decision"], "RESEARCH_MORE")
        self.assertIn("customer_problem", result["missing_requirements"])

    def test_fabricated_blocker_cannot_kill(self):
        inputs = default_inputs()
        inputs["hard_blocker"] = {
            "confirmed": True,
            "evidence_refs": ["owner-reviewed:fake-blocker"],
        }

        result = self.check(inputs)
        self.assertEqual(result["decision"], "RESEARCH_MORE")
        self.assertIn("hard_blocker_evidence", result["missing_requirements"])

    def test_invalid_blocker_also_prevents_go(self):
        inputs = self.go_inputs()
        inputs["hard_blocker"] = {
            "confirmed": True,
            "evidence_refs": ["owner-reviewed:fake-blocker"],
        }

        result = self.check(inputs)

        self.assertEqual(result["decision"], "RESEARCH_MORE")
        self.assertIn("hard_blocker_evidence", result["missing_requirements"])

    def test_wrong_scope_is_rejected(self):
        inputs = self.go_inputs()
        inputs["checks"]["customer_problem"]["evidence_refs"] = [
            self.refs["distribution"]
        ]

        result = self.check(inputs)
        self.assertIn("customer_problem", result["missing_requirements"])

    def test_unreviewed_record_is_rejected(self):
        inputs = self.go_inputs()
        ref = self.refs["customer_problem"]
        self.registry["records"][ref]["owner_reviewed"] = False

        result = self.check(inputs)
        self.assertIn("customer_problem", result["missing_requirements"])

    def test_missing_source_file_is_rejected(self):
        inputs = self.go_inputs()
        ref = self.refs["customer_problem"]
        filename = self.registry["records"][ref]["source_file"]
        (self.evidence_dir / filename).unlink()

        result = self.check(inputs)
        self.assertIn("customer_problem", result["missing_requirements"])

    def test_path_traversal_source_is_rejected(self):
        inputs = self.go_inputs()
        ref = self.refs["customer_problem"]
        self.registry["records"][ref]["source_file"] = "../outside.txt"

        result = self.check(inputs)
        self.assertIn("customer_problem", result["missing_requirements"])

    def test_mixed_valid_and_invalid_refs_are_rejected(self):
        inputs = self.go_inputs()
        inputs["checks"]["customer_problem"]["evidence_refs"].append(
            "owner-reviewed:fake"
        )

        result = self.check(inputs)
        self.assertIn("customer_problem", result["missing_requirements"])

    def test_missing_registry_fails_closed(self):
        inputs = self.go_inputs()

        result = evaluate(
            inputs,
            self.competitors,
            evidence_dir=self.evidence_dir,
        )

        self.assertEqual(result["decision"], "RESEARCH_MORE")


if __name__ == "__main__":
    unittest.main()
