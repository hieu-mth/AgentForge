"""Finite Studio motion budgets and versioned storyboard contracts."""
import hashlib
import json

FPS = 24
MOTION_PRESETS = {4: (2, 2), 6: (3, 3), 15: (8, 9)}
MAX_VERSIONS = 12
STORY_FIELDS = ("description", "image_prompt", "motion_prompt", "character_ids",
                "audio", "continuity", "script_range", "shot_id", "frames", "caption", "scene_notes")


def shot_limits(seconds):
    if seconds not in MOTION_PRESETS:
        raise ValueError("Phim chuyển động hỗ trợ 4, 6 hoặc 15 giây.")
    return MOTION_PRESETS[seconds]


def timeline(seconds, count):
    minimum, maximum = shot_limits(seconds)
    if not minimum <= count <= maximum:
        raise ValueError("Số cảnh vượt ngân sách của preset thời lượng.")
    frames, extra = divmod(seconds * FPS, count)
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
