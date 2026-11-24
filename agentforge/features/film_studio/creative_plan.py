"""Validate authored creative shots and split them into runtime-sized segments."""
import math

from agentforge.features.film_studio.draft_timeline import duration_limits


def compile_plan(scenes, proposed, output):
    if (not scenes or not isinstance(proposed, list) or len(scenes) != len(proposed)
            or any(type(scene.get("frames")) is not int or scene["frames"] < 1 for scene in scenes)
            or type(output.fps) is not int or output.fps < 1
            or type(output.max_frames) is not int or output.max_frames < 1):
        raise ValueError("Creative plan must preserve the authored scenes")
    seconds, remainder = divmod(sum(scene["frames"] for scene in scenes), output.fps)
    if remainder:
        raise ValueError("Creative plan requires a whole-second production frame budget")
    minimum, maximum = duration_limits(seconds, True, output)
    result = []
    offset = 0
    segment_count = 0
    for scene_number, (scene, shots) in enumerate(zip(scenes, proposed), 1):
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
                expected = next(iter(ordered_ids[next_action:next_action + 1]), None)
                detail = f"Hành động kế tiếp phải là {expected}." if expected else "Cảnh đã đủ hành động."
                raise ValueError(
                    f"Cảnh {scene_number}, góc quay {len(weights) + 1}: chuỗi hành động không hợp lệ. {detail}"
                )
            next_action += len(action_ids)
            weight = shot["seconds"]
            if type(weight) not in (int, float) or not 0.1 <= weight <= 60 or not math.isfinite(weight):
                raise ValueError("Invalid creative shot duration")
            if any(not isinstance(shot[key], str) or not 1 <= len(shot[key].strip()) <= 240
                   for key in ("camera", "intent")):
                raise ValueError("Invalid camera or creative intent")
            weights.append(weight)
        if next_action != len(scene["actions"]):
            missing = ", ".join(ordered_ids[next_action:])
            raise ValueError(f"Cảnh {scene_number}: kế hoạch thiếu hành động {missing}.")
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
            if segment_count > maximum:
                raise ValueError("Creative plan exceeds the runtime segment budget")
            size, extra = divmod(length, count)
            for index in range(count):
                frame_count = size + (index < extra)
                segments.append({"start_frame": offset, "frames": frame_count, "continuation": index > 0})
                offset += frame_count
            compiled.append({**shot, "frames": length, "segments": segments})
        result.append({**scene, "creative_shots": compiled})
    if segment_count < minimum:
        raise ValueError("Creative plan does not meet the production segment minimum")
    return {"fps": output.fps, "total_frames": offset, "scenes": result}


def compiled_shots(plan, output):
    """Recompute the canonical timeline when reading a saved plan."""
    try:
        scenes = [{key: value for key, value in scene.items() if key != "creative_shots"} for scene in plan["scenes"]]
        proposed = [[{k: shot[k] for k in ("actions", "seconds", "camera", "intent")}
                     for shot in scene["creative_shots"]] for scene in plan["scenes"]]
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Kế hoạch Creative Director đã lưu có cấu trúc không hợp lệ.") from exc
    if compile_plan(scenes, proposed, output) != plan:
        raise ValueError("Timeline Creative Director không khớp cấu hình runtime.")
    result = []
    for scene in plan["scenes"]:
        start = len(result)
        for index, shot in enumerate(scene["creative_shots"], 1):
            actions = [scene["actions"][int(key[1:])-1] for key in shot["actions"]]
            count = len(shot["segments"])
            for segment_index, segment in enumerate(shot["segments"], 1):
                frames = segment["frames"]
                first = (segment_index - 1) * len(actions) // count
                end = max(first + 1, segment_index * len(actions) // count)
                continues = segment_index > 1 and (segment_index - 2) * len(actions) // count == first
                result.append({"content_scene": scene["scene"], "script_range": scene["source_range"],
                               "content_shot": len(result)-start+1, "script_shot_frames": frames,
                               "suggested_seconds": frames / output.fps, "action": " ".join(actions[first:end]),
                               "reason": shot["intent"], "creative_shot": index, "segment": segment_index,
                               "segment_count": count, "continued_action": continues,
                               "creative_camera": shot["camera"]})
        for item in result[start:]:
            item["content_shot_count"] = len(result) - start
    return result


def propose_scene(scene, global_constraints, fps, infer):
    actions = {f"A{index+1:02d}": action for index, action in enumerate(scene["actions"])}
    if not actions:
        raise ValueError("Không tìm thấy hành động rõ trong cảnh để lập kế hoạch góc quay.")
    shot = {"type": "object", "additionalProperties": False,
            "required": ["actions", "seconds", "camera", "intent"],
            "properties": {
                "actions": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": list(actions)}},
                "seconds": {"type": "number", "minimum": 0.1, "maximum": 60},
                "camera": {"type": "string", "minLength": 1, "maxLength": 240},
                "intent": {"type": "string", "minLength": 1, "maxLength": 240}}}
    instructions = (
        "Direct this scene. Group adjacent actions when one camera angle serves them. "
        "Use each supplied action ID exactly once in order. Respect authored camera and constraints. "
        "Give relative duration, camera and storytelling intent. Do not invent actions."
    )
    payload = {"scene": {**scene, "actions": actions}, "global_constraints": global_constraints,
               "seconds": scene["frames"] / fps}
    schema = {"type": "object", "additionalProperties": False, "required": ["shots"],
              "properties": {"shots": {"type": "array", "minItems": 1, "maxItems": 16, "items": shot}}}
    for attempt in range(2):
        result = infer(instructions, payload, schema)
        if not isinstance(result, dict) or result.keys() != {"shots"} or not isinstance(result["shots"], list):
            raise ValueError("AI trả cấu trúc kế hoạch góc quay không hợp lệ.")
        shots = result["shots"]
        if not 1 <= len(shots) <= 16 or any(
                not isinstance(item, dict) or not isinstance(item.get("actions"), list)
                or not item["actions"] for item in shots):
            raise ValueError("Mỗi góc quay cần ít nhất một hành động.")
        sequence = [action for item in shots for action in item["actions"]]
        if sequence == list(actions):
            return shots
        if attempt == 0:
            instructions += " Revise the previous shots, including framing and pacing, to cover the required sequence."
            payload = {**payload, "previous_shots": shots, "required_sequence": list(actions)}
    raise ValueError("AI vẫn chưa giữ đúng thứ tự và đầy đủ hành động sau một lần sửa.")
