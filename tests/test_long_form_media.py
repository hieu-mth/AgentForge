"""Long-form movie planning contracts: no inference, file execution or upload."""
import copy
import tempfile
import unittest
from pathlib import Path

from agentforge.domains.media.long_form import (
    FilmPlanError, build_plan, estimate_attempts, load_plan, save_plan,
    verify_plan,
)

CAST = [{"id": "hero", "name": "Linh", "visual_bible": "Original dark haired adventurer, blue robe",
         "voice_notes": "Warm Vietnamese voice"}]


def chapter(ident, duration):
    return {"id": ident, "title": ident, "synopsis": "Original story beat, needs shot-by-shot writing",
            "duration_seconds": duration, "character_ids": ["hero"]}


def plan(seconds=20, target=8):
    return build_plan(title="Một câu chuyện gốc", genre="fantasy", style="Cinematic, 16:9",
                      characters=CAST, chapters=[chapter("act-a", seconds)], shot_seconds=target)


class FilmPlanTests(unittest.TestCase):
    def test_long_form_two_hours_plans_shots_but_does_not_claim_movies_exist(self):
        p = build_plan(title="Original movie", genre="fantasy", style="cinematic",
                       characters=CAST,
                       chapters=[chapter("act-one", 2400), chapter("act-two", 2400),
                                 chapter("act-three", 2400)], shot_seconds=8)
        self.assertEqual(p["runtime_seconds"], 7200)
        self.assertEqual(len(p["shots"]), 900)
        self.assertEqual(estimate_attempts(p)["estimated_generation_attempts"], 1800)
        self.assertEqual(p["status"], "PLANNED_NOT_RENDERED")
        self.assertFalse(p["runtime_verified"])
        self.assertFalse(p["youtube_uploaded"])
        self.assertTrue(all(x["motion_prompt"] is None for x in p["shots"]))

    def test_partial_last_shot_does_not_extend_chapter(self):
        p = plan(20)
        self.assertEqual([s["duration_seconds"] for s in p["shots"]], [8, 8, 4])
        self.assertEqual([s["start_seconds"] for s in p["shots"]], [0, 8, 16])
        self.assertEqual(sum(x["duration_seconds"] for x in p["shots"]), 20)

    def test_disallows_unbounded_expansion(self):
        with self.assertRaises(FilmPlanError):
            plan(21_601)
        with self.assertRaises(FilmPlanError):
            build_plan(title="x", genre="x", style="x", characters=CAST,
                       chapters=[chapter("a", 21_600)], shot_seconds=4)

    def test_rejects_non_canonical_and_tampered_plan(self):
        p = plan()
        bad = copy.deepcopy(p)
        bad["shots"][0]["status"] = "READY_FOR_YOUTUBE"
        with self.assertRaises(FilmPlanError):
            verify_plan(bad)
        bad = copy.deepcopy(p)
        bad["plan_sha256"] = "0" * 64
        with self.assertRaises(FilmPlanError):
            verify_plan(bad)

    def test_cast_references_are_explicit(self):
        with self.assertRaises(FilmPlanError):
            build_plan(title="x", genre="fantasy", style="cinematic",
                       chapters=[chapter("a", 16)], characters=[])
        with self.assertRaises(FilmPlanError):
            build_plan(title="x", genre="fantasy", style="cinematic",
                       chapters=[chapter("a", 16)], characters=CAST+CAST)

    def test_exclusive_local_save_reload_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            p = plan()
            path = save_plan(Path(temp), "original-film", p)
            self.assertTrue(path.is_file())
            self.assertEqual(load_plan(Path(temp), "original-film"), p)
            with self.assertRaises(FileExistsError):
                save_plan(Path(temp), "original-film", p)
            with self.assertRaises(FilmPlanError):
                save_plan(Path(temp), "..", p)
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(FilmPlanError):
                load_plan(Path(temp), "original-film")

    def test_attempt_estimate_marks_cost_unknown(self):
        a = estimate_attempts(plan(), attempts_per_shot=3)
        self.assertEqual(a["estimated_generation_attempts"], 9)
        self.assertIsNone(a["estimated_money"])
        self.assertFalse(a["quality_verified"])


if __name__ == "__main__":
    unittest.main()
