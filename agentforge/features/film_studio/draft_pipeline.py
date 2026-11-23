"""Checkpointed local idea-to-draft production."""
import copy
import hashlib
import os
import json
import re
import shutil
import sqlite3
import threading
from contextlib import closing, contextmanager
from uuid import uuid4

from agentforge import ops_control
from agentforge.ai import model_hub
from agentforge.features.film_studio import characters
from agentforge.features.film_studio import draft_resources, draft_timeline, studio_runtime
from agentforge.features.media import render, visual_jobs
from agentforge.features.film_studio.draft_resources import ResourceWait
from agentforge.integrations import comfy_service
from agentforge.paths import COMPANY_DATA_DIR, WORKSPACE_DIR, ensure_local_root

DB = COMPANY_DATA_DIR / "video_drafts.sqlite3"
MAX_VIDEO = 80 * 1024 * 1024
MAX_MOTION_INPUTS = 256 * 1024 * 1024
SIZES = {"9:16": (720, 1280), "16:9": (1280, 720)}
LOCK = threading.Lock()
ACTIVE = None
IMG_RETRIES = 3
BRIEF_LIMIT = 20_000
OUTLINE_LIMIT = 700
SCRIPT_HEADING = re.compile(r"(?im)^[ \t]*(?:cảnh|scene)\s+[0-9]+\b")
SCRIPT_DIALOGUE = re.compile(r"(?m)^[ \t]*([^\W\d][^:\n]{0,27}):[ \t]*(\S[^\n]*)")
_QUEUE_STATES = {"QUEUED", "RUNNING", "WAITING_RESOURCES"}


class DraftCancelled(Exception):
    pass


def _queue_limit():
    try:
        configured = int(os.getenv("AGENTFORGE_DRAFT_QUEUE_LIMIT", "3"))
    except ValueError:
        configured = 3
    return max(1, min(8, configured))


def _cancellation(ident, *, mark=False):
    with _db(mark) as conn:
        if conn is None:
            return False
        if mark:
            conn.execute("CREATE TABLE IF NOT EXISTS draft_cancellations (id TEXT PRIMARY KEY)")
            conn.execute("INSERT OR IGNORE INTO draft_cancellations VALUES (?)", (ident,))
        table = conn.execute("SELECT 1 FROM sqlite_master WHERE name='draft_cancellations'").fetchone()
        return bool(table and conn.execute("SELECT 1 FROM draft_cancellations WHERE id=?", (ident,)).fetchone())


@contextmanager
def _measured(job, operation, comfy_profile=None):
    if _cancellation(job["id"]):
        raise DraftCancelled
    before = draft_resources.snapshot()
    point = {"operation": operation, "before": before}
    job["resources"] = (job.get("resources", []) + [point])[-24:]
    _save(job)
    try:
        admission_sample = before
        reason = draft_resources.pressure(admission_sample, operation)
        if reason == "VRAM_LOW" and comfy_profile and comfy_profile.get("base_url"):
            if _release_idle_image(comfy_profile):
                admission_sample = point["after_release"] = draft_resources.snapshot()
                reason = draft_resources.pressure(admission_sample, operation)
        if reason:
            raise ResourceWait(reason)
        if operation in {"plan", "cast", "storyboard"}:
            draft_resources.require_gpu("image", admission_sample)
        yield
    finally:
        point["after"] = draft_resources.snapshot()
        _save(job)
        if _cancellation(job["id"]):
            raise DraftCancelled


class DraftNotFound(KeyError):
    """A valid production identifier has no persisted record."""


class DraftStoreUnavailable(RuntimeError):
    def __init__(self, message="Không truy cập được SQLite của bản nháp."):
        super().__init__(message)


def _text(value, max_length, *, label="Văn bản bản nháp"):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= max_length:
        raise ValueError(f"{label} phải có từ 1 đến {max_length} ký tự.")
    return value.strip()


def _number(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Invalid draft number")
    return value


@contextmanager
def _db(create=False):
    try:
        path = ensure_local_root(DB)
        if not create and not path.exists():
            yield None
            return
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path if create else path.as_uri() + "?mode=ro", uri=not create, timeout=3)
        with closing(conn), conn:
            if create:
                conn.execute("CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
            yield conn
    except sqlite3.DatabaseError as exc:
        code = getattr(exc, "sqlite_errorcode", 0) & 0xff
        if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise DraftStoreUnavailable("SQLite của bản nháp đang bận. Hãy thử lại.") from exc
        if code in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}:
            raise DraftStoreUnavailable("Tệp SQLite của bản nháp bị hỏng hoặc sai định dạng.") from exc
        raise DraftStoreUnavailable() from exc
    except OSError as exc:
        raise DraftStoreUnavailable() from exc


def _decode_row(row):
    try:
        job = json.loads(row[0])
        if (not isinstance(job, dict) or not isinstance(job.get("id"), str)
                or not isinstance(job.get("brief"), dict) or not isinstance(job.get("status"), str)):
            raise ValueError("Invalid draft record")
        return job
    except (ValueError, TypeError) as exc:
        raise DraftStoreUnavailable("Bản ghi bản nháp trong SQLite bị lỗi.") from exc


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("Invalid production ID")
    return value


def _folder(ident):
    return ensure_local_root(WORKSPACE_DIR / "drafts" / _id(ident) / "episode-01")


def _read(ident):
    _id(ident)
    with _db() as conn:
        row = conn.execute("SELECT body FROM drafts WHERE id=?", (ident,)).fetchone() if conn else None
        if row is None:
            raise DraftNotFound(ident)
        return _decode_row(row)


def _save(job):
    job["updated_at"] = visual_jobs._now()
    with _db(True) as conn:
        conn.execute("INSERT INTO drafts(id,body) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                     (job["id"], json.dumps(job, ensure_ascii=False)))


def list_drafts():
    with _db() as conn:
        if conn is None:
            return []
        jobs = [_decode_row(row) for row in conn.execute(
            """SELECT body FROM drafts
               ORDER BY COALESCE(julianday(json_extract(body, '$.updated_at')),
                                 julianday(json_extract(body, '$.created_at'))) DESC, rowid DESC
               LIMIT 30""")]
    for job in jobs:
        job["worker_active"] = job["id"] == ACTIVE
        if job["status"] == "RUNNING" and not job["worker_active"] and "storyboard_version" in job:
            job["status"] = "INTERRUPTED"
    return jobs


def jobs_pending():
    if ACTIVE:
        return True
    with _db() as conn:
        return bool(conn and conn.execute(
            "SELECT 1 FROM drafts WHERE json_extract(body,'$.status') IN "
            "('QUEUED','RUNNING','WAITING_RESOURCES') LIMIT 1").fetchone())


@contextmanager
def _worker_slot():
    if not LOCK.acquire(blocking=False):
        raise PermissionError("A draft production is already running")
    try:
        with model_hub.local_process_slot(DB.parent / "video_drafts.worker",
                                          "A draft production is already running"):
            yield
    finally:
        LOCK.release()


def _release_idle_image(profile):
    return studio_runtime.image_adapter(profile).release_idle_models(profile)


def _ask(profile, instructions, data, schema, comfy_profile, *, cpu_only=False, extended_plan=False):
    return studio_runtime.text_adapter(profile).infer_structured(
        profile, instructions, data, schema, cpu_only=cpu_only, extended_plan=extended_plan)


def _object(**properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


STRING = {"type": "string"}


def _story(value, count, duration, cast):
    if not isinstance(value, dict) or value.keys() != {"title", "continuity", "scenes"}:
        raise ValueError("Invalid storyboard object")
    scenes = value["scenes"]
    if not isinstance(scenes, list) or len(scenes) != count:
        raise ValueError("Storyboard scene count does not match the production")
    result = []
    for index, scene in enumerate(scenes):
        fields = {"description", "image_prompt", "character_ids", "audio"}
        if not isinstance(scene, dict) or not fields <= scene.keys() <= fields | {"duration_weight"}:
            raise ValueError("Invalid storyboard scene")
        ids = scene["character_ids"]
        if not isinstance(ids, list) or len(ids) > 2 or any(not isinstance(x, str) or x not in cast for x in ids):
            raise ValueError("Storyboard contains unknown character references")
        result.append({"description": _text(scene["description"], 350),
                       "image_prompt": _text(scene["image_prompt"], 600),
                       "character_ids": list(dict.fromkeys(ids)), "audio": _text(scene["audio"], 160),
                       "seconds": duration // count + (index < duration % count),
                       "asset": None, "job_id": None, "attempts": 0})
        if "duration_weight" in scene:
            result[-1]["duration_weight"] = _number(scene["duration_weight"], 1, 3)
    return {"title": _text(value["title"], 100), "continuity": _text(value["continuity"], 240),
            "scenes": result}


def _activity(job, stage, operation, profile=None, **details):
    job["stage"] = stage
    job["activity"] = {"operation": operation, **details}
    if profile:
        job["activity"].update(provider=profile["provider"], model=profile["model"])
    _save(job)


def _needs_scene_analysis(text):
    return (len(text) > 500 or SCRIPT_HEADING.search(text) is not None
            or SCRIPT_DIALOGUE.search(text) is not None or "\n\n" in text.strip())


def _script_ranges(script, count, seconds):
    headings = [match.start() for match in SCRIPT_HEADING.finditer(script)]
    if len(headings) > count:
        raise ValueError(f"Kịch bản có {len(headings)} cảnh đánh số. Hãy tăng số cảnh hoặc chia thành nhiều bản nháp.")
    dialogue = sum(len(match[2].split()) for match in SCRIPT_DIALOGUE.finditer(script)
                   if not SCRIPT_HEADING.match(match[1]))
    if dialogue > seconds * 3:
        raise ValueError("Thời lượng có thể không đủ cho các dòng lời thoại. Hãy tăng thời lượng hoặc chia kịch bản.")
    points = [0, *headings[1:], len(script)]
    while len(points) <= count:
        # Preserve explicit scene boundaries and prefer paragraph, then line, then word breaks.
        candidates = []
        for start, end in zip(points, points[1:]):
            section = script[start:end]
            first = len(section) - len(section.lstrip())
            last = len(section.rstrip())
            for separator in (r"\n[ \t]*\n", r"\n", r"\s+"):
                breaks = [match.end() for match in re.finditer(separator, section)
                          if match.start() > first and match.end() < last]
                if breaks:
                    middle = min(breaks, key=lambda at: abs(at - len(section) / 2))
                    candidates.append((end-start, start+middle))
                    break
        if not candidates:
            raise ValueError("Kịch bản không có đủ đoạn để chia theo số cảnh đã chọn.")
        points.append(max(candidates)[1])
        points.sort()
    return list(zip(points, points[1:]))


def _script_scene(job, profile, comfy, source, continuity, index, *, proposed_shot=None, cast=None):
    _activity(job, "STORYBOARD", "script", profile, scene=index + 1)
    seconds, extra = divmod(job["brief"]["seconds"], job["brief"]["scene_count"])
    if len(source) > 1000:
        facts = []
        start = 0
        while start < len(source):
            end = min(start + 900, len(source))
            if end < len(source):
                boundary = max(source.rfind("\n", start + 600, end),
                               source.rfind(" ", start + 600, end))
                if boundary != -1:
                    end = boundary + 1
            with _measured(job, "storyboard", comfy):
                output = _ask(profile,
                              "Extract the essential character names, actions, setting and key dialogue "
                              "from this consecutive script excerpt. Keep the source language. Do not invent. "
                              "Return at most 240 characters in facts.",
                              {"excerpt": source[start:end]}, _object(facts=STRING), comfy)
            facts.append(_text(output["facts"], 240))
            start = end
        if sum(map(len, facts)) > 3200:
            raise ValueError("Một cảnh có quá nhiều nội dung. Hãy thêm ranh giới cảnh hoặc chia kịch bản.")
        source = facts
    fields = {key: {**STRING, "minLength": 1, "maxLength": limit} for key, limit in
              (("title", 100), ("continuity", 240), ("description", 350), ("image_prompt", 600), ("audio", 160))}
    weighted = job["brief"]["seconds"] == 30 and job["brief"].get("mode") == "motion"
    if weighted:
        fields["duration_weight"] = {"type": "integer", "minimum": 1, "maximum": 3}
    context = {"source": source, "prior_continuity": continuity, "scene": index + 1,
               "seconds": seconds + (index < extra)}
    if proposed_shot:
        context.update(proposed_action=proposed_shot["action"], shot_reason=proposed_shot["reason"],
                       seconds=proposed_shot["timeline_seconds"])
    if cast:
        fields["character_ids"] = {"type": "array", "items": {**STRING, "enum": list(cast)}, "maxItems": 2}
        context["cast"] = cast
    with _measured(job, "storyboard", comfy):
        return _ask(profile,
                    "Adapt only this scene from the original script or its ordered excerpt notes. "
                    "Preserve characters, events and their order. Prior continuity is for visual consistency only. "
                    "Use Vietnamese title and description, and an English image_prompt. Return audio notes; "
                    "the preview is silent and the original dialogue is stored separately. "
                    "Use a title up to 100 characters, continuity up to 240, description up to 350, "
                    "image_prompt up to 600 and audio up to 160. "
                    + ("Set duration_weight to 1 for a quick beat, 2 for normal motion or 3 for sustained action. "
                       if weighted else "")
                    + ("Focus on the proposed action, using the source only as context. " if proposed_shot else "")
                    + ("Use character_ids only for supplied cast present in this shot." if cast else ""),
                    context,
                    _object(**fields), comfy)


def _write_script_board(job, bindings, *, outline=None):
    brief = job["brief"]
    script = outline if outline is not None else brief["idea"]
    ranges = _script_ranges(script, brief["scene_count"], brief["seconds"])
    scenes = []
    visual_continuity = []
    title = continuity = ""
    for index, (start, end) in enumerate(ranges):
        data = _script_scene(job, bindings["film.storyboard"], bindings["image.generate"],
                             script[start:end], continuity, index)
        scene_title = _text(data.pop("title"), 100)
        title = title or scene_title
        continuity = _text(data.pop("continuity"), 240)
        visual_continuity.append(continuity)
        scenes.append({**data, "character_ids": []})
    board = _story({"title": title, "continuity": continuity, "scenes": scenes},
                   brief["scene_count"], brief["seconds"], {})
    for scene, (start, end), notes in zip(board["scenes"], ranges, visual_continuity):
        if outline is None:
            scene["script_range"] = [start, end]
        scene["continuity"] = notes
    job.update(board=board, cast={})
    _save(job)


class ShotBudgetMismatch(ValueError):
    def __init__(self, count, seconds, minimum, maximum):
        self.seconds, self.minimum, self.maximum = seconds, minimum, maximum
        super().__init__(f"AI trả {count} cảnh. Video {seconds} giây cần {minimum}–{maximum} cảnh.")


def _duration_plan(job, profile):
    brief = job["brief"]
    moving = brief.get("mode") == "motion"
    script = brief["idea"]
    cap = draft_timeline.MOTION_PRODUCTION_SHOT_BUDGET if moving else 6
    max_seconds = draft_timeline.MAX_DURATION_SECONDS
    max_shot_seconds = draft_timeline.MOTION_OUTPUT.max_frames / draft_timeline.FPS if moving else max_seconds
    if len(SCRIPT_HEADING.findall(script)) > cap:
        raise ValueError(f"Kịch bản vượt {cap} cảnh. Hãy gộp các hành động liên quan hoặc chia video.")
    bounded_text = {**STRING, "minLength": 1, "maxLength": 180}
    shot = _object(action=bounded_text, suggested_seconds={"type": "number"}, reason=bounded_text)
    schema = _object(estimated_duration_seconds={"type": "integer"},
                     shots={"type": "array", "maxItems": cap, "items": shot},
                     duration_reasoning={**STRING, "minLength": 1, "maxLength": 350},
                     production_feasibility={"type": "string", "enum": ["feasible", "over_budget"]})
    _activity(job, "PLANNING", "duration", profile)
    with _measured(job, "duration"):
        source = script
        if len(script) > 1800:
            source = []
            for start in range(0, len(script), 1000):
                if _cancellation(job["id"]):
                    raise DraftCancelled
                excerpt = _ask(profile, "Summarize essential actions, transitions and dialogue in order, "
                               "without adding events. Use at most 120 characters.",
                               {"excerpt": script[start:start+1000]},
                               _object(beats={**STRING, "minLength": 1, "maxLength": 120}), None, cpu_only=True)
                source.append(_text(excerpt["beats"], 120, label="Tóm tắt hành động"))
        limits = {seconds: draft_timeline.duration_limits(seconds, moving)
                  for seconds in range(4 if moving else 6, max_seconds + 1)}
        result = _ask(profile,
                      "Estimate timing from distinct actions and pacing, not word count. Keep important events "
                      "in order and consider opening, development, climax and ending only when present. "
                      "Merge related beats; never pad, repeat, or silently remove content. "
                      "Return the Vietnamese action, timing and reason for each shot. Estimate a whole number "
                      "of seconds. Suggest relative shot timings within the per-shot limits. If essential actions "
                      "cannot fit, report over_budget with a concrete split or reduction in duration_reasoning. "
                      "The allowed_shot_counts table contains [minimum, maximum] for EACH duration. "
                      "Choose a permitted count for the estimate AND the owner's duration if provided. "
                      "A story beat can use multiple camera shots covering distinct moments of the same "
                      "action. Keep each action and reason brief.",
                      {"source": source, "requested_seconds": brief["seconds"], "allowed_shot_counts": limits,
                       "min_shot_seconds": 1 if moving else 2, "max_shot_seconds": max_shot_seconds,
                       "max_seconds": max_seconds}, schema, None, cpu_only=True, extended_plan=moving)
        try:
            return _validate_duration_plan(brief, result, moving, max_shot_seconds)
        except ShotBudgetMismatch as mismatch:
            if _cancellation(job["id"]):
                raise DraftCancelled
            target = brief["seconds"] if brief["duration_mode"] == "manual" else mismatch.seconds
            minimum, maximum = limits[target]
            retry_schema = _object(**{**schema["properties"],
                "estimated_duration_seconds": {"type": "integer", "enum": [target]},
                "shots": {"type": "array", "minItems": minimum, "maxItems": maximum, "items": shot}})
            repaired = _ask(profile,
                            "Replan the source at the exact requested duration and within the given shot count. "
                            "Break longer story beats into sequential camera shots of distinct moments. "
                            "Preserve the characters and events. Never add filler or repeat actions. "
                            "If this cannot be done, report over_budget and explain why in Vietnamese.",
                            {"source": source, "seconds": target, "min_shots": minimum, "max_shots": maximum,
                             "min_shot_seconds": 1 if moving else 2, "max_shot_seconds": max_shot_seconds},
                            retry_schema, None, cpu_only=True, extended_plan=moving)
            try:
                return _validate_duration_plan(brief, repaired, moving, max_shot_seconds, required_estimate=target)
            except ShotBudgetMismatch as exc:
                raise ValueError(f"{exc} AI vẫn chưa lập được timeline sau khi điều chỉnh.") from None


def _validate_duration_plan(brief, result, moving, max_shot_seconds, *, required_estimate=None):
    if not isinstance(result, dict):
        raise ValueError("AI trả kế hoạch thời lượng sai cấu trúc.")
    reasoning = _text(result.get("duration_reasoning"), 350, label="Lý do đề xuất thời lượng")
    if result.get("production_feasibility") == "over_budget":
        raise ValueError("Kịch bản vượt ngân sách sản xuất. " + reasoning)
    if result.get("production_feasibility") != "feasible":
        raise ValueError("AI chưa xác định được tính khả thi. Hãy rút gọn hoặc chia kịch bản.")
    estimate = result.get("estimated_duration_seconds")
    if required_estimate is not None and estimate != required_estimate:
        raise ValueError(f"AI chưa giữ đúng thời lượng {required_estimate} giây khi lập lại storyboard.")
    proposed = result.get("shots")
    if not isinstance(proposed, list) or not proposed:
        raise ValueError("AI chưa trả về danh sách cảnh. Hãy tiếp tục từ checkpoint để lập lại storyboard.")
    count = len(proposed)
    accepted = estimate if brief["duration_mode"] == "auto" else brief["seconds"]
    for seconds in (estimate,) if estimate == accepted else (estimate, accepted):
        minimum, maximum = draft_timeline.duration_limits(seconds, moving)
        if not minimum <= count <= maximum:
            raise ShotBudgetMismatch(count, seconds, minimum, maximum)
    shots = []
    for item in proposed:
        seconds = item.get("suggested_seconds") if isinstance(item, dict) else None
        if (type(seconds) not in {float, int}
                or not (1 if moving else 2) <= seconds <= max_shot_seconds):
            raise ValueError("Thời lượng cảnh AI đề xuất vượt giới hạn. Hãy chia hành động thành cảnh ngắn hơn.")
        shots.append({"action": _text(item.get("action"), 180, label="Hành động của cảnh"),
                      "reason": _text(item.get("reason"), 180, label="Lý do giữ cảnh"),
                      "suggested_seconds": seconds})
    weights = [item["suggested_seconds"] for item in shots]
    draft_timeline.planned_timeline(accepted, moving, weights)
    return {"estimated_duration_seconds": estimate, "recommended_shot_count": count,
            "shots": shots, "duration_reasoning": reasoning, "production_feasibility": "feasible",
            "initial_accepted_seconds": accepted}


def _write_planned_board(job, bindings):
    brief = job["brief"]
    if not job.get("duration_plan"):
        plan = _duration_plan(job, bindings["general.text"])
        job["duration_plan"] = plan
        brief.update(seconds=plan["initial_accepted_seconds"], scene_count=plan["recommended_shot_count"])
        _save(job)
    plan = job["duration_plan"]
    layout = _storyboard_layout(job, brief["scene_count"], [shot["suggested_seconds"] for shot in plan["shots"]])
    script = brief["idea"]
    cast = _select_cast(job, bindings, " ".join(shot["action"] for shot in plan["shots"]))
    ranges = _script_ranges(script, brief["scene_count"], brief["seconds"]) if _needs_scene_analysis(script) else []
    scenes, notes = [], []
    title = continuity = ""
    for index, shot in enumerate(plan["shots"]):
        source = script[slice(*ranges[index])] if ranges else script
        data = _script_scene(job, bindings["film.storyboard"], bindings["image.generate"],
                             source, continuity, index, cast=cast,
                             proposed_shot={**shot, "timeline_seconds": layout[index] / draft_timeline.FPS})
        scene_title = _text(data.pop("title"), 100)
        title = title or scene_title
        continuity = _text(data.pop("continuity"), 240)
        notes.append(continuity)
        data.setdefault("character_ids", [])
        scenes.append(data)
    board = _story({"title": title, "continuity": continuity, "scenes": scenes},
                   brief["scene_count"], brief["seconds"], cast)
    for index, (scene, shot) in enumerate(zip(board["scenes"], plan["shots"])):
        scene.update(continuity=notes[index], suggested_seconds=shot["suggested_seconds"], shot_reason=shot["reason"])
        if ranges:
            scene["script_range"] = list(ranges[index])
    job.update(board=board, cast=cast)
    _save(job)


def _select_cast(job, bindings, outline):
    candidates = {row["id"]: {"name": row["name"], "appearance": row["appearance"][:220]}
                  for row in characters.list_characters()["characters"][:10]}
    if not candidates:
        return {}
    selector = bindings.get("character.select", bindings["film.storyboard"])
    comfy = bindings["image.generate"]
    _activity(job, "STORYBOARD", "cast", selector)
    with _measured(job, "cast", comfy):
        selection = _ask(selector, "Select up to two relevant registered characters. Return empty if none fit.",
                         {"outline": outline, "candidates": candidates},
                         _object(ids={"type": "array", "items": {**STRING, "enum": list(candidates)},
                                      "maxItems": 2}), comfy)
    ids = selection["ids"]
    if not isinstance(ids, list) or len(ids) > 2 or any(not isinstance(x, str) or x not in candidates for x in ids):
        raise ValueError("Invalid character selection")
    return {key: candidates[key] for key in ids}


def _write_board(job, bindings):
    if "duration_mode" in job["brief"]:
        return _write_planned_board(job, bindings)
    if job["brief"]["seconds"] == 30 and job["brief"].get("mode") == "motion":
        brief = job["brief"]
        scripted = _needs_scene_analysis(brief["idea"])
        if not job.get("plan"):
            minimum, maximum = draft_timeline.shot_limits(30)
            minimum = max(minimum, len(SCRIPT_HEADING.findall(brief["idea"])))
            if scripted and maximum > minimum:
                try:
                    _script_ranges(brief["idea"], maximum, 30)
                except ValueError:
                    maximum = minimum
            _activity(job, "PLANNING", "plan", bindings["general.text"])
            fields = _object(outline={**STRING, "minLength": 1, "maxLength": OUTLINE_LIMIT},
                             scene_count={"type": "integer", "minimum": minimum, "maximum": maximum})
            with _measured(job, "plan", bindings["image.generate"]):
                result = _ask(bindings["general.text"],
                    f"Choose {minimum} to {maximum} distinct short shots based on the action. "
                    "Keep the story order and important actions. Write an outline of at most 700 characters "
                    "with at least 16 words; prefer distinct action beats over repeated establishing shots.",
                    {"excerpt": brief["idea"][:2000], "explicit_scenes": len(SCRIPT_HEADING.findall(brief["idea"]))},
                    fields, bindings["image.generate"])
            count = _number(result.get("scene_count"), minimum, maximum)
            job["plan"] = _text(result.get("outline"), OUTLINE_LIMIT, label="Dàn ý do AI trả về")
            brief["scene_count"] = count
            _save(job)
        return _write_script_board(job, bindings, outline=None if scripted else job["plan"])
    if job["brief"].get("input_type") == "script" or _needs_scene_analysis(job["brief"]["idea"]):
        return _write_script_board(job, bindings)
    comfy = bindings["image.generate"]
    if not job.get("plan"):
        _activity(job, "PLANNING", "plan", bindings["general.text"])
        with _measured(job, "plan", comfy):
            output = _ask(bindings["general.text"],
                          "Plan a coherent video and return a Vietnamese outline. Develop a short premise. "
                          "When the input supplies story details, preserve its events, people and dialogue "
                          "and fill only missing details. "
                          f"Keep the outline concise, at most {OUTLINE_LIMIT} characters. "
                          "Use the selected duration and scene count from the brief.",
                          job["brief"], _object(outline={**STRING, "minLength": 1, "maxLength": OUTLINE_LIMIT}),
                          comfy)
        job["plan"] = _text(output.get("outline"), OUTLINE_LIMIT, label="Dàn ý do AI trả về")
        _save(job)
    job["stage"] = "STORYBOARD"
    _save(job)
    cast = _select_cast(job, bindings, job["plan"])
    count = job["brief"]["scene_count"]
    references = {"type": "array", "items": {**STRING, "enum": list(cast)} if cast else STRING,
                  "maxItems": min(2, len(cast))}
    schema = _object(title=STRING, continuity=STRING, scenes={
        "type": "array", "minItems": count, "maxItems": count, "items": _object(
            description=STRING, image_prompt=STRING, character_ids=references,
            audio=STRING)})
    _activity(job, "STORYBOARD", "storyboard", bindings["film.storyboard"])
    with _measured(job, "storyboard", comfy):
        data = _ask(bindings["film.storyboard"],
                "Write a coherent Vietnamese storyboard for a silent video. Describe a concrete "
                "visible movement in each scene description. "
                "Use English visual prompts with stable setting and character appearance. "
                "Use only supplied cast IDs, or an empty character_ids array if cast is empty. "
                "Describe any invented characters only in the prompt. Add optional audio notes.",
                {"brief": job["brief"], "outline": job["plan"], "cast": cast}, schema, comfy)
    job["board"] = _story(data, count, job["brief"]["seconds"], cast)
    job["cast"] = cast
    _save(job)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _scene_path(job, index):
    scene = job["board"]["scenes"][index]
    ident = scene.get("image_key", scene.get("shot_id"))
    name = f"scene-{_id(ident)}.png" if ident else f"scene-{index+1:02d}.png"
    return ensure_local_root(_folder(job["id"]) / name)


def _stamp_storyboard(job):
    board = job["board"]
    weight_key = "suggested_seconds" if "duration_mode" in job["brief"] else "duration_weight"
    layout = _storyboard_layout(job, len(board["scenes"]), [s.get(weight_key, 2) for s in board["scenes"]])
    moving = job["brief"].get("mode") == "motion"
    for scene, frames in zip(board["scenes"], layout):
        scene.setdefault("shot_id", uuid4().hex)
        scene.setdefault("motion_prompt", scene["description"])
        scene.update(frames=frames, seconds=frames / draft_timeline.FPS if moving else frames // draft_timeline.FPS)
    job["storyboard_sha"] = draft_timeline.digest(job)
    job.update(status="STORYBOARD_REVIEW", stage="STORYBOARD", error=None)
    job.pop("approved_storyboard_sha", None)


def _storyboard_layout(job, count, weights=None):
    brief = job["brief"]
    if "duration_mode" in brief:
        return draft_timeline.planned_timeline(brief["seconds"], brief.get("mode") == "motion",
                                               weights if weights is not None else [2]*count)
    if brief.get("mode") == "motion":
        return draft_timeline.timeline(brief["seconds"], count, weights)
    if not 2 <= count <= 6 or count * 2 > brief["seconds"]:
        raise ValueError("Bản nháp ảnh tĩnh cần 2–6 cảnh và ít nhất 2 giây mỗi cảnh.")
    length, extra = divmod(brief["seconds"], count)
    return [(length + (index < extra)) * draft_timeline.FPS for index in range(count)]


def _image(job, index, scene, revision, profile):
    path = _scene_path(job, index)
    if scene["asset"]:
        image(job, index)
        return
    prior = None
    if scene["job_id"]:
        try:
            prior = visual_jobs._row(scene["job_id"])
        except KeyError:
            pass
    if prior and prior["status"] in {"SUBMITTING", "SUBMITTED", "SUBMIT_UNCERTAIN", "COLLECTING"}:
        raise ValueError("The prior ComfyUI scene job needs reconciliation before retry")
    if not prior or prior["status"] != "ASSET_READY":
        if ("storyboard_version" in job or job["brief"].get("mode") == "motion") and scene["job_id"]:
            raise ValueError("Cần kiểm tra tác vụ tạo ảnh cũ trước khi duyệt phiên bản sửa.")
        if scene["attempts"] >= IMG_RETRIES:
            raise ValueError("Scene reached its retry limit")
        previous_job = scene["job_id"]
        scene["job_id"] = uuid4().hex
        scene["attempts"] += 1
        _save(job)
        cast = job["cast"]
        identity = ". ".join(cast[key]["name"] + ": " + cast[key]["appearance"] for key in scene["character_ids"])
        prompt = ". ".join((scene.get("continuity", job["board"]["continuity"]), identity,
                            scene.get("scene_notes", ""), scene["image_prompt"]))
        request = studio_runtime.ImageRequest(prompt, job["brief"]["ratio"],
                                              f"{job['id']}/episode-01/scene-{index+1:02d}",
                                              scene["job_id"], revision)
        try:
            output = studio_runtime.image_adapter(profile).generate(profile, request)
        except (comfy_service.StartupError, draft_resources.ResourceBlocked):
            scene["job_id"] = previous_job
            scene["attempts"] -= 1
            raise
        if output["status"] == "GPU_RESOURCE_FAILURE":
            raise ResourceWait("GPU_RESOURCE_FAILURE")
        if output["status"] != "ASSET_READY":
            raise ValueError("ComfyUI scene result: " + output["status"])
    temporary = ensure_local_root(path.with_name(uuid4().hex + ".tmp"))
    try:
        with visual_jobs.open_image_for_job(scene["job_id"]) as (source, digest), temporary.open("xb") as stream:
            remaining = visual_jobs.MAX_IMAGE
            while chunk := source.read(min(64 * 1024, remaining + 1)):
                remaining -= len(chunk)
                if remaining < 0:
                    raise ValueError("Scene image exceeds import budget")
                stream.write(chunk)
        with temporary.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise ValueError("Scene image changed during import")
        temporary.replace(ensure_local_root(path))
    finally:
        temporary.unlink(missing_ok=True)
    scene["asset"] = digest
    _save(job)


def _render(job):
    folder = _folder(job["id"])
    moving = job["brief"].get("mode") == "motion"
    if moving and job["brief"]["seconds"] >= 30:
        ids = [scene.get("motion_job") for scene in job["board"]["scenes"]]
        if None in ids or len(set(ids)) != len(ids):
            raise ValueError("Phim từ 30 giây cần clip riêng cho từng cảnh.")
    width, height = draft_timeline.MOTION_OUTPUT.resolution if moving else SIZES[job["brief"]["ratio"]]
    ffmpeg = render._ffmpeg()
    command = [ffmpeg, "-nostdin", "-n", "-v", "error"]
    filters, streams = [], []
    input_bytes = 0
    for index, scene in enumerate(job["board"]["scenes"]):
        if moving:
            clip = studio_runtime.motion_artifacts().clip_path(scene)
            input_bytes += clip.stat().st_size
            if input_bytes > MAX_MOTION_INPUTS:
                raise ValueError("Motion clips exceed the production assembly budget")
            command += ["-threads", "1", "-i", str(clip)]
            frames = scene.get("frames", int(scene["seconds"] * draft_timeline.FPS))
            filters.append(f"[{index}:v]trim=end_frame={frames},setpts=PTS-STARTPTS,setsar=1[v{index}]")
            streams.append(f"[v{index}]")
            continue
        command += ["-i", str(_scene_path(job, index))]
        frames = scene["seconds"] * draft_timeline.FPS
        filters.append(f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                       f"crop={width}:{height},setsar=1,zoompan=z='1+0.00025*on':"
                       f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s={width}x{height}:fps={draft_timeline.FPS},"
                       f"fade=t=in:st=0:d=0.2,fade=t=out:st={scene['seconds']-0.2}:d=0.2[v{index}]")
        streams.append(f"[v{index}]")
    filters.append("".join(streams) + f"concat=n={len(streams)}:v=1:a=0[out]")
    target = _video_file(job)
    temporary = ensure_local_root(folder / (uuid4().hex + ".mp4"))
    try:
        render._run_process(command + ["-filter_complex_threads", "1", "-filter_complex", ";".join(filters),
                                       "-map", "[out]", "-an", "-c:v", "libx264", "-threads", "2", "-preset", "fast",
                                       "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)],
                            cwd=folder, timeout=150)
        if not 1024 <= temporary.stat().st_size <= MAX_VIDEO:
            raise ValueError("Unexpected MP4 size")
        if job.get("status") == "RUNNING":
            _activity(job, "VERIFY", "verify")
        verification = render._run_process([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(temporary),
                                            "-map", "0:v:0", "-progress", "pipe:1", "-f", "null", "-"],
                                           cwd=folder, timeout=60)
        frames = re.findall(r"(?m)^frame=(\d+)", verification.stdout)
        if not frames or int(frames[-1]) != job["brief"]["seconds"] * draft_timeline.FPS:
            raise ValueError("MP4 duration verification failed")
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        temporary.replace(ensure_local_root(target))
        if "storyboard_version" in job:
            subtitles = draft_timeline.captions(job["board"]["scenes"])
            receipt = {"production_id": job["id"], "version": job["storyboard_version"],
                       "storyboard_sha": job["approved_storyboard_sha"], "video_sha": digest,
                       "technical": {"frames_decoded": int(frames[-1]), "fps": draft_timeline.FPS, "width": width, "height": height},
                       "visual_qa": "UNVERIFIED", "owner_qa": "PENDING",
                       "subtitle_sha": _sha(subtitles) if subtitles else None,
                       "shots": [{key: scene.get(key) for key in ("shot_id", "frames", "job_id", "asset",
                                  "motion_job", "motion_sha")} for scene in job["board"]["scenes"]]}
            record = ensure_local_root(target.with_suffix(".receipt.json"))
            staged = ensure_local_root(folder / (uuid4().hex + ".json.tmp"))
            try:
                with staged.open("x", encoding="utf-8") as stream:
                    json.dump(receipt, stream, ensure_ascii=False, indent=2)
                staged.replace(record)
            finally:
                staged.unlink(missing_ok=True)
            job["receipt_sha"] = _sha(record.read_bytes())
            job["subtitle_sha"] = receipt["subtitle_sha"]
        return digest
    finally:
        temporary.unlink(missing_ok=True)


def _work(job, slot):
    global ACTIVE
    image_profile = None
    used_image = False
    try:
        if _cancellation(job["id"]):
            raise DraftCancelled
        ops_control.require_active()
        moving = job["brief"].get("mode") == "motion"
        reviewing = "storyboard_version" in job and not job.get("approved_storyboard_sha")
        with model_hub.local_inference_slot():
            revision, bindings = model_hub.draft_routes()
            if reviewing:
                studio_runtime.motion_artifacts().require_resolved_ledger(job)
                if bindings["image.generate"].get("base_url"):
                    profile = bindings["image.generate"]
                    studio_runtime.image_adapter(profile).preflight(profile, include_profiles=True)
                if not job.get("board"):
                    _write_board(job, bindings)
                if _cancellation(job["id"]):
                    raise DraftCancelled
                _stamp_storyboard(job)
                return
            if "storyboard_version" in job and (
                    job["approved_storyboard_sha"] != draft_timeline.digest(job)):
                raise ValueError("Storyboard đã thay đổi. Cần Owner duyệt lại.")
            if (moving or "storyboard_version" in job) and revision != job["motion_revision"]:
                raise ValueError("Model routing changed after approval; review and create a new draft")
            motion = studio_runtime.motion_adapter(bindings.get("film.motion")) if moving else None
            motion_profile = motion.bind(bindings["film.motion"]) if moving else None
            if moving:
                motion.require_resolved_ledger(job)
            image_profile = bindings["image.generate"]
            board = job.get("board")
            needs_gpu = not board or any(not scene["asset"] for scene in board["scenes"])
            if needs_gpu and image_profile.get("base_url"):
                studio_runtime.image_adapter(image_profile).preflight(image_profile)
            folder = _folder(job["id"])
            folder.mkdir(parents=True, exist_ok=True)
            if not job.get("board"):
                _write_board(job, bindings)
            for index, scene in enumerate(job["board"]["scenes"]):
                ops_control.require_active()
                if scene["asset"]:
                    _image(job, index, scene, revision, bindings["image.generate"])
                else:
                    _activity(job, "IMAGES", "image", image_profile, scene=index + 1)
                    with _measured(job, "image", image_profile):
                        used_image = True
                        _image(job, index, scene, revision, bindings["image.generate"])
            if moving and used_image:
                _release_idle_image(image_profile)
        if moving:
            prepared = motion.prepare(job, folder)
            for index, scene in enumerate(job["board"]["scenes"]):
                if _cancellation(job["id"]):
                    raise DraftCancelled
                if model_hub.draft_routes()[0] != job["motion_revision"]:
                    raise ValueError("Model routing changed after approval; review and create a new draft")
                _activity(job, "MOTION", "motion", motion_profile, scene=index + 1)
                try:
                    motion.run_shot(scene, index, prepared, motion_profile,
                                          lambda: _save(job), lambda: _cancellation(job["id"]))
                except studio_runtime.NeedsReconciliation:
                    raise
                except Exception:
                    if _cancellation(job["id"]):
                        raise DraftCancelled from None
                    raise
                if _cancellation(job["id"]):
                    raise DraftCancelled
        with model_hub.local_inference_slot():
            ops_control.require_active()
            _activity(job, "RENDER", "render")
            with _measured(job, "render"):
                job["video_sha"] = _render(job)
            job["status"] = "REVIEW"
    except (ResourceWait, comfy_service.StartupPressure, draft_resources.ResourceBlocked) as exc:
        job.update(status="WAITING_RESOURCES", error=str(exc))
    except DraftCancelled:
        job.update(status="CANCELLED", error=None, video_sha=None)
    except studio_runtime.NeedsReconciliation as exc:
        job.update(status="NEEDS_RECONCILIATION", error=str(exc))
    except (ValueError, PermissionError) as exc:
        if str(exc) == "LOCAL_INFERENCE_BUSY":
            job.update(status="WAITING_RESOURCES", error="GPU_BUSY")
        else:
            job.update(status="FAILED", error=str(exc)[:240])
    except Exception:
        job.update(status="FAILED", error="Local runtime failed at " + job["stage"] + "; check Ollama, ComfyUI or FFmpeg before resuming.")
    finally:
        try:
            if used_image and job.get("status") != "WAITING_RESOURCES" and image_profile.get("base_url"):
                try:
                    with model_hub.local_inference_slot():
                        _release_idle_image(image_profile)
                except OSError:
                    pass
            activity = job.pop("activity", {})
            if job["status"] == "FAILED" and activity.get("scene"):
                job["failed_scene"] = activity["scene"]
            with comfy_service.LOCK:
                if job["status"] != "NEEDS_RECONCILIATION" and _cancellation(job["id"]):
                    job.update(status="CANCELLED", error=None, video_sha=None)
                if job.get("attempt_started_at"):
                    job["attempt_finished_at"] = visual_jobs._now()
                _save(job)
        finally:
            ACTIVE = None
            slot.__exit__(None, None, None)
        if job["status"] != "WAITING_RESOURCES":
            _dispatch()


def _start(job, slot):
    global ACTIVE
    with comfy_service.LOCK:
        if _cancellation(job["id"]):
            raise DraftCancelled
        comfy_service.reset_idle()
        job.update(status="RUNNING", error=None)
        job["attempt_started_at"] = visual_jobs._now()
        job.setdefault("started_at", job["attempt_started_at"])
        job.pop("attempt_finished_at", None)
        job.pop("failed_scene", None)
        job.pop("activity", None)
        _save(job)
        snapshot = copy.deepcopy(job)
        ACTIVE = job["id"]
        try:
            threading.Thread(target=_work, args=(job, slot), daemon=True).start()
        except BaseException:
            ACTIVE = None
            raise
    return snapshot


def _dispatch():
    try:
        slot = _worker_slot()
        slot.__enter__()
    except PermissionError:
        return
    started = False
    try:
        with _db() as conn:
            if conn is None:
                return
            if conn.execute("SELECT 1 FROM drafts WHERE json_extract(body,'$.status') IN "
                            "('RUNNING','WAITING_RESOURCES') LIMIT 1").fetchone():
                return
            row = conn.execute("SELECT body FROM drafts WHERE json_extract(body,'$.status')='QUEUED' "
                               "ORDER BY rowid LIMIT 1").fetchone()
        if row:
            result = _start(_decode_row(row), slot)
            started = True
            return result
    finally:
        if not started:
            slot.__exit__(None, None, None)


def submit(data):
    ident = _id(data["id"])
    motion_mode = data.get("mode") == "motion"
    duration_mode = data.get("duration_mode")
    if duration_mode is None:
        seconds = _number(data["seconds"], 4 if motion_mode else 6, 60)
        count = _number(data["scene_count"], 2, draft_timeline.shot_limits(seconds)[1] if motion_mode else 6)
        if not motion_mode and seconds < count * 2:
            raise ValueError("Choose at least two seconds per scene")
    else:
        seconds, count = data["seconds"], data["scene_count"]
        if duration_mode not in ("auto", "manual") or count is not None or (duration_mode == "auto" and seconds is not None):
            raise ValueError("Thiết lập thời lượng không hợp lệ.")
        if duration_mode == "manual":
            draft_timeline.duration_limits(seconds, motion_mode)
    if not isinstance(data["ratio"], str) or data["ratio"] not in SIZES:
        raise ValueError("Choose a supported ratio and at least two seconds per scene")
    idea = data["idea"]
    if not isinstance(idea, str) or not idea.strip() or len(idea) > BRIEF_LIMIT:
        raise ValueError(f"Nội dung video phải có từ 1 đến {BRIEF_LIMIT:,} ký tự.")
    try:
        idea.encode("utf-8")
    except UnicodeError:
        raise ValueError("Nội dung có ký tự Unicode không hợp lệ.") from None
    if duration_mode is None and _needs_scene_analysis(idea):
        if motion_mode and seconds == 30:
            minimum, maximum = draft_timeline.shot_limits(seconds)
            count_for_script = min(maximum, max(minimum, len(SCRIPT_HEADING.findall(idea))))
        else:
            count_for_script = count
        _script_ranges(idea, count_for_script, seconds)
    brief = {"idea": idea, "seconds": seconds,
             "scene_count": count, "ratio": data["ratio"]}
    mode = data.get("mode", "still")
    if mode not in ("still", "motion"):
        raise ValueError("Invalid video mode")
    if mode == "motion":
        if duration_mode is None:
            draft_timeline.timeline(seconds, count)
        if brief["ratio"] != "16:9":
            raise ValueError("Phim chuyển động hiện hỗ trợ khung hình 16:9.")
        brief["mode"] = mode
    if duration_mode is not None:
        brief["duration_mode"] = duration_mode
    try:
        prior = _read(ident)
    except KeyError:
        prior = None
    if prior:
        if prior.get("submitted_brief", prior["brief"]) != brief:
            raise ValueError("Production ID already belongs to another brief")
        return prior
    ops_control.require_active()
    model_hub.draft_routes()
    created_at = visual_jobs._now()
    job = {"id": ident, "brief": brief, "stage": "QUEUED", "status": "QUEUED",
           "video_sha": None, "created_at": created_at, "updated_at": created_at}
    job["storyboard_version"] = 1
    job["submitted_brief"] = dict(brief)
    with comfy_service.LOCK, _db(True) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT body FROM drafts WHERE id=?", (ident,)).fetchone()
        if row:
            prior = _decode_row(row)
            if prior.get("submitted_brief", prior["brief"]) != brief:
                raise ValueError("Production ID already belongs to another brief")
            return prior
        statuses = [row[0] for row in conn.execute("SELECT json_extract(body,'$.status') FROM drafts "
                    "WHERE json_extract(body,'$.status') IN ('QUEUED','RUNNING','WAITING_RESOURCES')")]
        if "WAITING_RESOURCES" in statuses or len(statuses) >= _queue_limit():
            raise ValueError("Draft queue is full or paused for resources")
        conn.execute("INSERT INTO drafts VALUES (?,?)", (ident, json.dumps(job, ensure_ascii=False)))
        comfy_service.reset_idle()
    started = _dispatch()
    return started if started and started["id"] == ident else _read(ident)


def _storyboard_action(job, action, data):
    if ("storyboard_version" not in job or not job.get("board")
            or data["sha256"] != draft_timeline.digest(job)
            or data["sha256"] != job.get("storyboard_sha")):
        raise ValueError("Storyboard đã thay đổi. Tải lại trước khi tiếp tục.")
    if action == "storyboard-approve":
        if job["status"] != "STORYBOARD_REVIEW":
            raise ValueError("Storyboard không chờ duyệt.")
        ops_control.require_active()
        revision, bindings = model_hub.draft_routes()
        if job["brief"].get("mode") == "motion":
            studio_runtime.motion_adapter(bindings.get("film.motion")).bind(bindings["film.motion"])
        else:
            render._ffmpeg()
        job.update(approved_storyboard_sha=job["storyboard_sha"], motion_revision=revision, status="QUEUED")
        with comfy_service.LOCK, _db(True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            statuses = [row[0] for row in conn.execute(
                "SELECT json_extract(body,'$.status') FROM drafts "
                "WHERE json_extract(body,'$.status') IN ('QUEUED','RUNNING','WAITING_RESOURCES')")]
            if "WAITING_RESOURCES" in statuses or len(statuses) >= _queue_limit():
                raise ValueError("Hàng đợi production đầy hoặc đang chờ tài nguyên.")
            conn.execute("UPDATE drafts SET body=? WHERE id=?", (json.dumps(job, ensure_ascii=False), job["id"]))
            comfy_service.reset_idle()
        return job
    if job["status"] not in {"STORYBOARD_REVIEW", "REVIEW", "FAILED"}:
        raise ValueError("Storyboard chưa thể chỉnh ở trạng thái này.")
    studio_runtime.motion_artifacts().require_resolved_ledger({})  # A possible dispatch must be reconciled before edit.
    if job["storyboard_version"] >= draft_timeline.MAX_VERSIONS:
        raise ValueError("Đã đạt giới hạn phiên bản. Tạo phim mới để tiếp tục.")
    original = draft_timeline.snapshot(job)
    scenes = job["board"]["scenes"]
    checkpoints = [{key: scene.get(key) for key in (
        "shot_id", "image_key", "job_id", "asset", "motion_job", "motion_sha")} for scene in scenes]
    if action != "storyboard-duration":
        index = _number(data["index"], 0, len(scenes) if action == "storyboard-add" else len(scenes)-1)
    if action == "storyboard-duration":
        if "duration_mode" not in job["brief"]:
            raise ValueError("Video này sử dụng preset thời lượng đã lưu.")
        seconds = data["seconds"]
        draft_timeline.planned_timeline(seconds, job["brief"].get("mode") == "motion",
                                        [scene.get("suggested_seconds", 2) for scene in scenes])
        if seconds == job["brief"]["seconds"]:
            return job
        job["brief"]["seconds"] = seconds
    elif action == "storyboard-remove":
        _storyboard_layout(job, len(scenes)-1)
        scenes.pop(index)
    elif action == "storyboard-move":
        target = _number(data["target"], 0, len(scenes)-1)
        scenes.insert(target, scenes.pop(index))
    else:
        if action == "storyboard-add":
            _storyboard_layout(job, len(scenes)+1)
            scene = {"character_ids": [], "audio": "", "attempts": 0, "asset": None, "job_id": None}
            scenes.insert(index, scene)
        else:
            scene = scenes[index]
        if action == "storyboard-rewrite":
            _, bindings = model_hub.draft_routes()
            with model_hub.local_inference_slot(), _measured(job, "storyboard", bindings["image.generate"]):
                data = _ask(bindings["film.storyboard"], "Rewrite only this shot. Preserve the cast. "
                            "Return description, English image_prompt and motion_prompt.",
                            {"scene": {key: scene[key] for key in draft_timeline.STORY_FIELDS if key in scene},
                             "feedback": _text(data["feedback"], 350), "continuity": original["continuity"]},
                            _object(description=STRING, image_prompt=STRING, motion_prompt=STRING),
                            bindings["image.generate"])
        prompts = {key: _text(data[key], limit) for key, limit in
                   (("description", 350), ("image_prompt", 600), ("motion_prompt", 600))}
        for key, limit in (("caption", 220), ("scene_notes", 240)):
            if key in data:
                prompts[key] = _text(data[key], limit).replace("\n", " ") if data[key] != "" else ""
        notes = prompts.get("scene_notes", scene.get("scene_notes", ""))
        changed_notes = notes != scene.get("scene_notes", "")
        image_changed = changed_notes or prompts["image_prompt"] != scene.get("image_prompt")
        motion_changed = image_changed or prompts["motion_prompt"] != scene.get("motion_prompt")
        scene.update(prompts)
        if image_changed:
            scene.update(image_key=uuid4().hex, asset=None, job_id=None, attempts=0)
        if motion_changed:
            scene.pop("motion_job", None)
            scene.pop("motion_sha", None)
    job.setdefault("storyboard_history", []).append(
        {"sha256": job["storyboard_sha"], "storyboard": original, "video_sha": job["video_sha"],
         "receipt_sha": job.get("receipt_sha"), "checkpoints": checkpoints, "status": job["status"]})
    job["storyboard_version"] += 1
    job["brief"]["scene_count"] = len(scenes)
    job["video_sha"] = None
    job.pop("receipt_sha", None)
    job.pop("subtitle_sha", None)
    _stamp_storyboard(job)
    _save(job)
    return job


def _delete_draft(ident):
    # Share the worker slot with start, resume and storyboard edits.
    with _worker_slot(), comfy_service.LOCK:
        job = _read(ident)
        has_video = job.get("video_sha") or any(entry.get("video_sha") for entry in job.get("storyboard_history", []))
        if job["status"] not in {"CANCELLED", "FAILED", "STORYBOARD_REVIEW"} or has_video:
            raise ValueError("Chỉ có thể xóa bản nháp chưa hoàn thành và đã dừng.")
        studio_runtime.motion_artifacts().require_draft_removable(ident)
        root = ensure_local_root(WORKSPACE_DIR / "drafts")
        folder = ensure_local_root(root / ident).resolve()
        if folder.parent != root.resolve():
            raise PermissionError("Draft storage path refused")
        with _db(True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if folder.exists():
                shutil.rmtree(folder)
            conn.execute("DELETE FROM drafts WHERE id=?", (ident,))
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='draft_cancellations'").fetchone():
                conn.execute("DELETE FROM draft_cancellations WHERE id=?", (ident,))
    return {"id": ident, "deleted": True}


def act(ident, action, data):
    if action == "delete":
        return _delete_draft(ident)
    if action == "cancel":
        with comfy_service.LOCK:
            job = _read(ident)
            if job["status"] not in _QUEUE_STATES:
                raise ValueError("Draft cannot be cancelled")
            if job["status"] == "RUNNING" and not ACTIVE and job.get("stage") == "MOTION":
                raise ValueError("Cần đối soát tác vụ chuyển động trước khi hủy.")
            _cancellation(ident, mark=True)
            if job["status"] != "RUNNING" or not ACTIVE:
                job.update(status="CANCELLED", error=None)
                _save(job)
        _dispatch()
        return job
    if action == "resume" and _read(ident)["status"] == "QUEUED":
        started = _dispatch()
        return started if started and started["id"] == ident else _read(ident)
    slot = _worker_slot()
    slot.__enter__()
    started = False
    try:
        job = _read(ident)
        if action.startswith("storyboard-"):
            return _storyboard_action(job, action, data)
        if action in {"approve", "reject"}:
            if job["status"] != "REVIEW" or data.get("sha256") != job["video_sha"]:
                raise ValueError("Review the current draft version")
            with video_path(job).open("rb") as stream:
                verify_video(job, stream)
            job["status"] = "APPROVED" if action == "approve" else "REJECTED"
            _save(job)
            return job
        if action == "edit":
            if job["brief"].get("mode") == "motion" or "storyboard_version" in job:
                raise ValueError("Chỉnh sửa từ storyboard để lưu phiên bản và duyệt lại.")
            if job["status"] in {"APPROVED", "REJECTED", "CANCELLED"} or not job.get("board"):
                raise ValueError("Scene cannot be edited")
            scene = job["board"]["scenes"][_number(data["index"], 0, len(job["board"]["scenes"]) - 1)]
            scene.update(description=_text(data["description"], 350), image_prompt=_text(data["image_prompt"], 600),
                         asset=None, job_id=None, attempts=0)
            job.update(status="FAILED", video_sha=None, error="Scene changed. Resume to regenerate this scene.")
            _save(job)
            return job
        if action != "resume" or job["status"] not in {"RUNNING", "FAILED", "WAITING_RESOURCES", "NEEDS_RECONCILIATION"}:
            raise ValueError("Draft cannot be resumed")
        if job["status"] == "NEEDS_RECONCILIATION" and _cancellation(ident):
            if studio_runtime.motion_artifacts().reconcile_cancelled(job):
                job.update(status="CANCELLED", error=None, video_sha=None)
                _save(job)
            return job
        with _db() as conn:
            if conn.execute("SELECT 1 FROM drafts WHERE id<>? AND json_extract(body,'$.status')="
                            "'WAITING_RESOURCES' LIMIT 1", (ident,)).fetchone():
                raise ValueError("Resume the draft that is waiting for resources first")
        ops_control.require_active()
        model_hub.draft_routes()
        job = _start(job, slot)
        started = True
        return job
    finally:
        if not started:
            slot.__exit__(None, None, None)


def image(job, index):
    scenes = job.get("board", {}).get("scenes", [])
    scene = scenes[_number(index, 0, len(scenes) - 1)]
    path = _scene_path(job, index)
    if not scene["asset"] or not path.is_file() or path.stat().st_size > visual_jobs.MAX_IMAGE:
        raise ValueError("Scene image unavailable")
    data = path.read_bytes()
    if _sha(data) != scene["asset"]:
        raise ValueError("Scene image hash mismatch")
    return data


def _video_file(job):
    version = job.get("storyboard_version")
    name = f"draft-v{_number(version, 1, draft_timeline.MAX_VERSIONS):02d}.mp4" if version else "draft.mp4"
    return ensure_local_root(_folder(job["id"]) / name)


def video_path(job):
    if not job.get("video_sha"):
        raise ValueError("Draft video unavailable")
    return _video_file(job)


def verify_video(job, stream):
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        if size > MAX_VIDEO:
            raise ValueError("Draft video exceeds size limit")
        digest.update(chunk)
    if not 1024 <= size or digest.hexdigest() != job["video_sha"]:
        raise ValueError("Draft video hash mismatch")
    if "storyboard_version" in job:
        verified_receipt(job)


def verified_receipt(job):
    record = ensure_local_root(video_path(job).with_suffix(".receipt.json"))
    if not record.is_file() or record.stat().st_size > 16_384:
        raise ValueError("Draft receipt unavailable")
    data = record.read_bytes()
    if _sha(data) != job.get("receipt_sha"):
        raise ValueError("Draft receipt hash mismatch")
    return data
