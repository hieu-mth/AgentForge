"""Explicit Owner media tests; persist reservations before external side effects."""
import hashlib
import json
import sqlite3
from contextlib import closing

from agentforge import ops_control
from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_motion_cloud as motion, studio_runtime
from agentforge.features.film_studio.studio_contracts import ProviderRequestError
from agentforge.features.film_studio.draft_resources import NeedsReconciliation
from agentforge.features.media import visual_jobs
from agentforge.paths import ensure_local_root

MAX_VIDEO = motion.MAX_CLIP_BYTES


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


def _image_reply(ident, profile):
    row = visual_jobs._row(ident)
    metadata = visual_jobs.runtime_details(ident)
    if not metadata or not metadata.get("probe") or metadata.get("profile_sha") != _fingerprint(profile):
        raise ValueError("Image probe does not match this profile.")
    ready = row["status"] == "ASSET_READY"
    if ready:
        with visual_jobs.open_image_for_job(ident):
            pass
    return {"probe_id": ident, "status": "ASSET_READY" if ready else
            ("REJECTED" if row["status"] == "REJECTED" else "NEEDS_RECONCILIATION"),
            "preview_url": "/api/visuals/" + ident + "/preview" if ready else None,
            **({"error": metadata["error"]} if "error" in metadata else {})}


def _start_video(ident, profile, prompt):
    adapter = studio_runtime.motion_adapter(profile)
    adapter.bind(profile)
    transport = motion._transport(profile)
    seconds = min(adapter.billable_durations(profile))
    body = transport.payload(profile["model"], prompt, seconds, audio=adapter.native_audio(profile))
    token = motion._key(profile)
    marker = "probe:" + _fingerprint(profile)
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    with closing(motion._db(True)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM jobs WHERE id=?", (ident,)).fetchone()
        if row:
            if row["production"] != marker or row["request_sha"] != digest:
                raise ValueError("Probe ID already belongs to another request.")
            return _video_reply(dict(row))
        db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                   (ident, marker, "text-to-video", profile["model"], seconds, digest, "SUBMITTING", None, None))
    try:
        remote = transport.submit_video(body, token, "text-to-video")
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


def handle(request):
    action = request.get("ack")
    common = {"ack", "profile_id", "expected_revision", "probe_id"}
    if action not in {"RUN_MEDIA_MODEL_PROBE", "POLL_MEDIA_MODEL_PROBE"} or set(request) != (
            common | {"prompt"} if action == "RUN_MEDIA_MODEL_PROBE" else common):
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
        if model_hub.orchestrator_policy.compatible("image", profile):
            if action == "RUN_MEDIA_MODEL_PROBE":
                try:
                    return _image_reply(ident, profile)
                except KeyError:
                    pass
                request_data = studio_runtime.ImageRequest(prompt, "16:9", "", ident, request["expected_revision"])
                try:
                    studio_runtime.image_adapter(profile).generate(profile, request_data)
                except (NeedsReconciliation, ProviderRequestError):
                    pass
            return _image_reply(ident, profile)
        if model_hub.orchestrator_policy.compatible("video", profile):
            return _start_video(ident, profile, prompt) if action == "RUN_MEDIA_MODEL_PROBE" else _poll_video(ident, profile)
        raise ValueError("Unsupported media probe capability.")
