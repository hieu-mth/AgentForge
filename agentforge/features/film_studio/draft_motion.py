"""Bounded Studio production using the existing LTX pilot and motion ledger."""
import hashlib
import http.client
import json
import re
import tempfile
import time
from contextlib import closing, nullcontext
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_continuity, draft_resources, long_form, motion_comfy, motion_ltx, motion_verify
from agentforge.features.film_studio.draft_resources import NeedsReconciliation
from agentforge.features.film_studio.studio_contracts import MotionOutput
from agentforge.features.media import render
from agentforge.integrations import comfy_service, comfyui
from agentforge.paths import ensure_local_root

FRAMES = 49  # Studio's approved preset, independent of experimental pilot presets.
ADAPTER_ID = motion_ltx.FORMAT


def workflow_sha(profile=None):
    return hashlib.sha256(_workflow_bytes(profile)).hexdigest()


def weights_identity(profile=None):
    if profile and "comfy_video" in profile:
        return motion_ltx.configured_weights(profile["comfy_video"])
    return {motion_ltx.CHECKPOINT: motion_ltx.CHECKPOINT_SHA, motion_ltx.ENCODER: motion_ltx.ENCODER_SHA}


def check_legacy_workflow(folder):
    workflow = ensure_local_root(folder / "motion-workflow.json")
    if workflow.exists() and motion_comfy.inspect_workflow(workflow)["sha256"] != workflow_sha():
        raise ValueError("Stored motion workflow differs from the original runtime; create a new production.")


def _workflow_bytes(profile=None):
    record = (motion_ltx.configured_workflow(profile["comfy_video"], profile["model"])
              if profile and "comfy_video" in profile else motion_ltx.workflow(FRAMES))
    if profile and "comfy_video" in profile:
        return (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()
    return (json.dumps(record, indent=2) + "\n").encode()


def input_modes(profile):
    record = profile.get("comfy_video")
    return (motion_ltx.configured_input_mode(record),) if record else ("image-to-video",)


def output_profile(profile):
    preset = (motion_ltx.configured_output(profile["comfy_video"])
              if profile and "comfy_video" in profile else motion_ltx.profile(FRAMES))
    return MotionOutput(preset["fps"], preset["frames"], (preset["width"], preset["height"]))


def supports(profile):
    if (profile.get("provider") != "comfyui" or not profile.get("motion_encoder")
            or "flux" in profile or "comfy_image" in profile):
        return False
    if "comfy_video" in profile:
        try:
            motion_ltx.configured_workflow(profile["comfy_video"], profile["model"])
            return True
        except (ValueError, KeyError, TypeError):
            return False
    return profile.get("model") in (motion_ltx.CHECKPOINT, motion_ltx.MODEL_ID)


def bind(profile):
    endpoint = urlsplit(profile.get("base_url", ""))
    if (not supports(profile) or endpoint.port != motion_comfy.PORT
            or endpoint.hostname not in {"localhost", "127.0.0.1"}):
        raise ValueError("Hãy gán workflow video, checkpoint và encoder tương thích đúng endpoint Motion cho film.motion.")
    config = comfy_service._settings()
    if not config or config["port"] != endpoint.port:
        raise ValueError("Hãy đăng ký ComfyUI Portable cho endpoint Motion trong Môi trường & Tài nguyên.")
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not render.find_media_tool(tool)]
    if missing:
        raise ValueError("Thiếu công cụ xác minh video: " + ", ".join(missing)
                         + ". AgentForge tìm trong data/company/runtime_tools/ffmpeg hoặc PATH của backend.")
    return profile


def registry_readiness(profile):
    """Inspect the installed Studio preset without starting ComfyUI or a job."""
    endpoint = urlsplit(profile["base_url"])
    port = endpoint.port
    if port != motion_comfy.PORT or endpoint.hostname not in {"localhost", "127.0.0.1"}:
        return "MOTION_ENDPOINT_MISMATCH"
    try:
        stats = comfyui.request_json("/system_stats", port=port, timeout=3)
        devices = stats.get("devices") if isinstance(stats, dict) else None
        if not isinstance(devices, list):
            return "INVALID_RESPONSE"
        if not any(isinstance(device, dict) and device.get("type") == "cuda" for device in devices):
            return "GPU_UNAVAILABLE"
    except (OSError, http.client.HTTPException, comfyui.ComfyUITransportError, comfyui.ComfyHTTPError) as exc:
        return comfyui.failure_status(exc)
    try:
        if "comfy_video" in profile:
            motion_ltx.check_runtime(port, require_models=True, record=profile["comfy_video"])
        else:
            motion_ltx.check_runtime(port, require_models=True, frames=FRAMES)
    except (OSError, http.client.HTTPException, comfyui.ComfyUITransportError, comfyui.ComfyHTTPError) as exc:
        return comfyui.failure_status(exc)
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RuntimeError):
        return "MOTION_WORKFLOW_UNAVAILABLE"
    # Endpoint metadata does not establish process ownership. Keep the same
    # on-disk requirements as dispatch, including for externally started ComfyUI.
    config = comfy_service._settings()
    if not config or config["port"] != port:
        return "MOTION_LAUNCHER_REQUIRED"
    if not all(render.find_media_tool(tool) for tool in ("ffmpeg", "ffprobe")):
        return "MEDIA_TOOLS_UNAVAILABLE"
    try:
        if "comfy_video" in profile:
            motion_ltx.verify_configured_weights(profile["comfy_video"], config["install_root"],
                                                 profile["motion_encoder"], metadata_only=True)
        else:
            motion_ltx.verify_weights(config["install_root"], profile["motion_encoder"], metadata_only=True)
    except (OSError, ValueError):
        return "MOTION_WEIGHTS_UNAVAILABLE"
    return "READY"


def verify_clip(scene, stream):
    receipt = motion_verify.inspect_receipt(scene["motion_job"], film_root=motion_comfy.FILMS,
                                           db_path=motion_comfy.DB, video_stream=stream)
    if receipt["clip_sha256"] != scene["motion_sha"]:
        raise ValueError("Motion clip hash mismatch")


MAX_CLIP_BYTES = motion_verify.MAX_MP4_BYTES


def prepare(job, folder, profile=None):
    slug = "draft-" + job["id"]
    if "storyboard_version" in job:
        slug = f"d-{job['id']}-v{job['storyboard_version']}"
    shot_count = job["brief"]["scene_count"]
    plan = long_form.build_plan(title=job["board"]["title"], genre="Studio",
        style=("Configured motion draft" if profile and "comfy_video" in profile else "LTX motion draft"), chapters=[{"id": "draft", "title": job["board"]["title"],
        "synopsis": "Motion draft from the approved storyboard.", "duration_seconds": shot_count*4,
        "character_ids": []}], shot_seconds=4)
    try:
        long_form.save_plan(motion_comfy.FILMS, slug, plan)
    except FileExistsError:
        if long_form.load_plan(motion_comfy.FILMS, slug) != plan:
            raise ValueError("Motion plan changed; create a new draft") from None
    workflow = ensure_local_root(folder / "motion-workflow.json")
    payload = _workflow_bytes(profile)
    try:
        with workflow.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        pass
    digest = hashlib.sha256(payload).hexdigest()
    if motion_comfy.inspect_workflow(workflow)["sha256"] != digest:
        raise ValueError("Draft motion workflow changed")
    return slug, plan["plan_sha256"], workflow, digest


def require_resolved_ledger(job):
    owned = {scene.get("motion_job") for scene in job.get("board", {}).get("scenes", [])}
    conn = motion_comfy._db(motion_comfy.DB)
    if conn is not None:
        with closing(conn):
            if any(row[0] not in owned for row in conn.execute(
                    "SELECT job_id FROM motion_jobs WHERE state IN ('SUBMITTING','SUBMITTED')")):
                raise draft_resources.ResourceBlocked("MOTION_RECONCILIATION_REQUIRED")


def require_draft_removable(ident):
    conn = motion_comfy._db(motion_comfy.DB)
    if conn is not None:
        with closing(conn):
            if conn.execute(
                "SELECT 1 FROM motion_jobs WHERE state IN ('SUBMITTING','SUBMITTED') "
                "AND (film_slug=? OR film_slug GLOB ?) LIMIT 1",
                (f"draft-{ident}", f"d-{ident}-v[0-9]*"),
            ).fetchone():
                raise ValueError("Cần đối soát tác vụ chuyển động trước khi xóa bản nháp.")


def reconcile_cancelled(job):
    terminal = {"COMFY_COMPLETE_NOT_IMPORTED_OR_VERIFIED", motion_verify.TECHNICAL,
                "PROVIDER_FAILED", "GPU_RESOURCE_FAILURE"}
    for scene in job["board"]["scenes"]:
        if scene.get("motion_job"):
            try:
                status = motion_comfy.job_status(scene["motion_job"], db_path=motion_comfy.DB)["status"]
            except (OSError, RuntimeError, ValueError, http.client.HTTPException):
                return False
            if status not in terminal:
                return False
    return True


def _resource_stop_reason():
    sample = draft_resources.memory_snapshot()
    ram, used, limit = (sample[key] for key in ("ram_available", "commit_used", "commit_limit"))
    if ram is None or used is None or limit is None:
        return "Không đọc được RAM hoặc Windows commit."
    if ram < 4*1024**3:
        return "RAM khả dụng dưới 4 GiB."
    if limit-used < 6*1024**3:
        return "Windows commit headroom dưới 6 GiB."
    return None


def _provider(job_id, cancelled):
    row = motion_verify._job(job_id, motion_comfy.DB)
    if not row["provider_id"]:
        raise NeedsReconciliation("Motion dispatch requires reconciliation")
    provider = str(UUID(row["provider_id"]))
    deadline = time.monotonic() + 240
    stop_actions = set()
    stop_reason = None
    while time.monotonic() < deadline:
        try:
            status = motion_comfy.job_status(job_id, db_path=motion_comfy.DB)["status"]
        except (OSError, http.client.HTTPException, motion_comfy.MotionError) as exc:
            raise NeedsReconciliation("Motion provider disconnected; reconcile the existing job") from exc
        if status in {"COMFY_COMPLETE_NOT_IMPORTED_OR_VERIFIED", motion_verify.TECHNICAL}:
            if stop_actions:
                raise ValueError("Motion finished after an interrupt request; review before continuing")
            return
        if status != "PROVIDER_QUEUED_OR_UNKNOWN":
            if status in {"PROVIDER_FAILED", "GPU_RESOURCE_FAILURE"} and stop_reason:
                raise ValueError("AgentForge đã yêu cầu ngắt chuyển động. " + stop_reason)
            raise ValueError("Motion stopped: " + status)
        reason = stop_reason or ("Owner yêu cầu hủy." if cancelled() else _resource_stop_reason())
        if reason:
            try:
                queue = json.loads(comfy_service.comfyui.request_image_bytes("/queue", port=motion_comfy.PORT))
                pending = any(entry[1] == provider for entry in queue["queue_pending"])
                running = any(entry[1] == provider for entry in queue["queue_running"])
                action = "/queue" if pending else "/interrupt" if running else None
                if action and action not in stop_actions:
                    body = {"delete": [provider]} if pending else {"prompt_id": provider}
                    with closing(http.client.HTTPConnection("127.0.0.1", motion_comfy.PORT, timeout=3)) as conn:
                        conn.request("POST", action, body=json.dumps(body), headers={"Content-Type": "application/json"})
                        if conn.getresponse().status != 200:
                            raise NeedsReconciliation("Motion interrupt unconfirmed; reconcile before continuing")
                    stop_actions.add(action)
                    stop_reason = reason
            except NeedsReconciliation:
                raise
            except (OSError, http.client.HTTPException, ValueError, RuntimeError, KeyError, IndexError, TypeError) as exc:
                raise NeedsReconciliation("Motion interrupt unconfirmed; reconcile before continuing") from exc
        time.sleep(1)
    raise NeedsReconciliation("Motion completion unconfirmed; reconcile the existing job before continuing")


def clip_path(scene):
    job_id = scene["motion_job"]
    receipt = motion_verify.inspect_receipt(job_id, db_path=motion_comfy.DB, film_root=motion_comfy.FILMS)
    if receipt["clip_sha256"] != scene["motion_sha"]:
        raise ValueError("Motion clip changed since checkpoint")
    return (motion_comfy.FILMS / receipt["film_slug"] / "motion_clips" / job_id / "clip.mp4")


def _collect_clip(job_id, name, folder):
    if not isinstance(name, str) or not re.fullmatch(r"af_motion_" + job_id + r"_[0-9]{5}_\.mp4", name):
        raise ValueError("Motion output does not match the ledger job")
    if comfy_service.status()["managed"]:
        return motion_verify.import_clip(job_id=job_id, filename=name,
            output_dir=comfy_service.RUNTIME_DIR/"output", confirmed=True,
            db_path=motion_comfy.DB, film_root=motion_comfy.FILMS)
    # External ComfyUI may use a different output directory. Fetch only the
    # exact file identified by this job's history from the fixed local endpoint.
    query = urlencode({"filename": name, "type": "output", "subfolder": ""})
    start = time.monotonic()
    with (tempfile.TemporaryDirectory(prefix="motion-output-", dir=ensure_local_root(folder)) as staging,
          closing(http.client.HTTPConnection("127.0.0.1", motion_comfy.PORT, timeout=5)) as conn):
        conn.request("GET", "/view?" + query)
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError("ComfyUI could not provide the motion MP4")
        remaining = motion_verify.MAX_MP4_BYTES
        with (Path(staging)/name).open("xb") as stream:
            while chunk := response.read1(min(65536, remaining + 1)):
                remaining -= len(chunk)
                if remaining < 0 or time.monotonic() - start > 60:
                    raise ValueError("Motion MP4 exceeded its download limit")
                stream.write(chunk)
        return motion_verify.import_clip(job_id=job_id, filename=name, output_dir=Path(staging),
            confirmed=True, db_path=motion_comfy.DB, film_root=motion_comfy.FILMS)


def collect_verified_clip(job_id, folder):
    """Shared receipt-first collection for production and explicit probes."""
    try:
        return motion_verify.inspect_receipt(job_id, db_path=motion_comfy.DB, film_root=motion_comfy.FILMS)
    except KeyError:
        row = motion_verify._job(job_id, motion_comfy.DB)
        provider_id = str(UUID(row["provider_id"]))
        history = motion_comfy._json_request("/history/" + provider_id)[provider_id]
        entries = history["outputs"]["13"]["images"]
        if len(entries) != 1 or entries[0]["type"] != "output" or entries[0]["subfolder"] != "":
            raise ValueError("Motion output metadata is invalid")
        return _collect_clip(job_id, entries[0]["filename"], folder)


def retryable_motion_job(job_id):
    row = motion_verify._job(job_id, motion_comfy.DB)
    if row["state"] not in {"FAILED", "FAILED_RESOURCE"}:
        raise ValueError("Lần chạy chuyển động cũ chưa kết thúc ở trạng thái lỗi. Hãy đối soát trước.")
    return row


def run_shot(scene, index, prepared, profile, save, cancelled, *, dispatch_guard=nullcontext,
             retry_motion_job=None, previous_motion=None):
    slug, plan_sha, workflow, digest = prepared
    is_i2v = "image-to-video" in input_modes(profile)
    if previous_motion is not None and not is_i2v:
        raise ValueError("Frame continuation requires an image-to-video workflow.")
    if previous_motion is not None:
        clip_path(previous_motion)
    if scene.get("motion_sha"):
        clip_path(scene)
        if previous_motion is not None:
            _record_continuation(scene, previous_motion)
        return
    if retry_motion_job is not None:
        row = retryable_motion_job(retry_motion_job)
        if (scene.get("motion_job") != retry_motion_job or
                (row["film_slug"], row["shot_id"], row["plan_sha"]) != (slug, f"sh-{index+1:05d}", plan_sha)):
            raise ValueError("Checkpoint chuyển động đã thay đổi. Hãy tải lại trước khi thử lại.")
    if not scene.get("motion_job") or retry_motion_job is not None:
        if cancelled():
            return

        def reserve(job_id):
            scene["motion_job"] = job_id
            save()
            if cancelled():
                raise ValueError("Draft cancelled before motion dispatch")
        try:
            motion_comfy.submit_shot(film_slug=slug, shot_id=f"sh-{index+1:05d}", plan_sha=plan_sha,
                prompt=draft_continuity.prompt(scene, image_input=False) if not is_i2v else draft_continuity.prompt(scene),
                workflow_path=workflow, workflow_sha=digest, seed=scene.get("motion_seed", 42+index), confirmed=True,
                **({"image_job": scene["job_id"], "image_sha": scene["asset"]} if is_i2v else {}),
                ltx_encoder=Path(profile["motion_encoder"]), confirm_ltx_gate_b=True, on_reserved=reserve,
                confirm_new_attempt=retry_motion_job is not None,
                db_path=motion_comfy.DB, film_root=motion_comfy.FILMS, dispatch_guard=dispatch_guard,
                **({"previous_motion": previous_motion} if previous_motion is not None else {}))
        except (OSError, ValueError, RuntimeError, http.client.HTTPException) as exc:
            if scene.get("motion_job") and motion_verify._job(scene["motion_job"], motion_comfy.DB)["state"] == "SUBMITTING":
                raise NeedsReconciliation("Motion submission requires reconciliation") from exc
            raise
    job_id = scene["motion_job"]
    with model_hub.local_inference_slot():
        _provider(job_id, cancelled)
        if cancelled():
            return
        receipt = collect_verified_clip(job_id, workflow.parent)
        if previous_motion is not None:
            _record_continuation(scene, previous_motion)
        scene["motion_sha"] = receipt["clip_sha256"]
        save()


def _record_continuation(scene, previous_motion):
    marker = motion_verify.continuation_marker(previous_motion)
    conn = motion_comfy._db(motion_comfy.DB)
    if conn is None:
        raise ValueError("Motion source ledger unavailable")
    with closing(conn):
        row = conn.execute("SELECT image_job,image_sha FROM motion_sources WHERE job_id=?",
                           (scene["motion_job"],)).fetchone()
    if row is None or row["image_job"] != marker or not motion_comfy.SHA.fullmatch(row["image_sha"]):
        raise ValueError("Motion checkpoint does not match the approved continuation source")
    evidence = {"source": marker, "image_sha256": row["image_sha"]}
    if scene.get("motion_source") not in (None, evidence):
        raise ValueError("Continuation frame provenance changed")
    scene["motion_source"] = evidence
