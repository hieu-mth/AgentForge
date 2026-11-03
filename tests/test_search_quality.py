import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agentforge import pain_discovery
from agentforge.search_quality import classify_community_hit


class TestSearchQuality(unittest.TestCase):

    def test_reject_noncommunity_source(self):
        result = classify_community_hit({
            "url": "https://wikipedia.org/wiki/Excel",
            "title": "Excel inventory",
            "snippet": "Inventory problems"
        })
        self.assertEqual(result, "REJECT_NOT_COMMUNITY")

    def test_reject_spoofed_domain(self):
        result = classify_community_hit({
            "url": "https://reddit.com.evil.example/post",
            "title": "Excel inventory",
            "snippet": "Inventory tracking problem"
        })
        self.assertEqual(result, "REJECT_NOT_COMMUNITY")

    def test_reject_off_topic_community_post(self):
        result = classify_community_hit({
            "url": "https://voz.vn/t/example",
            "title": "Tin giai tri",
            "snippet": "Quan ly dien dan"
        })
        self.assertEqual(result, "REJECT_OFF_TOPIC")

    def test_relevant_source_requires_review(self):
        result = classify_community_hit({
            "url": "https://reddit.com/r/smallbusiness/comments/example",
            "title": "Excel inventory tracking",
            "snippet": "My stock spreadsheet has errors"
        })
        self.assertEqual(result, "REVIEW_ONLY_NOT_VERIFIED")

    def test_collection_keeps_rejected_for_audit(self):
        hits = [
            {
                "url": "https://reddit.com/r/smallbusiness/comments/example",
                "title": "Excel inventory issues",
                "snippet": "Stock tracking errors in Excel"
            },
            {
                "url": "https://example.com/blog",
                "title": "Excel inventory tips",
                "snippet": "Stock tracking errors"
            }
        ]

        with patch.object(
            pain_discovery, "web_search", return_value=hits
        ):
            with redirect_stdout(io.StringIO()):
                sources, errors = pain_discovery.collect()

        self.assertEqual(len(sources), 2)
        self.assertEqual(errors, [])
        self.assertEqual(
            sources[0]["quality_status"],
            "REVIEW_ONLY_NOT_VERIFIED"
        )
        self.assertEqual(
            sources[1]["quality_status"],
            "REJECT_NOT_COMMUNITY"
        )

    def test_no_reviewable_sources_skips_model(self):
        hits = [{
            "url": "https://example.com/marketing",
            "title": "Free Excel inventory tips",
            "snippet": "Inventory tracking for shops"
        }]

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "pain_leads.json"

            with patch.object(pain_discovery, "OUTPUT", output):
                with patch.object(
                    pain_discovery, "web_search", return_value=hits
                ):
                    with patch.object(
                        pain_discovery, "generate_json"
                    ) as model:
                        with redirect_stdout(io.StringIO()):
                            pain_discovery.main()

                        model.assert_not_called()

            data = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(
            data["status"],
            "NO_REVIEWABLE_COMMUNITY_LEADS"
        )
        self.assertEqual(data["reviewable_sources"], 0)
        self.assertEqual(data["rejected_sources"], 1)
        self.assertEqual(data["signals"], [])


if __name__ == "__main__":
    unittest.main()