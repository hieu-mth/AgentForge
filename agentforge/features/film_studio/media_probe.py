"""Explicit Owner media tests; persist reservations before external side effects."""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from agentforge import ops_control
from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_motion_cloud as motion, studio_runtime
from agentforge.features.film_studio import draft_motion, long_form, motion_comfy, motion_verify
from agentforge.features.film_studio.studio_contracts import ProviderRequestError
from agentforge.features.film_studio.draft_resources import NeedsReconciliation
from agentforge.features.media import flux_runtime, visual_jobs
from agentforge.paths import ensure_local_root

MAX_VIDEO = max(motion.MAX_CLIP_BYTES, motion_verify.MAX_MP4_BYTES)


def _fingerprint(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()


def video_record(ident):
    row = motion._row(visual_jobs._id(ident))
    if not row["production"].startswith("probe:"):
        raise ValueError("Not a media probe.")
    return row


def video_path(row):
    if row["state"] != "VERIFIED":
        raise ValueError("Media probe is not ready.")
    return motion._path(row)


def verify_video(row, stream):
    motion.verify_clip({"motion_job": row["id"], "motion_sha": row["output_sha"]}, stream)


def _video_reply(row):
    state = row["state"]
    detail = motion.submission_error(row["id"]) if state == "REJECTED" else None
    return {"probe_id": row["id"], "status": {"VERIFIED": "ASSET_READY", "SUBMITTING": "NEEDS_RECONCILIATION"}.get(state, state),
            "preview_url": "/api/model-hub/media-probe/" + row["id"] + "/preview" if state == "VERIFIED" else None,
            **({"error": detail["message"]} if detail else {})}


IMAGE_OPTIONS = frozenset({"width", "height", "steps", "seed"})


def _image_reply(ident, profile, prompt=None, options=None):
    row = visual_jobs._row(ident)
    metadata = visual_jobs.runtime_details(ident)
    if not metadata or not metadata.get("probe") or metadata.get("profile_sha") != _fingerprint(profile):
        raise ValueError("Image probe does not match this profile.")
    local = not model_hub.is_cloud(profile)
    if prompt is not None:
        if local:
            if metadata.get("probe_request_sha") != _fingerprint({"prompt": prompt, "options": options or {}}):
                raise ValueError("Probe ID already belongs to another request.")
        elif metadata.get("prompt") != prompt:
            raise ValueError("Probe ID already belongs to another request.")
    ready = row["status"] == "ASSET_READY"
    if ready:
        with visual_jobs.open_image_for_job(ident):
            pass
    state = row["status"]
    status = ("ASSET_READY" if ready else "REJECTED" if state in {"REJECTED", "WORKFLOW_REJECTED"} else
              "FAILED" if state in {"EXECUTION_FAILED", "GPU_RESOURCE_FAILURE", "CANCELLED"} else "NEEDS_RECONCILIATION")
    result = {"probe_id": ident, "status": status,
              "preview_url": "/api/visuals/" + ident + "/preview" if ready else None,
              **({"error": metadata["error"]} if "error" in metadata else {})}
    if local:
        result.update({key: metadata[key] for key in ("width", "height", "steps", "seed", "duration_seconds")})
        if ready:
            result["workspace_path"] = f"workspace/{metadata['output_dir']}/{ident}.png"
        else:
            result["error"] = state
    return result


def _video_input(profile, source):
    adapter = studio_runtime.motion_adapter(profile)
    mode = "image-to-video" if source is not None else "text-to-video"
    if mode not in adapter.input_modes(profile):
        raise ValueError("Video probe does not support " + mode + " for this profile.")
    if source is None:
        return mode, None
    ident = visual_jobs._id(source)
    row = visual_jobs._row(ident)
    return mode, visual_jobs.read_motion_source(ident, row["asset_sha"])


def _start_video(ident, profile, prompt, source=None):
    adapter = studio_runtime.motion_adapter(profile)
    endpoint, image = _video_input(profile, source)
    adapter.bind(profile)
    transport = motion._transport(profile)
    seconds = min(adapter.billable_durations(profile))
    body = transport.payload(profile["model"], prompt, seconds, image=image, audio=adapter.native_audio(profile))
    token = motion._key(profile)
    marker = "probe:" + _fingerprint(profile)
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    with closing(motion._db(True)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM jobs WHERE id=?", (ident,)).fetchone()
        if row:
            if row["production"] != marker or row["request_sha"] != digest or row["endpoint"] != endpoint:
                raise ValueError("Probe ID already belongs to another request.")
            return _video_reply(dict(row))
        db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                   (ident, marker, endpoint, profile["model"], seconds, digest, "SUBMITTING", None, None))
    try:
        remote = transport.submit_video(body, token, endpoint)
        motion._state(ident, "SUBMITTED", provider_id=remote)
    except ProviderRequestError as exc:
        if exc.rejected:
            motion.reject_submission(ident, exc)
            return _video_reply(video_record(ident))
        return {"probe_id": ident, "status": "NEEDS_RECONCILIATION", "preview_url": None, "error": str(exc)}
    except (ValueError, OSError, TypeError, sqlite3.Error):
        return {"probe_id": ident, "status": "NEEDS_RECONCILIATION", "preview_url": None}
    return _video_reply(video_record(ident))


def _poll_video(ident, profile):
    row = video_record(ident)
    if row["production"] != "probe:" + _fingerprint(profile):
        raise ValueError("Media probe profile changed.")
    if row["state"] != "SUBMITTED":
        return _video_reply(row)
    response = motion._poll(row, profile)
    if response["status"] == "failed":
        motion._state(ident, "FAILED")
    elif response["status"] == "completed":
        target = motion._path(row)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = ensure_local_root(target.with_suffix(".part.mp4"))
        try:
            if not target.exists():
                temporary.unlink(missing_ok=True)
                motion._transport(profile).download_video(response, temporary, row["seconds"])
                digest = motion.verify_download(temporary, row["seconds"], profile)
                temporary.replace(target)
            else:
                digest = motion.verify_download(target, row["seconds"], profile)
            motion._state(ident, "VERIFIED", digest=digest)
        finally:
            temporary.unlink(missing_ok=True)
    return _video_reply(video_record(ident))


def _local_row(ident):
    slug = "probe-" + visual_jobs._id(ident)
    conn = motion_comfy._db(motion_comfy.DB)
    if conn is None:
        return None
    with closing(conn):
        rows = conn.execute("SELECT * FROM motion_jobs WHERE film_slug=?", (slug,)).fetchall()
    if len(rows) > 1:
        raise NeedsReconciliation("Multiple local probe attempts; review ledger.")
    return dict(rows[0]) if rows else None


def local_video_record(ident):
    row = _local_row(ident)
    if row is None:
        raise KeyError("Local video probe not found.")
    return motion_verify.inspect_receipt(row["job_id"], db_path=motion_comfy.DB, film_root=motion_comfy.FILMS)


def local_video_path(receipt):
    return draft_motion.clip_path({"motion_job": receipt["job_id"], "motion_sha": receipt["clip_sha256"]})


def verify_local_video(receipt, stream):
    draft_motion.verify_clip({"motion_job": receipt["job_id"], "motion_sha": receipt["clip_sha256"]}, stream)


def _local_reply(ident, status):
    return {"probe_id": ident, "status": status,
            "preview_url": "/api/model-hub/media-probe/" + ident + "/local-preview" if status == "ASSET_READY" else None}


def _collect_local(ident, row):
    job_id = row["job_id"]
    if row["state"] == "SUBMITTING":
        return _local_reply(ident, "NEEDS_RECONCILIATION")
    with model_hub.local_inference_slot():
        if row["state"] in {"FAILED", "FAILED_RESOURCE"}:
            return _local_reply(ident, "FAILED")
        try:
            draft_motion._provider(job_id, lambda: False)
        except NeedsReconciliation:
            return _local_reply(ident, "NEEDS_RECONCILIATION")
        except ValueError:
            if motion_comfy.job_status(job_id, db_path=motion_comfy.DB)["status"] in {"PROVIDER_FAILED", "GPU_RESOURCE_FAILURE"}:
                return _local_reply(ident, "FAILED")
            raise
        draft_motion.collect_verified_clip(job_id, motion_comfy.FILMS / row["film_slug"])
        return _local_reply(ident, "ASSET_READY")


def _local_video(ident, profile, prompt=None, source=None):
    slug = "probe-" + visual_jobs._id(ident)
    row = _local_row(ident)
    if prompt is not None:
        mode, image = _video_input(profile, source)
        digest = hashlib.sha256(image).hexdigest() if image is not None else None
        request_sha = _fingerprint({"prompt": prompt, "source": source, "sha": digest})
        plan = long_form.build_plan(title=_fingerprint(profile), genre="Probe", style="Local model probe",
            chapters=[{"id": "probe", "title": "Probe", "synopsis": request_sha,
                       "duration_seconds": 4, "character_ids": []}], shot_seconds=4)
        try:
            long_form.save_plan(motion_comfy.FILMS, slug, plan)
        except FileExistsError:
            if long_form.load_plan(motion_comfy.FILMS, slug) != plan:
                raise ValueError("Probe ID already belongs to another request.")
        if row is None:
            draft_motion.bind(profile)
            workflow = ensure_local_root(motion_comfy.FILMS / slug / "motion-workflow.json")
            payload = draft_motion._workflow_bytes(profile)
            try:
                with workflow.open("xb") as stream:
                    stream.write(payload)
            except FileExistsError:
                pass
            try:
                motion_comfy.submit_shot(film_slug=slug, shot_id="sh-00001", plan_sha=plan["plan_sha256"],
                    prompt=prompt, workflow_path=workflow, workflow_sha=draft_motion.workflow_sha(profile),
                    seed=42, confirmed=True, ltx_encoder=Path(profile["motion_encoder"]),
                    confirm_ltx_gate_b=mode == "image-to-video", image_job=source, image_sha=digest,
                    db_path=motion_comfy.DB, film_root=motion_comfy.FILMS)
            except (ValueError, OSError, RuntimeError):
                row = _local_row(ident)
                if row is None:
                    raise
            row = _local_row(ident)
    if row is None:
        raise KeyError("Local video probe not found.")
    plan = long_form.load_plan(motion_comfy.FILMS, slug)
    if (plan["title"] != _fingerprint(profile) or plan["plan_sha256"] != row["plan_sha"]
            or row["workflow_sha"] != draft_motion.workflow_sha(profile)):
        raise ValueError("Media probe profile changed.")
    return _collect_local(ident, row)


def handle(request):
    action = request.get("ack")
    common = {"ack", "profile_id", "expected_revision", "probe_id"}
    fields = set(request)
    if (action not in {"RUN_MEDIA_MODEL_PROBE", "POLL_MEDIA_MODEL_PROBE"} or
            (fields - (IMAGE_OPTIONS | {"source_image_job"}) if action == "RUN_MEDIA_MODEL_PROBE" else fields) !=
            (common | {"prompt"} if action == "RUN_MEDIA_MODEL_PROBE" else common)):
        raise ValueError("Invalid media probe request.")
    ident = visual_jobs._id(request["probe_id"])
    profile = model_hub.media_probe_profile(request["profile_id"], expected_revision=request["expected_revision"])
    ops_control.require_active()
    # Serialize explicit polls/submissions across local backend processes.
    with model_hub.local_process_slot(model_hub.DB_PATH.parent / "media_probe.worker", "MEDIA_PROBE_BUSY"):
        if action == "RUN_MEDIA_MODEL_PROBE":
            prompt = request["prompt"]
            if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
                raise ValueError("Enter a prompt of up to 2000 characters.")
        options = {key: request[key] for key in IMAGE_OPTIONS & fields}
        if model_hub.orchestrator_policy.compatible("image", profile):
            if "source_image_job" in request:
                raise ValueError("Image probe does not accept a video source.")
            local = not model_hub.is_cloud(profile)
            if options and not local:
                raise ValueError("Image options are only supported by local workflows.")
            if action == "RUN_MEDIA_MODEL_PROBE":
                try:
                    return _image_reply(ident, profile, prompt, options)
                except KeyError:
                    pass
                if local:
                    with model_hub.local_inference_slot():
                        flux_runtime.generate(prompt, profile_id=profile["id"],
                            expected_revision=request["expected_revision"], production_job=ident,
                            probe_request_sha=_fingerprint({"prompt": prompt, "options": options}), **options)
                else:
                    request_data = studio_runtime.ImageRequest(prompt, "16:9", "", ident, request["expected_revision"])
                    try:
                        studio_runtime.image_adapter(profile).generate(profile, request_data)
                    except (NeedsReconciliation, ProviderRequestError):
                        pass
            return _image_reply(ident, profile)
        if model_hub.orchestrator_policy.compatible("video", profile):
            if options:
                raise ValueError("Video probe does not accept image workflow options.")
            source = request.get("source_image_job")
            if not model_hub.is_cloud(profile):
                return _local_video(ident, profile, prompt if action == "RUN_MEDIA_MODEL_PROBE" else None, source)
            return _start_video(ident, profile, prompt, source) if action == "RUN_MEDIA_MODEL_PROBE" else _poll_video(ident, profile)
        raise ValueError("Unsupported media probe capability.")
