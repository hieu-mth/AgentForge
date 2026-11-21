"""Bounded Studio production using the existing LTX pilot and motion ledger."""
import hashlib
import http.client
import json
import re
import shutil
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_resources, long_form, motion_comfy, motion_ltx, motion_verify
from agentforge.integrations import comfy_service
from agentforge.paths import ensure_local_root

FRAMES = 49
MAX_SHOTS = 3
SECONDS_PER_SHOT = 2


class NeedsReconciliation(ValueError):
    """A provider job may still exist and must never be submitted again."""


def binding(bindings):
    profile = bindings.get("film.motion", {})
    endpoint = urlsplit(profile.get("base_url", ""))
    if (profile.get("provider") != "comfyui" or profile.get("model") not in (motion_ltx.CHECKPOINT, motion_ltx.MODEL_ID)
            or not profile.get("motion_encoder") or endpoint.port != motion_comfy.PORT
            or endpoint.hostname not in {"localhost", "127.0.0.1"}):
        raise ValueError("Assign an LTX 2B FP8 checkpoint and encoder to film.motion on the Motion endpoint")
    config = comfy_service._settings()
    if not config or config["port"] != endpoint.port:
        raise ValueError("Configure the AgentForge ComfyUI launcher on the Motion endpoint")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise ValueError("Motion verification requires FFmpeg and ffprobe on AgentForge's PATH")
    return profile


def prepare(job, folder):
    slug = "draft-" + job["id"]
    if "storyboard_version" in job:
        slug = f"d-{job['id']}-v{job['storyboard_version']}"
    shot_count = job["brief"]["scene_count"]
    plan = long_form.build_plan(title=job["board"]["title"], genre="Studio",
        style="LTX motion draft", chapters=[{"id": "draft", "title": job["board"]["title"],
        "synopsis": "Motion draft from the approved storyboard.", "duration_seconds": shot_count*4,
        "character_ids": []}], shot_seconds=4)
    try:
        long_form.save_plan(motion_comfy.FILMS, slug, plan)
    except FileExistsError:
        if long_form.load_plan(motion_comfy.FILMS, slug) != plan:
            raise ValueError("Motion plan changed; create a new draft") from None
    workflow = ensure_local_root(folder / "motion-workflow.json")
    payload = (json.dumps(motion_ltx.workflow(FRAMES), indent=2) + "\n").encode()
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


def _provider(job_id, cancelled):
    row = motion_verify._job(job_id, motion_comfy.DB)
    if not row["provider_id"]:
        raise NeedsReconciliation("Motion dispatch requires reconciliation")
    provider = str(UUID(row["provider_id"]))
    deadline = time.monotonic() + 240
    stop_actions = set()
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
            raise ValueError("Motion stopped: " + status)
        sample = draft_resources.snapshot()
        used, limit = sample["commit_used"], sample["commit_limit"]
        ram = sample["ram_available"]
        if (stop_actions or cancelled() or ram is None or ram < 4*1024**3
                or used is None or limit is None or limit-used < 6*1024**3):
            queue = json.loads(comfy_service.comfyui.request_image_bytes("/queue", port=motion_comfy.PORT))
            pending = any(entry[1] == provider for entry in queue["queue_pending"])
            action, body = (("/queue", {"delete": [provider]}) if pending
                            else ("/interrupt", {"prompt_id": provider}))
            if action not in stop_actions:
                stop_actions.add(action)
                with closing(http.client.HTTPConnection("127.0.0.1", motion_comfy.PORT, timeout=3)) as conn:
                    conn.request("POST", action, body=json.dumps(body), headers={"Content-Type": "application/json"})
                    if conn.getresponse().status != 200:
                        raise NeedsReconciliation("Motion interrupt unconfirmed; reconcile before continuing")
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


def run_shot(scene, index, prepared, profile, save, cancelled):
    slug, plan_sha, workflow, digest = prepared
    if scene.get("motion_sha"):
        clip_path(scene)
        return
    if not scene.get("motion_job"):
        if cancelled():
            return

        def reserve(job_id):
            scene["motion_job"] = job_id
            save()
            if cancelled():
                raise ValueError("Draft cancelled before motion dispatch")
        try:
            motion_comfy.submit_shot(film_slug=slug, shot_id=f"sh-{index+1:05d}", plan_sha=plan_sha,
                prompt=("Animate this shot with natural movement, preserving character identity. "
                        + scene.get("motion_prompt", scene["description"]) + " " + scene.get("scene_notes", "")),
                workflow_path=workflow, workflow_sha=digest, seed=42+index, confirmed=True,
                image_job=scene["job_id"], image_sha=scene["asset"],
                ltx_encoder=Path(profile["motion_encoder"]), confirm_ltx_gate_b=True, on_reserved=reserve,
                db_path=motion_comfy.DB, film_root=motion_comfy.FILMS)
        except (OSError, ValueError, RuntimeError, http.client.HTTPException) as exc:
            if scene.get("motion_job") and motion_verify._job(scene["motion_job"], motion_comfy.DB)["state"] == "SUBMITTING":
                raise NeedsReconciliation("Motion submission requires reconciliation") from exc
            raise
    job_id = scene["motion_job"]
    with model_hub.local_inference_slot():
        _provider(job_id, cancelled)
        if cancelled():
            return
        try:
            receipt = motion_verify.inspect_receipt(job_id, db_path=motion_comfy.DB, film_root=motion_comfy.FILMS)
        except KeyError:
            row = motion_verify._job(job_id, motion_comfy.DB)
            provider_id = str(UUID(row["provider_id"]))
            history = motion_comfy._json_request("/history/" + provider_id)[provider_id]
            entries = history["outputs"]["13"]["images"]
            if len(entries) != 1 or entries[0]["type"] != "output" or entries[0]["subfolder"] != "":
                raise ValueError("Motion output metadata is invalid")
            receipt = _collect_clip(job_id, entries[0]["filename"], workflow.parent)
        scene["motion_sha"] = receipt["clip_sha256"]
        save()
