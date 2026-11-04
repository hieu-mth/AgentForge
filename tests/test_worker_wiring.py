import unittest
from unittest.mock import patch

from agentforge import research, source_review


class TestWorkerWiring(unittest.TestCase):

    def test_research_plan_uses_worker(self):
        with patch.object(
            research,
            "generate_json",
            return_value={
                "queries": ["platform fees", "market demand"]
            },
        ) as mocked:
            result = research.plan({
                "topic": "Online business"
            })

        self.assertEqual(len(result["queries"]), 2)

        self.assertEqual(
            mocked.call_args.kwargs["worker_id"],
            "opportunity_researcher",
        )

    def test_research_analysis_uses_worker(self):
        with patch.object(
            research,
            "generate",
            return_value="Evidence is insufficient.",
        ) as mocked:
            result = research.analyze({
                "topic": "Digital products",
                "sources": [
                    {
                        "source_id": "S1",
                        "url": "https://example.com",
                        "snippet": "Example lead",
                    }
                ],
            })

        self.assertEqual(
            result["status"],
            "LEADS_ONLY_NOT_VERIFIED",
        )

        self.assertEqual(
            mocked.call_args.kwargs["worker_id"],
            "opportunity_researcher",
        )

    def test_source_review_uses_worker(self):
        with patch.object(
            source_review,
            "generate_json",
            return_value={"observations": []},
        ) as mocked:
            result = source_review.analyze_page(
                "Example source text for testing."
            )

        self.assertEqual(result, [])

        self.assertEqual(
            mocked.call_args.kwargs["worker_id"],
            "source_reviewer",
        )


if __name__ == "__main__":
    unittest.main()
