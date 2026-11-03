import unittest

from agentforge.evaluation import default_inputs, evaluate, REQUIRED


class TestEvaluation(unittest.TestCase):

    def setUp(self):
        self.competitors = {
            "competitors": [{
                "name": "Example Vendor",
                "facts": [{
                    "field": "price",
                    "statement": "Paid product advertised",
                    "quote": "Example vendor price listing",
                    "quote_status": "MATCHED_IN_PAGE"
                }]
            }]
        }

    def test_vendor_price_alone_is_not_go(self):
        result = evaluate(default_inputs(), self.competitors)

        self.assertEqual(result["decision"], "RESEARCH_MORE")
        self.assertEqual(len(result["vendor_price_quotes"]), 1)
        self.assertFalse(result["execution_authorized"])

    def test_evidenced_hard_blocker_kills(self):
        inputs = default_inputs()

        inputs["hard_blocker"] = {
            "confirmed": True,
            "evidence_refs": ["owner-reviewed:blocker-record"]
        }

        result = evaluate(inputs, self.competitors)

        self.assertEqual(result["decision"], "KILL")

    def test_go_requires_all_checks_and_approval(self):
        inputs = default_inputs()

        for key in REQUIRED:
            inputs["checks"][key] = {
                "status": "SUPPORTED",
                "evidence_refs": ["owner-reviewed:test-evidence"]
            }

        inputs["experiment"] = {
            "budget_cap_vnd": 100000,
            "owner_approved": True
        }

        result = evaluate(inputs, self.competitors)

        self.assertEqual(result["decision"], "GO_TO_EXPERIMENT")
        self.assertFalse(result["execution_authorized"])


if __name__ == "__main__":
    unittest.main()