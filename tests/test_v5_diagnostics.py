"""V5 error classification stays actionable without exposing untrusted model text."""
import json
import unittest

from agentforge.core.skill_runner import _safe_failure


class V5DiagnosticsTests(unittest.TestCase):
    def test_schema_errors_are_stage_specific(self):
        cases = [
            ("webapp.architect", ValueError("ARCHITECTURE_INVALID: ui_sections"),
             "V5_ARCHITECTURE_SCHEMA_INVALID"),
            ("webapp.review", ValueError("REVIEW_INVALID: recommendation"),
             "V5_REVIEW_SCHEMA_INVALID"),
            ("webapp.review", ValueError("ARCHITECTURE_INVALID: schema not canonical"),
             "V5_ARCHITECTURE_SOURCE_INVALID"),
            ("webapp.architect", json.JSONDecodeError("invalid", "{", 0),
             "V5_MODEL_JSON_INVALID"),
        ]
        for skill, exc, expected in cases:
            with self.subTest(skill=skill, expected=expected):
                self.assertTrue(_safe_failure(skill, exc).startswith(expected + ":"))

    def test_untrusted_exception_text_is_not_echoed(self):
        private = "SECRET-SOURCE-AND-TOKEN"
        for skill in ("webapp.architect", "webapp.audit", "webapp.review"):
            for exc in (ValueError(private), ValueError("REVIEW_INVALID: " + private)):
                output = _safe_failure(skill, exc)
                self.assertNotIn(private, output)
                self.assertLess(len(output), 240)


if __name__ == "__main__":
    unittest.main()
