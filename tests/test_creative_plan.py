import unittest

from agentforge.features.film_studio.creative_plan import compile_plan, compiled_shots, propose_scene
from agentforge.features.film_studio.studio_contracts import MotionOutput


class CreativePlanTests(unittest.TestCase):
    def test_unequal_creative_shots_fit_runtime_without_reordering_actions(self):
        scenes = [{"frames": 120, "actions": ["approach", "stop"]},
                  {"frames": 120, "actions": ["open", "react"]}]
        shot = {"seconds": 5, "camera": "hold framing", "intent": "maintain continuity"}
        plan = compile_plan(scenes, [[{**shot, "actions": ["A01", "A02"]}],
            [{**shot, "actions": ["A01"], "seconds": 1}, {**shot, "actions": ["A02"], "seconds": 4}]],
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
        for actions in (["A01"], ["A02", "A01"], ["A01", "A01"]):
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                compile_plan([scene], [[{**shot, "actions": actions}]], MotionOutput(24, 49, (512, 288)))

    def test_rejects_invalid_duration_and_modified_frames_using_adapter_limits(self):
        scene = {"scene": 1, "source_range": [0, 20], "frames": 72, "actions": ["open"]}
        shot = {"actions": ["A01"], "camera": "static", "intent": "show the event"}
        output = MotionOutput(12, 20, (320, 192))
        for seconds in (0, -1, True, float("nan")):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                compile_plan([scene], [[{**shot, "seconds": seconds}]], output)
        plan = compile_plan([scene], [[{**shot, "seconds": 6}]], output)
        self.assertEqual([item["script_shot_frames"] for item in compiled_shots(plan, output)], [18]*4)
        plan["scenes"][0]["creative_shots"][0]["segments"][0]["frames"] = 0
        with self.assertRaises(ValueError):
            compiled_shots(plan, output)
        with self.assertRaisesRegex(ValueError, "cấu trúc"):
            propose_scene(scene, [], output.fps, lambda *_: {"unexpected": []})
