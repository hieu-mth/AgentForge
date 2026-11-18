"""Image prompts must be scene-specific and not inherit retired commerce defaults."""
import unittest

from agentforge.features.media.visual_jobs import _prompt


class VisualPromptTests(unittest.TestCase):
    def test_film_prompt_uses_owner_subject_without_business_styling(self):
        one = _prompt("mèo trắng phong cách hoạt hình", "nhảy qua hàng rào", 0, "video")
        two = _prompt("mèo trắng phong cách hoạt hình", "ngủ bên cửa sổ", 1, "video")
        self.assertIn("mèo trắng", one)
        self.assertIn("nhảy qua hàng rào", one)
        self.assertIn("ngủ bên cửa sổ", two)
        self.assertNotEqual(one, two)
        self.assertNotIn("Commercial editorial", one)
        self.assertNotIn("Product/subject", one)
        self.assertLessEqual(len(one), 450)

    def test_long_brief_reserves_space_for_each_scene(self):
        text = _prompt("mèo " * 100, "bước lên cây " * 25, 0, "image")
        self.assertIn("bước lên cây", text)
        self.assertLessEqual(len(text), 450)

    def test_invalid_scene_is_rejected(self):
        with self.assertRaises(ValueError):
            _prompt("mèo", "", 0, "video")


if __name__ == "__main__":
    unittest.main()
