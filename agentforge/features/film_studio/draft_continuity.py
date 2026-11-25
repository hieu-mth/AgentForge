"""AI-authored shot boundaries and dependency-safe checkpoint invalidation."""
TRANSITIONS = ("CUT", "CAMERA_CHANGE", "CONTINUE")
STATE_LIMIT = 120


def validate_entry(entry, index, previous_id):
    if not isinstance(entry, dict) or set(entry) != {"transition", "start_state", "end_state", "previous_shot_id"}:
        raise ValueError("Invalid motion continuity plan")
    if (entry["transition"] not in TRANSITIONS or (index == 0 and entry["transition"] != "CUT")
            or entry["previous_shot_id"] != previous_id):
        raise ValueError("Invalid continuity boundary")
    for field in ("start_state", "end_state"):
        value = entry[field]
        if (not isinstance(value, str) or not 1 <= len(value.strip()) <= STATE_LIMIT
                or any(ord(char) < 32 for char in value)):
            raise ValueError("Invalid continuity state")
    return entry


def validate(job):
    scenes = job["board"]["scenes"]
    for index, scene in enumerate(scenes):
        if "continuity_plan" in scene:
            if job["brief"].get("mode") != "motion":
                raise ValueError("Motion continuity needs motion mode")
            validate_entry(scene["continuity_plan"], index, scenes[index-1]["shot_id"] if index else None)


def propose(job, infer):
    """AI chooses cuts; Python only validates identity, order and bounded fields."""
    scenes = job["board"]["scenes"]
    entries = []
    for index in range(0, len(scenes), 4):
        batch = scenes[index:index+4]
        keys = [scene["shot_id"] for scene in batch]
        schema = {"type": "object", "additionalProperties": False, "required": ["shots"],
                  "properties": {"shots": {"type": "array", "minItems": len(keys), "maxItems": len(keys),
                    "items": {"type": "object", "additionalProperties": False,
                    "required": ["shot_id", "transition", "start_state", "end_state"],
                    "properties": {"shot_id": {"type": "string", "enum": keys},
                                   "transition": {"type": "string", "enum": list(TRANSITIONS)},
                                   "start_state": {"type": "string", "minLength": 1, "maxLength": STATE_LIMIT},
                                   "end_state": {"type": "string", "minLength": 1, "maxLength": STATE_LIMIT}}}}}}
        def context(scene):
            return {key: scene[key] for key in ("shot_id", "description", "motion_prompt", "image_prompt",
                                                "character_ids", "creative_camera", "continuity", "seconds") if key in scene}
        result = infer(
            "Direct the visual boundaries for these existing shots in order. Preserve authored action, cast and camera. "
            "CUT is a new scene or intentional discontinuity; CAMERA_CHANGE is a new angle retaining character/prop state; "
            "CONTINUE means same framing and continuous action, so the previous clip's last displayed frame will be used "
            "as the next shot's exact image input. Never choose CONTINUE across an intentional angle or scene change. "
            "First film shot must be CUT. Describe concrete initial and final pose, props and location in short English "
            "states of at most 120 characters. Do not repeat the preceding action or invent a new event.",
            {"continuity": job["board"]["continuity"], "first_batch": index == 0,
             "previous": context(scenes[index-1]) if index else None,
             "previous_end": entries[-1]["end_state"] if entries else None,
             "shots": [context(scene) for scene in batch]}, schema)
        rows = result.get("shots") if isinstance(result, dict) and set(result) == {"shots"} else None
        if not isinstance(rows, list) or len(rows) != len(keys):
            raise ValueError("AI returned incomplete continuity boundaries")
        for offset, row in enumerate(rows):
            position = index + offset
            if (not isinstance(row, dict) or set(row) != {"shot_id", "transition", "start_state", "end_state"}
                    or row["shot_id"] != keys[offset]):
                raise ValueError("AI changed shot order")
            entry = {key: row[key] for key in ("transition", "start_state", "end_state")}
            entry["previous_shot_id"] = scenes[position-1]["shot_id"] if position else None
            entries.append(validate_entry(entry, position, entry["previous_shot_id"]))
    return entries


def clear_motion(scene):
    for field in ("motion_job", "motion_sha", "motion_source"):
        scene.pop(field, None)


def clear_stale_boundaries(scenes):
    """Reordering/removing shots must not implicitly authorize a different predecessor."""
    for index, scene in enumerate(scenes):
        plan = scene.get("continuity_plan")
        if plan and (plan["previous_shot_id"] != (scenes[index-1]["shot_id"] if index else None)
                     or (index == 0 and plan["transition"] != "CUT")):
            scene.pop("continuity_plan")
            clear_motion(scene)


def invalidate_dependencies(scenes, old_scenes, old_checkpoints):
    """Invalidate chained descendants only; stop propagation at a cut or new angle."""
    previous = {item["shot_id"]: (item, old_checkpoints[i]) for i, item in enumerate(old_scenes)}
    for index, scene in enumerate(scenes):
        plan = scene.get("continuity_plan")
        if not plan or plan["transition"] != "CONTINUE":
            continue
        parent = scenes[index-1]
        old = previous.get(parent["shot_id"])
        if (not old or not parent.get("motion_sha") or parent["motion_sha"] != old[1].get("motion_sha")
                or parent["frames"] != old[0]["frames"]):
            clear_motion(scene)


def prompt(scene):
    text = scene.get("motion_prompt", scene["description"])
    notes = scene.get("scene_notes", "")
    plan = scene.get("continuity_plan")
    prefix = "Animate this shot with natural movement, preserving character identity. "
    if not plan:
        return prefix + text + " " + notes
    boundary = (" Start state: " + plan["start_state"] + ". End state: " + plan["end_state"] + ". ")
    if plan["transition"] == "CONTINUE":
        boundary += "Continue from supplied frame without replaying the previous action. "
    # Bound the adapter prompt; retain the authored motion and boundary before optional notes.
    return (prefix + text + boundary + notes)[:1100]
