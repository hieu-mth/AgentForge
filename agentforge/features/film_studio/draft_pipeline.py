"""Checkpointed local idea-to-draft production."""
import copy
import hashlib
import os
import json
import re
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from uuid import uuid4
from urllib.parse import urlsplit

from agentforge import ops_control
from agentforge.ai import model_hub
from agentforge.features.film_studio import characters
from agentforge.features.film_studio import draft_resources
from agentforge.features.media import flux_runtime, flux_workflow, render, visual_jobs
from agentforge.integrations import comfy_service
from agentforge.ops import runtime_certification as runtime
from agentforge.paths import COMPANY_DATA_DIR, WORKSPACE_DIR, ensure_local_root

DB = COMPANY_DATA_DIR / "video_drafts.sqlite3"
MAX_VIDEO = 80 * 1024 * 1024
SIZES = {"9:16": (720, 1280), "16:9": (1280, 720)}
LOCK = threading.Lock()
ACTIVE = None
IMG_RETRIES = 3
_QUEUE_STATES = {"QUEUED", "RUNNING", "WAITING_RESOURCES"}


class ResourceWait(Exception):
    pass


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
        reason = draft_resources.pressure(before, operation)
        if reason == "VRAM_LOW" and comfy_profile and comfy_profile.get("base_url"):
            if _release_idle_comfy(comfy_profile):
                point["after_release"] = draft_resources.snapshot()
                reason = draft_resources.pressure(point["after_release"], operation)
        if reason:
            raise ResourceWait(reason)
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


def _text(value, max_length):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= max_length:
        raise ValueError("Invalid draft text")
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
        jobs = [_decode_row(row) for row in conn.execute("SELECT body FROM drafts ORDER BY rowid DESC LIMIT 30")]
    return [{**job, "worker_active": job["id"] == ACTIVE} for job in jobs]


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
        parent = ensure_local_root(DB.parent)
        parent.mkdir(parents=True, exist_ok=True)
        path = ensure_local_root(parent / "video_drafts.worker")
        with path.open("a+b") as stream:
            if not stream.tell():
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                import msvcrt
            except ImportError:
                import fcntl
                lock = lambda: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                lock = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                lock()
            except OSError:
                raise PermissionError("A draft production is already running") from None
            yield
    finally:
        LOCK.release()


def _release_idle_comfy(profile):
    if not draft_resources.can_release_models(draft_resources.snapshot()):
        return False
    port = urlsplit(profile["base_url"]).port
    try:
        queue = flux_runtime._json("/queue", port=port)
        if queue.get("queue_running") != [] or queue.get("queue_pending") != []:
            return False
        def reserved():
            stats = flux_runtime._json("/system_stats", port=port)
            return sum(device.get("torch_vram_total", 0) for device in stats.get("devices", [])
                       if device.get("type") == "cuda")
        initial = reserved()
        from agentforge.integrations import comfyui
        comfyui.request_image_bytes("/free", body={"unload_models": True, "free_memory": True}, port=port)
        for _ in range(8):
            time.sleep(1)
            remaining = reserved()
            if remaining == 0 or remaining < initial:
                return True
    except (OSError, ValueError, RuntimeError):
        return False
    return False


def _ask(profile, instructions, data, schema, comfy_profile):
    host, port = runtime._local_endpoint(profile["base_url"])
    if not runtime._installed_local_model(host, port, profile["model"]):
        raise ValueError("Configured Ollama model is unavailable: " + profile["id"])
    payload = {"model": profile["model"], "stream": False, "think": False,
               "keep_alive": 0, "format": schema,
               "options": {"temperature": 0.2, "num_predict": 1600, "num_ctx": 4096},
               "messages": [{"role": "system", "content": instructions},
                            {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]}
    try:
        message = runtime._http_json(host, port, "/api/chat", timeout=150, max_request_bytes=16384, payload=payload)
    except runtime.LocalProviderHTTPError as exc:
        if exc.status != 500:
            raise ValueError(f"Ollama rejected the request (HTTP {exc.status}): {profile['id']}") from None
        # A prior FLUX call can leave weights resident even when its queue is idle.
        if not _release_idle_comfy(comfy_profile):
            payload["options"]["num_gpu"] = 0
        try:
            message = runtime._http_json(host, port, "/api/chat", timeout=150, max_request_bytes=16384, payload=payload)
        except runtime.LocalProviderHTTPError as retry:
            raise ValueError(f"Ollama failed after one resource retry (HTTP {retry.status}): {profile['id']}") from None
    if message.get("done") is not True or message.get("done_reason") == "length":
        raise ValueError("Ollama did not complete the structured response")
    return json.loads(message["message"]["content"])


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
        if not isinstance(scene, dict) or scene.keys() != {"description", "image_prompt", "character_ids", "audio"}:
            raise ValueError("Invalid storyboard scene")
        ids = scene["character_ids"]
        if not isinstance(ids, list) or len(ids) > 2 or any(not isinstance(x, str) or x not in cast for x in ids):
            raise ValueError("Storyboard contains unknown character references")
        result.append({"description": _text(scene["description"], 350),
                       "image_prompt": _text(scene["image_prompt"], 600),
                       "character_ids": list(dict.fromkeys(ids)), "audio": _text(scene["audio"], 160),
                       "seconds": duration // count + (index < duration % count),
                       "asset": None, "job_id": None, "attempts": 0})
    return {"title": _text(value["title"], 100), "continuity": _text(value["continuity"], 240),
            "scenes": result}


def _activity(job, stage, operation, profile=None, **details):
    job["stage"] = stage
    job["activity"] = {"operation": operation, **details}
    if profile:
        job["activity"].update(provider=profile["provider"], model=profile["model"])
    _save(job)


def _write_board(job, bindings):
    comfy = bindings["image.generate"]
    if not job.get("plan"):
        _activity(job, "PLANNING", "plan", bindings["general.text"])
        with _measured(job, "plan", comfy):
            output = _ask(bindings["general.text"], "Plan a short coherent video. Return Vietnamese outline.",
                          job["brief"], _object(outline=STRING), comfy)
        job["plan"] = _text(output["outline"], 700)
        _save(job)
    job["stage"] = "STORYBOARD"
    _save(job)
    candidates = {row["id"]: {"name": row["name"], "appearance": row["appearance"][:220]}
                  for row in characters.list_characters()["characters"][:10]}
    cast = {}
    if candidates:
        selector = bindings.get("character.select", bindings["film.storyboard"])
        if selector["provider"] != "ollama":
            raise ValueError("Assign a local Ollama model to character.select")
        _activity(job, "STORYBOARD", "cast", selector)
        with _measured(job, "cast", comfy):
            selection = _ask(selector, "Select up to two relevant registered characters. Return empty if none fit.",
                             {"outline": job["plan"], "candidates": candidates},
                             _object(ids={"type": "array", "items": {**STRING, "enum": list(candidates)},
                                          "maxItems": 2}), comfy)
        ids = selection["ids"]
        if not isinstance(ids, list) or len(ids) > 2 or any(not isinstance(x, str) or x not in candidates for x in ids):
            raise ValueError("Invalid character selection")
        cast = {key: candidates[key] for key in ids}
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
                "Write a coherent Vietnamese storyboard for a silent motion slideshow. "
                "Use English visual prompts with stable setting and character appearance. "
                "Use only supplied cast IDs, or an empty character_ids array if cast is empty. "
                "Describe any invented characters only in the prompt. Add optional audio notes.",
                {"brief": job["brief"], "outline": job["plan"], "cast": cast}, schema, comfy)
    job["board"] = _story(data, count, job["brief"]["seconds"], cast)
    job["cast"] = cast
    _save(job)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _image(job, index, scene, revision, profile):
    path = ensure_local_root(_folder(job["id"]) / f"scene-{index+1:02d}.png")
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
        if scene["attempts"] >= IMG_RETRIES:
            raise ValueError("Scene reached its retry limit")
        previous_job = scene["job_id"]
        scene["job_id"] = uuid4().hex
        scene["attempts"] += 1
        _save(job)
        cast = job["cast"]
        identity = ". ".join(cast[key]["name"] + ": " + cast[key]["appearance"] for key in scene["character_ids"])
        prompt = ". ".join((job["board"]["continuity"], identity, scene["image_prompt"]))
        cfg = profile["flux"]
        long = min(768, cfg["max_resolution"] // 16 * 16)
        short = max(256, (long * 9 // 16) // 16 * 16)
        width, height = (short, long) if job["brief"]["ratio"] == "9:16" else (long, short)
        try:
            output = flux_runtime.generate(prompt, width=width, height=height, automated=True,
                                           scene=f"{job['id']}/episode-01/scene-{index+1:02d}",
                                           production_job=scene["job_id"], production_revision=revision)
        except comfy_service.StartupError:
            scene["job_id"] = previous_job
            scene["attempts"] -= 1
            raise
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
    width, height = SIZES[job["brief"]["ratio"]]
    ffmpeg = render._ffmpeg()
    command = [ffmpeg, "-nostdin", "-n", "-v", "error"]
    filters, streams = [], []
    for index, scene in enumerate(job["board"]["scenes"]):
        command += ["-i", str(ensure_local_root(folder / f"scene-{index+1:02d}.png"))]
        frames = scene["seconds"] * 24
        filters.append(f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                       f"crop={width}:{height},setsar=1,zoompan=z='1+0.00025*on':"
                       f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s={width}x{height}:fps=24,"
                       f"fade=t=in:st=0:d=0.2,fade=t=out:st={scene['seconds']-0.2}:d=0.2[v{index}]")
        streams.append(f"[v{index}]")
    filters.append("".join(streams) + f"concat=n={len(streams)}:v=1:a=0[out]")
    target = ensure_local_root(folder / "draft.mp4")
    temporary = ensure_local_root(folder / (uuid4().hex + ".mp4"))
    try:
        render._run_process(command + ["-filter_complex_threads", "1", "-filter_complex", ";".join(filters),
                                       "-map", "[out]", "-an", "-c:v", "libx264", "-threads", "2", "-preset", "fast",
                                       "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)],
                            cwd=folder, timeout=150)
        if not 1024 <= temporary.stat().st_size <= MAX_VIDEO:
            raise ValueError("Unexpected MP4 size")
        verification = render._run_process([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(temporary),
                                            "-map", "0:v:0", "-progress", "pipe:1", "-f", "null", "-"],
                                           cwd=folder, timeout=60)
        frames = re.findall(r"(?m)^frame=(\d+)", verification.stdout)
        if not frames or int(frames[-1]) != job["brief"]["seconds"] * 24:
            raise ValueError("MP4 duration verification failed")
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        temporary.replace(ensure_local_root(target))
        return digest
    finally:
        temporary.unlink(missing_ok=True)


def _work(job, slot):
    global ACTIVE
    image_profile = None
    used_flux = False
    try:
        if _cancellation(job["id"]):
            raise DraftCancelled
        ops_control.require_active()
        with model_hub.local_inference_slot():
            revision, bindings = model_hub.draft_routes()
            image_profile = bindings["image.generate"]
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
                        used_flux = True
                        _image(job, index, scene, revision, bindings["image.generate"])
            ops_control.require_active()
            _activity(job, "RENDER", "render")
            with _measured(job, "render"):
                job["video_sha"] = _render(job)
            job["status"] = "REVIEW"
    except (ResourceWait, comfy_service.StartupPressure) as exc:
        job.update(status="WAITING_RESOURCES", error=str(exc))
    except DraftCancelled:
        job.update(status="CANCELLED", error=None, video_sha=None)
    except (ValueError, PermissionError) as exc:
        if str(exc) == "LOCAL_INFERENCE_BUSY":
            job.update(status="WAITING_RESOURCES", error="GPU_BUSY")
        else:
            job.update(status="FAILED", error=str(exc)[:240])
    except Exception:
        job.update(status="FAILED", error="Local runtime failed at " + job["stage"] + "; check Ollama, ComfyUI or FFmpeg before resuming.")
    finally:
        try:
            if used_flux and image_profile.get("base_url"):
                _release_idle_comfy(image_profile)
            job.pop("activity", None)
            _save(job)
        finally:
            ACTIVE = None
            slot.__exit__(None, None, None)
    if job["status"] != "WAITING_RESOURCES":
        _dispatch()


def _start(job, slot):
    global ACTIVE
    with comfy_service.LOCK:
        comfy_service.reset_idle()
        job.update(status="RUNNING", error=None)
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
    seconds = _number(data["seconds"], 6, 60)
    count = _number(data["scene_count"], 2, 6)
    if seconds < count * 2 or not isinstance(data["ratio"], str) or data["ratio"] not in SIZES:
        raise ValueError("Choose a supported ratio and at least two seconds per scene")
    brief = {"idea": _text(data["idea"], 500), "seconds": seconds,
             "scene_count": count, "ratio": data["ratio"]}
    try:
        prior = _read(ident)
    except KeyError:
        prior = None
    if prior:
        if prior["brief"] != brief:
            raise ValueError("Production ID already belongs to another brief")
        return prior
    ops_control.require_active()
    model_hub.draft_routes()
    render._ffmpeg()
    job = {"id": ident, "brief": brief, "stage": "QUEUED", "status": "QUEUED",
           "video_sha": None, "updated_at": visual_jobs._now()}
    with comfy_service.LOCK, _db(True) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT body FROM drafts WHERE id=?", (ident,)).fetchone()
        if row:
            prior = _decode_row(row)
            if prior["brief"] != brief:
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


def act(ident, action, data):
    if action == "cancel":
        job = _read(ident)
        if job["status"] not in _QUEUE_STATES:
            raise ValueError("Draft cannot be cancelled")
        _cancellation(ident, mark=True)
        if job["status"] == "RUNNING":
            try:
                slot = _worker_slot()
                slot.__enter__()
            except PermissionError:
                return job
            try:
                job = _read(ident)
                if job["status"] != "RUNNING":
                    return job
                job.update(status="CANCELLED", error=None)
                _save(job)
            finally:
                slot.__exit__(None, None, None)
            _dispatch()
            return job
        # A queued or waiting draft has no provider work to interrupt.
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
        if action in {"approve", "reject"}:
            if job["status"] != "REVIEW" or data.get("sha256") != job["video_sha"]:
                raise ValueError("Review the current draft version")
            with video_path(job).open("rb") as stream:
                verify_video(job, stream)
            job["status"] = "APPROVED" if action == "approve" else "REJECTED"
            _save(job)
            return job
        if action == "edit":
            if job["status"] == "APPROVED" or not job.get("board"):
                raise ValueError("Scene cannot be edited")
            scene = job["board"]["scenes"][_number(data["index"], 0, len(job["board"]["scenes"]) - 1)]
            scene.update(description=_text(data["description"], 350), image_prompt=_text(data["image_prompt"], 600),
                         asset=None, job_id=None, attempts=0)
            job.update(status="FAILED", video_sha=None, error="Scene changed. Resume to regenerate this scene.")
            _save(job)
            return job
        if action != "resume" or job["status"] not in {"RUNNING", "FAILED", "WAITING_RESOURCES"}:
            raise ValueError("Draft cannot be resumed")
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
    path = ensure_local_root(_folder(job["id"]) / f"scene-{index+1:02d}.png")
    if not scene["asset"] or not path.is_file() or path.stat().st_size > visual_jobs.MAX_IMAGE:
        raise ValueError("Scene image unavailable")
    data = path.read_bytes()
    if _sha(data) != scene["asset"]:
        raise ValueError("Scene image hash mismatch")
    return data


def video_path(job):
    if not job.get("video_sha"):
        raise ValueError("Draft video unavailable")
    return ensure_local_root(_folder(job["id"]) / "draft.mp4")


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
