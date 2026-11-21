"""Finite Studio motion budgets and versioned storyboard contracts."""
import hashlib
import json
import math

FPS = 24
LTX_CLIP_FRAMES = 49
MOTION_PRODUCTION_SHOT_BUDGET = 16
MOTION_PRESETS = {4: (2, 2), 6: (3, 3), 15: (8, 9),
                  30: (math.ceil(30 * FPS / LTX_CLIP_FRAMES), MOTION_PRODUCTION_SHOT_BUDGET)}
MAX_VERSIONS = 12
STORY_FIELDS = ("description", "image_prompt", "motion_prompt", "character_ids",
                "audio", "continuity", "script_range", "shot_id", "frames", "caption", "scene_notes", "duration_weight")


def shot_limits(seconds):
    if seconds not in MOTION_PRESETS:
        raise ValueError("Phim chuyển động hỗ trợ 4, 6, 15 hoặc 30 giây.")
    return MOTION_PRESETS[seconds]


def timeline(seconds, count, weights=None):
    minimum, maximum = shot_limits(seconds)
    if not minimum <= count <= maximum:
        raise ValueError("Số cảnh vượt ngân sách của preset thời lượng.")
    total = seconds * FPS
    if seconds == 30 and weights is not None:
        if len(weights) != count or any(type(weight) is not int or not 1 <= weight <= 3 for weight in weights):
            raise ValueError("Trọng số thời lượng cảnh phải nằm trong khoảng 1–3.")
        floor = 40
        frames = [floor] * count
        for _ in range(total - floor * count):
            index = min((i for i in range(count) if frames[i] < LTX_CLIP_FRAMES),
                        key=lambda i: ((frames[i] - floor + 1) / weights[i], i))
            frames[index] += 1
        return frames
    frames, extra = divmod(total, count)
    return [frames + (index < extra) for index in range(count)]


def snapshot(job):
    board = job["board"]
    return {"version": job["storyboard_version"], "title": board["title"],
            "continuity": board["continuity"], "cast": job.get("cast", {}),
            "seconds": job["brief"]["seconds"], "ratio": job["brief"]["ratio"],
            "scenes": [{key: scene[key] for key in STORY_FIELDS if key in scene}
                       for scene in board["scenes"]]}


def digest(job):
    encoded = json.dumps(snapshot(job), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def captions(scenes):
    from agentforge.features.film_studio.production import _srt_clock

    start = 0
    entries = []
    for scene in scenes:
        end = start + scene["frames"]
        if scene.get("caption"):
            entries.append(f"{len(entries)+1}\n{_srt_clock(start/FPS)} --> {_srt_clock(end/FPS)}\n"
                           + scene["caption"] + "\n")
        start = end
    return ("\n".join(entries) + "\n").encode("utf-8") if entries else b""
