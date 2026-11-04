import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import review_handoff, task_inbox


class TestReviewHandoff(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.company_dir = Path(self.temp.name) / "company"

        self.patcher = patch.object(
            task_inbox, "DATA_DIR", self.company_dir
        )
        self.patcher.start()

        self.task_id = "a" * 32 + "-source-review"
        self.url = "https://example.org/article"
        self.quote = (
            "A paid Excel service is advertised for local shops."
        )

        self.task = {
            "task_id": self.task_id,
            "opportunity_id": "research-aaaaaaaa",
            "kind": "SOURCE_REVIEW",
            "status": "PROPOSED",
            "source_urls": [self.url],
            "execution_authorized": False,
            "spending_authorized": False,
        }

        self.report = {
            "task_id": self.task_id,
            "opportunity_id": "research-aaaaaaaa",
            "review_status": "QUOTE_REVIEW_ONLY",
            "matched_quotes": 1,
            "customer_demand_verified": False,
            "revenue_verified": False,
            "execution_authorized": False,
            "spending_authorized": False,
            "source_reviews": [{
                "url": self.url,
                "status": "QUOTES_CHECKED_NOT_FACT_CHECKED",
                "observations": [
                    {
                        "field": "paid_alternative",
                        "statement": "A business advertises a paid service",
                        "quote": self.quote,
                        "quote_status": "MATCHED_IN_PAGE",
                        "independently_verified": False,
                    },
                    {
                        "field": "price",
                        "statement": "An invented price",
                        "quote": "A price not found in the page",
                        "quote_status": "REJECTED_QUOTE",
                        "independently_verified": False,
                    },
                ],
            }],
        }

        path = task_inbox.task_path(self.task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.task), encoding="utf-8")

        self.save_report()

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def save_report(self):
        self.report_path = (
            self.company_dir / "reviews" / f"{self.task_id}.json"
        )
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(
            json.dumps(self.report), encoding="utf-8"
        )

    def test_stages_only_matched_quotes_without_approval(self):
        output = review_handoff.prepare_candidates(self.task_id)
        document = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(
            document["status"], "PENDING_OWNER_REVIEW"
        )
        self.assertFalse(document["owner_reviewed"])
        self.assertFalse(document["execution_authorized"])
        self.assertFalse(document["spending_authorized"])

        self.assertEqual(len(document["candidates"]), 1)
        self.assertEqual(
            document["candidates"][0]["quote"], self.quote
        )
        self.assertEqual(
            document["candidates"][0]["supports"], []
        )
        self.assertFalse(
            document["candidates"][0]["owner_reviewed"]
        )

        self.assertFalse(
            (
                self.company_dir.parent
                / "opportunities"
                / "evidence_index.json"
            ).exists()
        )

    def test_does_not_overwrite_previous_handoff(self):
        output = review_handoff.prepare_candidates(self.task_id)
        original = output.read_bytes()

        with self.assertRaises(FileExistsError):
            review_handoff.prepare_candidates(self.task_id)

        self.assertEqual(output.read_bytes(), original)

    def test_missing_review_report_rejected(self):
        self.report_path.unlink()

        with self.assertRaises(FileNotFoundError):
            review_handoff.prepare_candidates(self.task_id)

    def test_mismatched_task_id_rejected(self):
        self.report["task_id"] = "b" * 32 + "-source-review"
        self.save_report()

        with self.assertRaises(ValueError):
            review_handoff.prepare_candidates(self.task_id)

    def test_mismatched_opportunity_rejected(self):
        self.report["opportunity_id"] = "another-opportunity"
        self.save_report()

        with self.assertRaises(ValueError):
            review_handoff.prepare_candidates(self.task_id)

    def test_unapproved_source_rejected(self):
        self.report["source_reviews"][0]["url"] = (
            "https://other.example.org/article"
        )
        self.save_report()

        with self.assertRaises(ValueError):
            review_handoff.prepare_candidates(self.task_id)

    def test_report_cannot_claim_approved_execution(self):
        self.report["execution_authorized"] = True
        self.save_report()

        with self.assertRaises(ValueError):
            review_handoff.prepare_candidates(self.task_id)

    def test_quote_count_mismatch_rejected(self):
        self.report["matched_quotes"] = 2
        self.save_report()

        with self.assertRaises(ValueError):
            review_handoff.prepare_candidates(self.task_id)

    def test_no_matched_quotes_rejected(self):
        self.report["matched_quotes"] = 0
        self.report["review_status"] = "NO_MATCHED_QUOTES"
        self.report["source_reviews"][0]["observations"][0][
            "quote_status"
        ] = "REJECTED_QUOTE"
        self.save_report()

        with self.assertRaises(ValueError):
            review_handoff.prepare_candidates(self.task_id)

    def test_deferred_task_rejected(self):
        self.task["status"] = "DEFERRED"
        path = task_inbox.task_path(self.task_id)
        path.write_text(json.dumps(self.task), encoding="utf-8")

        with self.assertRaises(ValueError):
            review_handoff.prepare_candidates(self.task_id)

    def test_invalid_task_id_rejected(self):
        with self.assertRaises(ValueError):
            review_handoff.prepare_candidates("../outside")


if __name__ == "__main__":
    unittest.main()
