"""Finite Studio motion budgets and versioned storyboard contracts."""
import hashlib
import json
import math
from agentforge.features.film_studio.studio_runtime import motion_output

MOTION_OUTPUT = motion_output()
FPS = MOTION_OUTPUT.fps
MAX_DURATION_SECONDS = 60
MOTION_PRODUCTION_SHOT_BUDGET = 32
MOTION_PRESETS = {4: (2, 2), 6: (3, 3), 15: (8, 9),
                  30: (math.ceil(30 * FPS / MOTION_OUTPUT.max_frames), 16)}
MAX_VERSIONS = 12
STORY_FIELDS = ("description", "image_prompt", "motion_prompt", "character_ids",
                "audio", "continuity", "script_range", "shot_id", "frames", "caption", "scene_notes", "duration_weight",
                "suggested_seconds", "shot_reason")


def duration_limits(seconds, moving):
    minimum = 4 if moving else 6
    if type(seconds) is not int or not minimum <= seconds <= MAX_DURATION_SECONDS:
        raise ValueError(f"Thời lượng phải là số nguyên từ {minimum} đến {MAX_DURATION_SECONDS} giây. "
                         "Hãy rút gọn hành động hoặc chia kịch bản thành nhiều video.")
    if moving:
        budget = max(16, math.ceil(seconds * MOTION_PRODUCTION_SHOT_BUDGET / MAX_DURATION_SECONDS))
        return max(2, math.ceil(seconds * FPS / MOTION_OUTPUT.max_frames)), min(seconds, budget)
    return 2, min(6, seconds // 2)


def planned_timeline(seconds, moving, weights):
    minimum, maximum = duration_limits(seconds, moving)
    count = len(weights)
    if not minimum <= count <= maximum:
        raise ValueError(f"{seconds} giây cần {minimum}–{maximum} cảnh. "
                         "Hãy chỉnh thời lượng hoặc chia/gộp các cảnh trước khi duyệt.")
    floor = FPS if moving else 2
    cap = MOTION_OUTPUT.max_frames if moving else seconds
    total = seconds * FPS if moving else seconds
    frames = [floor] * count
    total_weight = sum(weights)
    target = [total * weight / total_weight for weight in weights]
    for _ in range(total - floor * count):
        index = max((i for i in range(count) if frames[i] < cap), key=lambda i: (target[i]-frames[i], -i))
        frames[index] += 1
    return frames if moving else [length * FPS for length in frames]


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
            index = min((i for i in range(count) if frames[i] < MOTION_OUTPUT.max_frames),
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
