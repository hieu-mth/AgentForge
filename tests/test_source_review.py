import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import source_review, task_inbox


class TestSourceReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp.name) / "company"
        self.patch = patch.object(task_inbox, "DATA_DIR", self.data_dir)
        self.patch.start()
        self.task_id = "b" * 32 + "-excel-automation-service-review"
        self.task_path = (
            self.data_dir / "tasks" / (self.task_id.removesuffix("-review") + ".json")
        )
        self.task_path.parent.mkdir(parents=True, exist_ok=True)
        self.task = {
            "task_id": self.task_id,
            "opportunity_id": "excel-automation-service",
            "kind": "SOURCE_REVIEW",
            "status": "PROPOSED",
            "source_urls": [
                "https://sheet.com.vn/blog/test",
                "https://redai.vn/post/example",
            ],
            "execution_authorized": False,
            "spending_authorized": False,
        }
        self.save_task()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def save_task(self):
        self.task_path.write_text(json.dumps(self.task), encoding="utf-8")

    def test_refuses_without_manual_read_only_approval(self):
        with patch.object(source_review, "fetch_for_one_host") as fetch:
            with self.assertRaises(PermissionError):
                source_review.run_review(self.task_id, ["sheet.com.vn"])
            fetch.assert_not_called()

    def test_refuses_host_not_in_task(self):
        with patch.object(source_review, "fetch_for_one_host") as fetch:
            with self.assertRaises(ValueError):
                source_review.run_review(
                    self.task_id, ["example.com"], approve_read_only=True
                )
            fetch.assert_not_called()

    def test_rejects_private_or_untrusted_urls(self):
        for url in (
            "http://sheet.com.vn/test", "https://127.0.0.1/test",
            "https://localhost/test", "https://sheet.com.vn.evil.invalid/test",
            "https://user:password@sheet.com.vn/test",
            "https://sheet.com.vn:444/test",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    source_review.safe_host(url)

    def test_deferred_task_cannot_be_reviewed(self):
        self.task["status"] = "DEFERRED"
        self.save_task()
        with self.assertRaises(ValueError):
            source_review.get_task_urls(self.task_id)

    def test_no_whitelist_no_network(self):
        with patch.object(source_review, "fetch_for_one_host") as fetch:
            with self.assertRaises(ValueError):
                source_review.run_review(self.task_id, [], approve_read_only=True)
            fetch.assert_not_called()

    def test_read_only_review_matches_quote_and_keeps_task_unchanged(self):
        quote = "We provide a paid Excel automation service for small shops."
        page = {
            "title": "Example service",
            "text_excerpt": "About this service. " + quote + " Contact us for details.",
            "extracted_characters": 100,
        }
        model = {"observations": [
            {"field": "paid_alternative", "statement": "A paid service is advertised", "quote": quote},
            {"field": "price", "statement": "An invented price", "quote": "The price is 999999 VND for everyone."},
        ]}
        original_task_bytes = self.task_path.read_bytes()
        with patch.object(source_review, "fetch_for_one_host", return_value=page) as fetch:
            with patch.object(source_review, "generate_json", return_value=model) as generate:
                result = source_review.run_review(
                    self.task_id,
                    ["sheet.com.vn"],
                    approve_read_only=True,
                    max_pages=2,
                )
        self.assertEqual(fetch.call_count, 1)
        generate.assert_called_once()
        self.assertEqual(result["pages_fetched"], 1)
        self.assertEqual(result["matched_quotes"], 1)
        self.assertEqual(result["source_reviews"][1]["status"], "SKIPPED_HOST_NOT_APPROVED")
        self.assertEqual(result["source_reviews"][0]["observations"][1]["quote_status"], "REJECTED_QUOTE")
        self.assertFalse(result["customer_demand_verified"])
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(self.task_path.read_bytes(), original_task_bytes)
        saved = self.data_dir / "reviews" / f"{self.task_id}.json"
        self.assertTrue(saved.is_file())
        with patch.object(source_review, "fetch_for_one_host") as rerun:
            with self.assertRaises(FileExistsError):
                source_review.run_review(
                    self.task_id, ["sheet.com.vn"], approve_read_only=True
                )
            rerun.assert_not_called()


if __name__ == "__main__":
    unittest.main()
