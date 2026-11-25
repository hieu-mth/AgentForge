import unittest
from unittest.mock import Mock

from agentforge.features.film_studio.creative_plan import (
    compile_plan, compiled_shots, propose_scene, validate_scene_shots,
)
from agentforge.features.film_studio.studio_contracts import MotionOutput


class CreativePlanTests(unittest.TestCase):
    def test_director_sees_story_timing_not_runtime_frames(self):
        scene = {"scene": 1, "source_range": [0, 20], "frames": 144,
                 "actions": ["approach", "open"]}
        shots = [{"actions": ["A01", "A02"], "seconds": 6,
                  "camera": "wide", "intent": "show the event"}]
        infer = Mock(return_value={"shots": shots})
        self.assertEqual(propose_scene(scene, [], 24, infer), shots)
        payload = infer.call_args.args[1]
        self.assertEqual(payload["seconds"], 6)
        self.assertNotIn("frames", payload["scene"])
        self.assertEqual(payload["scene"]["actions"], {"A01": "approach", "A02": "open"})
        self.assertEqual(validate_scene_shots(scene["actions"], shots), [6])

    def test_same_creative_intent_compiles_for_different_motion_limits(self):
        scene = {"scene": 1, "source_range": [0, 20], "frames": 144,
                 "actions": ["approach", "open"]}
        shot = {"actions": ["A01", "A02"], "seconds": 6,
                "camera": "wide", "intent": "show the event"}
        short = MotionOutput(24, 49, (512, 288))
        longer = MotionOutput(24, 96, (512, 288))
        plans = [compile_plan([scene], [[shot]], output) for output in (short, longer)]
        for plan in plans:
            compiled = plan["scenes"][0]["creative_shots"][0]
            self.assertEqual({key: compiled[key] for key in shot}, shot)
            self.assertEqual(plan["total_frames"], 144)
        self.assertEqual([len(compiled_shots(plan, output))
                          for plan, output in zip(plans, (short, longer))], [3, 2])

    def test_director_rejects_invalid_creative_fields_before_compilation(self):
        scene = {"frames": 144, "actions": ["open"]}
        for shot in ({"actions": ["A01"], "seconds": 0, "camera": "wide", "intent": "open"},
                     {"actions": ["A01"], "seconds": 6, "camera": "", "intent": "open"},
                     {"actions": ["A01"], "seconds": 6, "camera": "wide"}):
            with self.subTest(shot=shot), self.assertRaises(ValueError):
                propose_scene(scene, [], 24, lambda *_: {"shots": [shot]})

    def test_model_repairs_omissions_with_scene_context_before_compilation(self):
        scene = {"scene": 1, "source_range": [0, 40], "frames": 120,
                 "actions": ["approach", "open", "roll", "recoil", "touch"]}
        output = MotionOutput(24, 49, (512, 288))
        shot = {"seconds": 2.5, "camera": "static", "intent": "follow the action"}
        original = [{**shot, "actions": ["A02"]}, {**shot, "actions": ["A04"]}]
        corrected = [{**shot, "actions": ["A01", "A02", "A03"]}, {**shot, "actions": ["A04", "A05"]}]
        infer = Mock(side_effect=[{"shots": original}, {"shots": corrected}])
        shots = propose_scene(scene, [], output.fps, infer)
        self.assertEqual(infer.call_count, 2)
        repair = infer.call_args.args[1]
        self.assertEqual(repair["previous_shots"], original)
        self.assertEqual(repair["scene"]["actions"]["A03"], "roll")
        self.assertEqual([item["actions"] for item in shots],
                         [["A01", "A02", "A03"], ["A04", "A05"]])
        self.assertEqual([item["actions"] for item in original], [["A02"], ["A04"]])
        plan = compile_plan([scene], [shots], output)
        segments = compiled_shots(plan, output)
        self.assertEqual(sum(segment["script_shot_frames"] for segment in segments), 120)
        self.assertEqual(" ".join(segment["action"] for segment in segments),
                         "approach open roll recoil touch")
        for actions in (["A02", "A01"], ["A01", "A01"], ["A99"]):
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                invalid = propose_scene(scene, [], output.fps,
                                        lambda *_: {"shots": [{**shot, "actions": actions}]})
                compile_plan([scene], [invalid], output)

    def test_even_complete_omission_gets_only_one_revision(self):
        scene = {"frames": 120, "actions": ["open", "react"]}
        for shots in ([], [{"actions": []}], [{"actions": ["A01"]}]):
            with self.subTest(shots=shots):
                infer = Mock(return_value={"shots": shots})
                with self.assertRaises(ValueError):
                    propose_scene(scene, [], 24, infer)
                self.assertEqual(infer.call_count, 2)
                self.assertEqual(infer.call_args.args[1]["required_sequence"], ["A01", "A02"])

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

    def test_segments_in_one_angle_do_not_replay_the_full_action_list(self):
        scene = {"scene": 1, "source_range": [0, 20], "frames": 96, "actions": ["recoil", "touch ball"]}
        shot = {"actions": ["A01", "A02"], "seconds": 4, "camera": "static", "intent": "show the reaction"}
        output = MotionOutput(24, 49, (512, 288))
        plan = compile_plan([scene], [[shot]], output)
        segments = compiled_shots(plan, output)
        self.assertEqual([item["action"] for item in segments], ["recoil", "touch ball"])
        self.assertEqual([item["continued_action"] for item in segments], [False, False])
        self.assertEqual([item["creative_shot"] for item in segments], [1, 1])
