import unittest

from agentforge.features.film_studio.creative_plan import compile_plan
from agentforge.features.film_studio.studio_contracts import MotionOutput


class CreativePlanTests(unittest.TestCase):
    def test_unequal_creative_shots_fit_runtime_without_reordering_actions(self):
        scenes = [{"frames": 120, "actions": ["approach", "stop"]},
                  {"frames": 120, "actions": ["open", "react"]}]
        shot = {"seconds": 5, "camera": "hold framing", "intent": "maintain continuity"}
        plan = compile_plan(scenes, [[{**shot, "actions": [0, 1]}],
            [{**shot, "actions": [0], "seconds": 1}, {**shot, "actions": [1], "seconds": 4}]],
            MotionOutput(24, 49, (512, 288)))
        self.assertEqual(plan["total_frames"], 240)
        first, second = (scene["creative_shots"] for scene in plan["scenes"])
        self.assertEqual([part["frames"] for part in first[0]["segments"]], [40, 40, 40])
        self.assertEqual([part["frames"] for part in second], [24, 96])
        self.assertEqual([part["continuation"] for part in first[0]["segments"]], [False, True, True])
        self.assertEqual(second[0]["segments"][0]["start_frame"], 120)

    def test_rejects_omitted_duplicate_and_reordered_actions(self):
        scene = {"frames": 120, "actions": ["open", "react"]}
        shot = {"seconds": 5, "camera": "static", "intent": "show the event"}
        for actions in ([0], [1, 0], [0, 0]):
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                compile_plan([scene], [[{**shot, "actions": actions}]], MotionOutput(24, 49, (512, 288)))
