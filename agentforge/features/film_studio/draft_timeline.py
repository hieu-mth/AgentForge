"""Finite Studio motion budgets and versioned storyboard contracts."""
import hashlib
import json
import math
from agentforge.features.film_studio import studio_runtime
from agentforge.features.film_studio.studio_runtime import LEGACY_MOTION_OUTPUT

STILL_FPS = 24
MAX_DURATION_SECONDS = 60
MOTION_PRODUCTION_SHOT_BUDGET = 32
MOTION_PRESETS = {4: (2, 2), 6: (3, 3), 15: (8, 9),
                  30: (15, 16)}
MAX_VERSIONS = 12
STORY_FIELDS = ("description", "image_prompt", "motion_prompt", "character_ids",
                "audio", "continuity", "script_range", "shot_id", "frames", "caption", "scene_notes", "duration_weight",
                "suggested_seconds", "shot_reason", "content_scene", "content_shot", "content_shot_count",
                "script_shot_frames", "shot_description", "creative_shot", "segment", "segment_count",
                "creative_camera", "motion_seed", "continuity_plan")


def duration_bounds(moving):
    return {"min": 4 if moving else 6, "max": MAX_DURATION_SECONDS}


def validate_duration(seconds, moving):
    minimum = duration_bounds(moving)["min"]
    if type(seconds) is not int or not minimum <= seconds <= MAX_DURATION_SECONDS:
        raise ValueError(f"Thời lượng phải là số nguyên từ {minimum} đến {MAX_DURATION_SECONDS} giây. "
                         "Hãy rút gọn hành động hoặc chia kịch bản thành nhiều video.")


def duration_limits(seconds, moving, output=LEGACY_MOTION_OUTPUT):
    validate_duration(seconds, moving)
    if moving:
        budget = max(16, math.ceil(seconds * MOTION_PRODUCTION_SHOT_BUDGET / MAX_DURATION_SECONDS))
        return max(2, math.ceil(seconds * output.fps / output.max_frames)), min(seconds, budget)
    return 2, min(6, seconds // 2)


def planned_timeline(seconds, moving, weights, output=LEGACY_MOTION_OUTPUT):
    minimum, maximum = duration_limits(seconds, moving, output)
    count = len(weights)
    if not minimum <= count <= maximum:
        raise ValueError(f"{seconds} giây cần {minimum}–{maximum} cảnh. "
                         "Hãy chỉnh thời lượng hoặc chia/gộp các cảnh trước khi duyệt.")
    floor = output.fps if moving else 2
    cap = output.max_frames if moving else seconds
    total = seconds * output.fps if moving else seconds
    frames = [floor] * count
    total_weight = sum(weights)
    target = [total * weight / total_weight for weight in weights]
    for _ in range(total - floor * count):
        index = max((i for i in range(count) if frames[i] < cap), key=lambda i: (target[i]-frames[i], -i))
        frames[index] += 1
    return frames if moving else [length * STILL_FPS for length in frames]


def scene_shots(seconds, scene_seconds, moving, output=LEGACY_MOTION_OUTPUT):
    """Split ordered content scenes independently, preserving their frame boundaries."""
    _, ceiling = duration_limits(seconds, moving, output)
    fps = output.fps if moving else STILL_FPS
    total = seconds * fps
    budgets = [None if value is None else round(value * fps) for value in scene_seconds]
    missing = budgets.count(None)
    spare = total - sum(value or 0 for value in budgets)
    minimum = 1 if moving else 2 * fps
    if (not missing and spare != 0) or (missing and spare < missing * minimum):
        raise ValueError(f"Tổng thời lượng cảnh nội dung không khớp mục tiêu {seconds} giây. "
                         "Hãy điều chỉnh tổng thời lượng hoặc mốc thời gian trong kịch bản.")
    if missing:
        share, extra = divmod(spare, missing)
        for index, budget in enumerate(budgets):
            if budget is None:
                budgets[index] = share + (extra > 0)
                extra -= 1
    if any(budget < minimum for budget in budgets):
        raise ValueError("Có cảnh nội dung quá ngắn để dựng. Hãy tăng thời lượng của cảnh.")
    cap = output.max_frames if moving else total
    result = []
    for budget in budgets:
        count = math.ceil(budget / cap)
        frames, extra = divmod(budget, count)
        result.append([frames + (index < extra) for index in range(count)])
    count = sum(map(len, result))
    if count > ceiling:
        raise ValueError(f"{seconds} giây cần {count} shot để giữ ranh giới cảnh, nhưng ngân sách là {ceiling} shot. "
                         "Hãy điều chỉnh thời lượng, hoặc chia thành hai video.")
    return result


def shot_limits(seconds):
    if seconds not in MOTION_PRESETS:
        raise ValueError("Phim chuyển động hỗ trợ 4, 6, 15 hoặc 30 giây.")
    return MOTION_PRESETS[seconds]


def timeline(seconds, count, weights=None, output=LEGACY_MOTION_OUTPUT):
    minimum, maximum = shot_limits(seconds)
    if not minimum <= count <= maximum:
        raise ValueError("Số cảnh vượt ngân sách của preset thời lượng.")
    total = seconds * output.fps
    if total > count * output.max_frames:
        raise ValueError("Motion output cannot cover this legacy preset.")
    if seconds == 30 and weights is not None:
        if len(weights) != count or any(type(weight) is not int or not 1 <= weight <= 3 for weight in weights):
            raise ValueError("Trọng số thời lượng cảnh phải nằm trong khoảng 1–3.")
        floor = min(40 * output.fps // 24, output.max_frames)
        frames = [floor] * count
        for _ in range(total - floor * count):
            index = min((i for i in range(count) if frames[i] < output.max_frames),
                        key=lambda i: ((frames[i] - floor + 1) / weights[i], i))
            frames[index] += 1
        return frames
    frames, extra = divmod(total, count)
    return [frames + (index < extra) for index in range(count)]


def job_fps(job):
    return studio_runtime.job_output(job).fps if job["brief"].get("mode") == "motion" else STILL_FPS


def storyboard_layout(job, count, weights=None):
    brief = job["brief"]
    plan = job.get("duration_plan") or {}
    if plan.get("content_scene_count"):
        if "creative_plan" in plan:
            from agentforge.features.film_studio import creative_plan
            compiled = creative_plan.compiled_shots(plan["creative_plan"], studio_runtime.job_output(job))
            if compiled != plan["shots"]:
                raise ValueError("Các segment không khớp kế hoạch Creative Director.")
        frames = [shot["script_shot_frames"] for shot in plan["shots"]]
        total = brief["seconds"] * job_fps(job)
        cap = studio_runtime.job_output(job).max_frames if brief.get("mode") == "motion" else total
        if (count != len(frames) or any(type(frame) is not int or not 1 <= frame <= cap for frame in frames)
                or sum(frames) != total):
            raise ValueError("Timeline cảnh gốc đã thay đổi. Hãy tạo một bản nháp mới để đổi cấu trúc.")
        return frames
    if "duration_mode" in brief:
        return planned_timeline(brief["seconds"], brief.get("mode") == "motion",
                                               weights if weights is not None else [2]*count,
                                               studio_runtime.job_output(job))
    if brief.get("mode") == "motion":
        return timeline(brief["seconds"], count, weights, studio_runtime.job_output(job))
    if not 2 <= count <= 6 or count * 2 > brief["seconds"]:
        raise ValueError("Bản nháp ảnh tĩnh cần 2–6 cảnh và ít nhất 2 giây mỗi cảnh.")
    length, extra = divmod(brief["seconds"], count)
    return [(length + (index < extra)) * STILL_FPS for index in range(count)]


def editor_constraints(job):
    """Presentation metadata only; never stored or included in approval digests."""
    brief = job["brief"]
    moving = brief.get("mode") == "motion"
    bounds = duration_bounds(moving)
    result = {"duration": bounds, "layout_editable": False, "duration_editable": False,
              "min_scenes": None, "max_scenes": None}
    if (not job.get("board") or not job.get("storyboard_version")
            or job.get("status") not in {"STORYBOARD_REVIEW", "REVIEW", "FAILED"}
            or job["storyboard_version"] >= MAX_VERSIONS
            or (job.get("duration_plan") or {}).get("content_scene_count")):
        return result
    seconds = brief.get("seconds")
    try:
        if brief.get("duration_mode") in {"auto", "manual"}:
            lo, hi = duration_limits(seconds, moving, studio_runtime.job_output(job))
            result["duration_editable"] = True
        elif moving:
            lo, hi = shot_limits(seconds)
        else:
            lo, hi = duration_limits(seconds, False)
    except (ValueError, TypeError, KeyError):
        return result
    result.update(layout_editable=lo <= hi, min_scenes=lo, max_scenes=hi)
    return result


def snapshot(job):
    board = job["board"]
    value = {"version": job["storyboard_version"], "title": board["title"],
            "continuity": board["continuity"], "cast": job.get("cast", {}),
            "seconds": job["brief"]["seconds"], "ratio": job["brief"]["ratio"],
            "scenes": [{key: scene[key] for key in STORY_FIELDS if key in scene}
                       for scene in board["scenes"]]}
    if "audio_plan" in job:
        value["audio_plan"] = job["audio_plan"]
    if "planning_output" in job:
        value["planning_output"] = job["planning_output"]
    if "motion_plan" in job:
        value["motion_plan"] = job["motion_plan"]
    if "studio_plan" in job:
        value["studio_plan"] = job["studio_plan"]
    if "production_plan" in job:
        value["production_plan"] = job["production_plan"]
    creative = job.get("duration_plan", {}).get("creative_plan")
    if creative is not None:
        value["creative_plan"] = creative
    return value


def digest(job):
    encoded = json.dumps(snapshot(job), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def captions(scenes, fps=STILL_FPS):
    from agentforge.features.film_studio.production import _srt_clock

    start = 0
    entries = []
    for scene in scenes:
        end = start + scene["frames"]
        if scene.get("caption"):
            entries.append(f"{len(entries)+1}\n{_srt_clock(start/fps)} --> {_srt_clock(end/fps)}\n"
                           + scene["caption"] + "\n")
        start = end
    return ("\n".join(entries) + "\n").encode("utf-8") if entries else b""
