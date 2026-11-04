import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import company_flow, source_reader, source_review, task_inbox


class TestCompanyFlow(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)

        self.reports = root / "research"
        self.reports.mkdir()

        self.data_dir = root / "company"
        self.research_id = "a" * 32

        self.patches = [
            patch.object(company_flow, "REPORTS", self.reports),
            patch.object(task_inbox, "DATA_DIR", self.data_dir),
        ]

        for item in self.patches:
            item.start()

        self.report = {
            "research_id": self.research_id,
            "topic": "Test opportunity",
            "status": "LEADS_ONLY_NOT_VERIFIED",
            "sources": [
                {
                    "source_id": "S1",
                    "url": "https://example.org/article-one",
                },
                {
                    "source_id": "S2",
                    "url": "https://example.org/article-two",
                },
            ],
        }

        self.save_report()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def save_report(self):
        path = self.reports / f"{self.research_id}.json"
        path.write_text(
            json.dumps(self.report),
            encoding="utf-8",
        )

    def propose(self, ids=None):
        return company_flow.propose_review(
            self.research_id,
            ["S1"] if ids is None else ids,
        )

    def test_creates_review_task_without_network(self):
        with patch.object(source_reader.OPENER, "open") as opener:
            task = self.propose(["S1", "S2"])
            opener.assert_not_called()

        saved = task_inbox.read_task(task["task_id"])

        self.assertEqual(saved["status"], "PROPOSED")
        self.assertEqual(saved["source_ids"], ["S1", "S2"])
        self.assertEqual(len(saved["source_urls"]), 2)
        self.assertFalse(saved["execution_authorized"])
        self.assertFalse(saved["spending_authorized"])

        _, urls, hosts = source_review.get_task_urls(
            task["task_id"]
        )
        self.assertEqual(len(urls), 2)
        self.assertEqual(hosts, ["example.org", "example.org"])

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            self.propose(["S9"])

    def test_unsafe_url_rejected(self):
        self.report["sources"][0]["url"] = (
            "https://127.0.0.1/private"
        )
        self.save_report()

        with patch.object(source_reader.OPENER, "open") as opener:
            with self.assertRaises(ValueError):
                self.propose()
            opener.assert_not_called()

    def test_duplicate_source_ids_rejected(self):
        with self.assertRaises(ValueError):
            self.propose(["S1", "S1"])

    def test_existing_task_cannot_be_overwritten(self):
        task = self.propose()
        path = task_inbox.task_path(task["task_id"])
        original = path.read_bytes()

        with self.assertRaises(FileExistsError):
            self.propose(["S2"])

        self.assertEqual(path.read_bytes(), original)

    def test_mismatched_report_id_rejected(self):
        self.report["research_id"] = "b" * 32
        self.save_report()

        with self.assertRaises(ValueError):
            self.propose()

    def test_non_lead_report_rejected(self):
        self.report["status"] = "MODEL_ANALYSIS_FAILED"
        self.save_report()

        with self.assertRaises(ValueError):
            self.propose()

    def test_invalid_research_id_rejected(self):
        with self.assertRaises(ValueError):
            company_flow.propose_review("../outside", ["S1"])


if __name__ == "__main__":
    unittest.main()
