"""Owner-visible storyboard projection must be bounded and fail closed."""
import unittest
from agentforge.core import result_view


class StoryboardProjectionTests(unittest.TestCase):
    def setUp(self):
        self.result = {
            "title": "Video thử nghiệm",
            "scenes": [
                {"headline": "Mở đầu", "caption": "Giới thiệu chủ đề", "duration_seconds": 4},
                {"headline": "Liên hệ", "caption": "Mời tư vấn", "duration_seconds": 5},
            ],
            "private_prompt": "DO NOT EXPOSE",
        }

    def test_owner_preview_is_bounded_and_no_unexpected_fields(self):
        view = result_view.present("media.copy_draft", self.result)
        self.assertEqual(view["kind"], "storyboard")
        self.assertEqual(view["title"], "Video thử nghiệm")
        self.assertEqual(len(view["scenes"]), 2)
        self.assertNotIn("private_prompt", str(view))
        self.assertEqual(view["review_required"], True)
        self.assertFalse(view["verified_claims"])

    def test_unknown_skill_has_no_result_projection(self):
        self.assertIsNone(result_view.present("unknown.skill", self.result))

    def test_invalid_storyboard_fails_closed(self):
        bad = dict(self.result)
        bad["scenes"] = [{"headline": "A", "caption": "B", "duration_seconds": 99}]
        self.assertIsNone(result_view.present("media.copy_draft", bad))

    def test_extra_scenes_are_bounded(self):
        many = dict(self.result)
        many["scenes"] = self.result["scenes"] * 10
        self.assertEqual(len(result_view.present("media.copy_draft", many)["scenes"]), 5)


if __name__ == "__main__":
    unittest.main()
