"""Validate authored creative shots and split them into runtime-sized segments."""
import math

from agentforge.features.film_studio.draft_timeline import MOTION_PRODUCTION_SHOT_BUDGET


def compile_plan(scenes, proposed, output):
    if not isinstance(proposed, list) or len(scenes) != len(proposed):
        raise ValueError("Creative plan must preserve the authored scenes")
    result = []
    offset = 0
    segment_count = 0
    for scene, shots in zip(scenes, proposed):
        if not isinstance(shots, list) or not 1 <= len(shots) <= min(16, scene["frames"]):
            raise ValueError("Invalid creative shot count")
        weights = []
        ordered_ids = [f"A{index+1:02d}" for index in range(len(scene["actions"]))]
        next_action = 0
        for shot in shots:
            if not isinstance(shot, dict) or set(shot) != {"actions", "seconds", "camera", "intent"}:
                raise ValueError("Invalid creative shot schema")
            action_ids = shot["actions"]
            if (not isinstance(action_ids, list) or not action_ids
                    or action_ids != ordered_ids[next_action:next_action + len(action_ids)]):
                raise ValueError("Creative plan must cover each action once in source order")
            next_action += len(action_ids)
            weight = shot["seconds"]
            if type(weight) not in (int, float) or not 0.1 <= weight <= 60 or not math.isfinite(weight):
                raise ValueError("Invalid creative shot duration")
            if any(not isinstance(shot[key], str) or not 1 <= len(shot[key].strip()) <= 240
                   for key in ("camera", "intent")):
                raise ValueError("Invalid camera or creative intent")
            weights.append(weight)
        if next_action != len(scene["actions"]):
            raise ValueError("Creative plan omitted source actions")
        frames = [1] * len(shots)
        for _ in range(scene["frames"] - len(shots)):
            index = max(range(len(shots)), key=lambda i: (
                scene["frames"] * weights[i] / sum(weights) - frames[i], -i))
            frames[index] += 1
        compiled = []
        for shot, length in zip(shots, frames):
            segments = []
            count = math.ceil(length / output.max_frames)
            segment_count += count
            if segment_count > MOTION_PRODUCTION_SHOT_BUDGET:
                raise ValueError("Creative plan exceeds the runtime segment budget")
            size, extra = divmod(length, count)
            for index in range(count):
                frame_count = size + (index < extra)
                segments.append({"start_frame": offset, "frames": frame_count, "continuation": index > 0})
                offset += frame_count
            compiled.append({**shot, "frames": length, "segments": segments})
        result.append({**scene, "creative_shots": compiled})
    return {"fps": output.fps, "total_frames": offset, "scenes": result}
