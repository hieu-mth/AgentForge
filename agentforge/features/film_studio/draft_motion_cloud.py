"""Shared cloud video lifecycle. Provider transports own request and output formats."""
import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing, nullcontext
from uuid import uuid4

from agentforge import ops_control
from agentforge.ai import model_hub, registry
from agentforge.features.film_studio import draft_continuity
from agentforge.features.film_studio.draft_resources import NeedsReconciliation, ResourceBlocked
from agentforge.features.film_studio.studio_contracts import ProviderRequestError
from agentforge.features.media import mp4, render, visual_jobs
from agentforge.paths import COMPANY_DATA_DIR, ensure_local_root

ADAPTER_ID = "cloud-motion-720p"
MAX_CLIP_BYTES = mp4.MAX_VIDEO_BYTES
DB = COMPANY_DATA_DIR / "cloud_motion.sqlite3"
RETRY_DELAYS = (60, 120, 300)


# Historical plans may omit provider duration metadata. Keep their original
# approved budget semantics until receipt migration; new routes pin durations.
_LEGACY_DURATIONS = (6, 8, 10)


def _transport(profile):
    return registry.resolve("cloud_video_transport", profile)


def supports(profile):
    if not profile.get("provider"):
        return False
    try:
        _transport(profile)
    except ValueError:
        return False
    return True


def billable_durations(profile):
    return _transport(profile).billable_durations(profile)


def native_audio(profile):
    return _transport(profile).native_audio(profile)


def input_modes(profile):
    return _transport(profile).input_modes(profile)


def output_profile(profile):
    return _transport(profile).output_profile(profile)


def verify_download(path, seconds, profile):
    spec = output_profile(profile)
    return mp4.verify_video(path, seconds, fps=spec.fps, resolution=spec.resolution,
                            require_audio=native_audio(profile))


def workflow_sha(profile):
    spec = output_profile(profile)
    # Preserve the historical fingerprint for the existing 720p/24fps contract.
    width, height = spec.resolution
    shape = "720p" if (width, height) == (1280, 720) else f"{width}x{height}"
    return hashlib.sha256(f"cloud-motion:{shape}:{spec.fps}fps:provider-duration-v1".encode()).hexdigest()


def weights_identity(profile):
    return {}  # Provider-managed weights cannot be fingerprinted locally.


def check_legacy_workflow(folder):
    raise ValueError("Cloud motion requires a new approved production.")


def registry_readiness(profile):
    return "CLOUD_VIDEO_NOT_PROBED"


def _key(profile):
    return _transport(profile).credential(profile)


def bind(profile):
    if not supports(profile):
        raise ValueError("Unsupported cloud video model.")
    _key(profile)
    if not all(render.find_media_tool(tool) for tool in ("ffmpeg", "ffprobe")):
        raise ValueError("Cloud video needs local FFmpeg and ffprobe for verification.")
    return profile


def billed_seconds(frames, durations, *, fps, max_frames):
    if (type(frames) is not int or not 1 <= frames <= max_frames
            or type(fps) is not int or fps <= 0
            or not durations or any(type(s) is not int or s <= 0 for s in durations)):
        raise ValueError("Cloud shot exceeds the approved video contract.")
    eligible = [seconds for seconds in durations if seconds * fps >= frames]
    if not eligible:
        raise ValueError("No billable duration covers the approved video shot.")
    return min(eligible)


def _profile_seconds(frames, profile):
    spec = output_profile(profile)
    return billed_seconds(frames, billable_durations(profile), fps=spec.fps, max_frames=spec.max_frames)


def _db(create=False):
    path = ensure_local_root(DB)
    if not create and not path.exists():
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path if create else path.as_uri() + "?mode=ro", uri=not create, timeout=5)
    conn.row_factory = sqlite3.Row
    if create:
        conn.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, production TEXT, endpoint TEXT, "
                     "model TEXT, seconds INTEGER, request_sha TEXT, state TEXT, provider_id TEXT, output_sha TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS submission_errors (id TEXT PRIMARY KEY, "
                     "attempts INTEGER NOT NULL, message TEXT NOT NULL, retry_at REAL)")
        conn.commit()
    return conn


def _row(ident):
    visual_jobs._id(ident)
    conn = _db()
    row = None
    if conn is not None:
        with closing(conn):
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (ident,)).fetchone()
    if not row:
        raise NeedsReconciliation("Cloud motion ledger is missing; do not submit again.")
    return dict(row)


def submission_error(ident):
    conn = _db()
    if conn is not None:
        with closing(conn):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='submission_errors'").fetchone():
                row = conn.execute("SELECT * FROM submission_errors WHERE id=?", (ident,)).fetchone()
                return dict(row) if row else None
    return None


def reject_submission(ident, error, *, automatic=False):
    """Persist definitive rejection before allowing another POST. Unknown stays SUBMITTING."""
    if not isinstance(error, ProviderRequestError) or not error.rejected:
        raise NeedsReconciliation("Provider rejection has not been established.")
    with closing(_db(True)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute("SELECT attempts FROM submission_errors WHERE id=?", (ident,)).fetchone()
        attempts = (prior[0] if prior else 0) + 1
        retry_at = None
        if automatic and error.retryable and attempts <= len(RETRY_DELAYS):
            delay = max(RETRY_DELAYS[attempts-1], error.retry_after or 0)
            # A server delay outside our bounded automatic window needs Owner action.
            if delay <= 900:
                retry_at = time.time() + delay
        changed = conn.execute("UPDATE jobs SET state='REJECTED' WHERE id=? AND state='SUBMITTING' AND provider_id IS NULL", (ident,))
        if changed.rowcount != 1:
            raise NeedsReconciliation("Cloud rejection checkpoint changed.")
        conn.execute("INSERT INTO submission_errors VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                     "attempts=excluded.attempts,message=excluded.message,retry_at=excluded.retry_at",
                     (ident, attempts, str(error), retry_at))
    return {"attempts": attempts, "message": str(error), "retry_at": retry_at}


def _rearm(ident, request_sha):
    with closing(_db(True)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        changed = conn.execute("UPDATE jobs SET state='SUBMITTING' WHERE id=? AND state='REJECTED' "
                               "AND provider_id IS NULL AND request_sha=? "
                               "AND EXISTS(SELECT 1 FROM submission_errors e WHERE e.id=jobs.id AND e.retry_at IS NOT NULL AND e.retry_at<=?)",
                               (ident, request_sha, time.time()))
        if changed.rowcount != 1:
            raise NeedsReconciliation("Cloud retry checkpoint changed.")


def _wait_rejected(job, row, save, cancelled):
    detail = submission_error(row["id"])
    if not detail or detail["retry_at"] is None:
        job.pop("cloud_wait", None)
        raise ValueError(detail["message"] if detail else "Cloud request was rejected.")
    job.update(status="WAITING_CLOUD_RESOURCES", error=detail["message"],
               cloud_wait={"retry_at": detail["retry_at"], "attempt": detail["attempts"], "max_retries": len(RETRY_DELAYS)})
    save()
    while time.time() < detail["retry_at"]:
        if cancelled():
            from agentforge.features.film_studio.draft_pipeline import DraftCancelled
            raise DraftCancelled
        ops_control.require_active()
        time.sleep(min(1, max(0, detail["retry_at"] - time.time())))
    job.update(status="RUNNING", error=None)
    job.pop("cloud_wait", None)
    save()


def reconciliation_jobs(job):
    """Read-only evidence for the exact production; never poll or submit on GET."""
    conn = _db()
    if conn is None:
        return []
    with closing(conn):
        return [dict(row) for row in conn.execute(
            "SELECT id, endpoint, model, seconds, request_sha, state, provider_id "
            "FROM jobs WHERE production=? AND state IN ('SUBMITTING','SUBMITTED') ORDER BY rowid",
            (job["id"],))]


def recover_provider_id(job, data, profile):
    """Owner-attested mapping, checked with provider GET only. Never sends another POST."""
    ident = visual_jobs._id(data["motion_job"])
    remote = _transport(profile)._id(data["provider_id"])
    if (data.get("owner_matched") is not True or job.get("status") != "NEEDS_RECONCILIATION"
            or not any(scene.get("motion_job") == ident and not scene.get("motion_sha")
                       for scene in job.get("board", {}).get("scenes", []))):
        raise PermissionError("Confirm the matching provider job for this unresolved shot.")
    row = _row(ident)
    if (row["production"] != job["id"] or row["state"] != "SUBMITTING"
            or row["provider_id"] is not None or row["model"] != profile["model"]
            or data.get("request_sha") != row["request_sha"]):
        raise ValueError("Cloud reconciliation checkpoint changed.")
    ops_control.require_active()
    # The API confirms existence/status, not provenance when the original POST was lost.
    response = _poll({**row, "provider_id": remote}, profile)
    with closing(_db(True)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM jobs WHERE provider_id=? AND id<>?", (remote, ident)).fetchone():
            raise ValueError("Provider job is already bound to another shot.")
        changed = conn.execute("UPDATE jobs SET state='SUBMITTED',provider_id=? "
                               "WHERE id=? AND production=? AND state='SUBMITTING' "
                               "AND provider_id IS NULL AND request_sha=?",
                               (remote, ident, job["id"], row["request_sha"]))
        if changed.rowcount != 1:
            raise ValueError("Cloud reconciliation checkpoint changed.")
    return {"motion_job": ident, "provider_id": remote, "provider_status": response["status"],
            "association": "OWNER_ATTESTED", "provider_status_verified": True}


def confirm_rejected_submission(job, data, profile):
    """Explicit Owner attestation of the original rejected POST, never a new POST."""
    ident = visual_jobs._id(data["motion_job"])
    evidence = data.get("provider_request_id")
    if (data.get("owner_confirmed_rejected") is not True
            or not isinstance(evidence, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,160}", evidence)
            or job.get("status") != "NEEDS_RECONCILIATION"):
        raise PermissionError("Require provider evidence for the original rejected request.")
    scenes = job.get("board", {}).get("scenes", [])
    matches = [i for i, scene in enumerate(scenes, 1)
               if scene.get("motion_job") == ident and not scene.get("motion_sha")]
    row = _row(ident)
    if (len(matches) != 1 or row["production"] != job["id"] or row["state"] != "SUBMITTING"
            or row["provider_id"] is not None or row["model"] != profile["model"]
            or row["request_sha"] != data.get("request_sha")):
        raise ValueError("Cloud reconciliation checkpoint changed.")
    # Keep the original reservation and history. Owner attestation is not an
    # independently verified provider response and never itself sends a request.
    with closing(_db(True)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        changed = conn.execute("UPDATE jobs SET state='REJECTED' WHERE id=? AND production=? "
                               "AND state='SUBMITTING' AND provider_id IS NULL AND request_sha=?",
                               (ident, job["id"], row["request_sha"]))
        if changed.rowcount != 1:
            raise ValueError("Cloud reconciliation checkpoint changed.")
        conn.execute("INSERT INTO submission_errors VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                     "message=excluded.message,retry_at=NULL",
                     (ident, len(RETRY_DELAYS)+1, "Owner confirmed original POST was rejected (not independently verified).", None))
    return {"motion_job": ident, "provider_request_id": evidence, "shot": matches[0],
            "association": "OWNER_ATTESTED_REJECTION", "provider_status_verified": False}


def _ledger_provider(model):
    """Infer the provider of a historical model-only receipt without network or DB writes.

    Unknown or ambiguous model IDs deliberately remain unscoped.
    """
    if not isinstance(model, str) or not model:
        return None
    matches = []
    for provider, descriptor in registry.ADAPTERS.items():
        if descriptor["connection"] != "cloud":
            continue
        profile = {"provider": provider, "model": model}
        matches.extend(provider for entry in registry.REGISTRATIONS
                       if entry.kind == "cloud_video_transport" and entry.matches(profile))
    return matches[0] if len(matches) == 1 else None


def require_resolved_ledger(job):
    """Block unresolved work in this production or the same cloud provider.

    Legacy receipts store a model ID rather than a provider. Isolate only when
    both providers can be uniquely resolved from the source-owned registry.
    Never discard receipts, release reservations, or dispatch during this check.
    """
    owned = {s.get("motion_job") for s in (job.get("board") or {}).get("scenes", [])}
    production = job.get("id")
    identity = job.get("approved_motion") or job.get("motion_plan") or {}
    provider = _ledger_provider(identity.get("model"))
    conn = _db()
    if conn is not None:
        with closing(conn):
            rows = conn.execute(
                "SELECT id, production, model FROM jobs WHERE production NOT LIKE 'probe:%' "
                "AND state IN ('SUBMITTING','SUBMITTED')")
            for row in rows:
                if row["id"] in owned and row["production"] == production:
                    continue
                other = _ledger_provider(row["model"])
                if (row["production"] == production or row["id"] in owned
                        or provider is None or other is None or provider == other):
                    raise ResourceBlocked("CLOUD_MOTION_RECONCILIATION_REQUIRED")


def require_draft_removable(ident):
    conn = _db()
    if conn is not None:
        with closing(conn):
            if conn.execute("SELECT 1 FROM jobs WHERE production=? AND state IN ('SUBMITTING','SUBMITTED')",
                            (ident,)).fetchone():
                raise ValueError("Cloud motion is unresolved; reconcile before deleting.")


def _path(row):
    from agentforge.features.film_studio import draft_pipeline as draft
    ident = visual_jobs._id(row["id"])
    if row["production"].startswith("probe:"):
        from agentforge.paths import WORKSPACE_DIR
        return ensure_local_root(WORKSPACE_DIR / "model-probes" / (ident + ".mp4"))
    return ensure_local_root(draft._folder(row["production"]) / ("cloud-" + ident + ".mp4"))


def verify_clip(scene, stream):
    row = _row(scene["motion_job"])
    if row["state"] != "VERIFIED" or row["output_sha"] != scene.get("motion_sha"):
        raise ValueError("Cloud clip is not verified.")
    digest = hashlib.sha256()
    length = 0
    while chunk := stream.read(1024 * 1024):
        length += len(chunk)
        if length > MAX_CLIP_BYTES:
            raise ValueError("Cloud clip too large.")
        digest.update(chunk)
    if digest.hexdigest() != row["output_sha"]:
        raise ValueError("Cloud clip hash mismatch.")


def clip_path(scene):
    path = _path(_row(scene["motion_job"]))
    with path.open("rb") as stream:
        verify_clip(scene, stream)
    return path


def remaining_seconds(job):
    durations = job.get("production_plan", {}).get("billable_durations_seconds", _LEGACY_DURATIONS)
    identity = job.get("approved_motion") or job.get("motion_plan") or {}
    # Historical cloud jobs stored only the original 24fps contract.
    output = identity.get("output", {"fps": 24, "max_frames": 240})
    return sum(billed_seconds(scene["frames"], durations, fps=output["fps"], max_frames=output["max_frames"])
               for scene in job["board"]["scenes"] if not scene.get("motion_job"))


def prepare(job, folder, profile=None):
    plan = job.get("production_plan") or {}
    if plan.get("method") not in {"cloud", "hybrid"} or job.get("approved_storyboard_sha") is None:
        raise ValueError("Cloud motion requires an explicitly approved production route and budget.")
    missing = remaining_seconds(job)
    if job.get("cloud_motion_seconds", 0) + missing > plan["max_cloud_seconds"]:
        raise ValueError("Cloud video seconds budget exceeded before rendering.")
    identity = job.get("approved_motion") or job.get("motion_plan") or {}
    return job["id"], job, folder, identity.get("workflow_sha")


def _source(job, scene, index, previous, folder):
    from agentforge.features.film_studio import draft_pipeline as draft
    if previous is not None:
        clip = clip_path(previous)
        target = ensure_local_root(folder / (uuid4().hex + ".png"))
        try:
            render._run_process([render._ffmpeg(), "-nostdin", "-v", "error", "-xerror",
                "-i", str(clip), "-vf", "select=eq(n\\," + str(previous["frames"] - 1) + ")",
                "-frames:v", "1", "-an", str(target)], cwd=folder, timeout=90)
            image = target.read_bytes()
        finally:
            target.unlink(missing_ok=True)
        return image, {"previous_job": previous["motion_job"], "frame": previous["frames"]-1,
                       "image_sha": hashlib.sha256(image).hexdigest()}
    if job["production_plan"]["method"] == "hybrid":
        image = draft.image(job, index)
        return image, {"image_sha": hashlib.sha256(image).hexdigest()}
    return None, None


def _reserve(job, profile, seconds, save, *, retry=False):
    from agentforge.features.film_studio import draft_pipeline as draft
    plan = job["production_plan"]
    limit = model_hub.cloud_call_limit(profile, moving=True, planning=False, allow_motion=True,
        motion_ref=plan["motion_ref"], direct_cloud=plan["method"] == "cloud",
        validate=lambda revision, bindings: draft._check_studio_routing(job, revision, bindings))
    limit = min(limit, job.get("cloud_call_limit", limit))
    extra_seconds = 0 if retry else seconds
    if job.get("cloud_calls", 0) >= limit or job.get("cloud_motion_seconds", 0) + extra_seconds > plan["max_cloud_seconds"]:
        raise ValueError("Cloud video budget exhausted.")
    job.update(cloud_calls=job.get("cloud_calls", 0)+1, cloud_call_limit=limit,
               cloud_motion_seconds=job.get("cloud_motion_seconds", 0)+extra_seconds)
    save()


def _poll(row, profile):
    if row["endpoint"] not in {"image-to-video", "text-to-video"}:
        raise NeedsReconciliation("Unknown cloud motion endpoint.")
    if row["model"] != profile.get("model"):
        raise NeedsReconciliation("Cloud job does not match the assigned model.")
    try:
        return _transport(profile).poll_video(row, _key(profile))
    except ProviderRequestError as exc:
        raise NeedsReconciliation(str(exc) + "; poll the existing job, do not resubmit.") from None
    except ValueError:
        raise NeedsReconciliation("Cloud job status could not be verified.") from None


def _state(ident, state, *, provider_id=None, digest=None):
    with closing(_db(True)) as conn, conn:
        if provider_id is not None:
            # The same remote output must never be associated with two local shots.
            # Serialize this check with Owner-attested recovery.
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM jobs WHERE provider_id=? AND id<>?",
                            (provider_id, ident)).fetchone():
                raise ValueError("Provider job is already bound to another shot.")
            changed = conn.execute("UPDATE jobs SET state=?,provider_id=? "
                                   "WHERE id=? AND state='SUBMITTING' AND provider_id IS NULL",
                                   (state, provider_id, ident))
            if changed.rowcount != 1:
                raise ValueError("Cloud submission checkpoint changed.")
            return
        conn.execute("UPDATE jobs SET state=?,output_sha=COALESCE(?,output_sha) WHERE id=?",
                     (state, digest, ident))


def _shot_row(production, scene, profile):
    row = _row(scene["motion_job"])
    if (row["production"] != production or row["model"] != profile["model"]
            or row["seconds"] != _profile_seconds(scene["frames"], profile)):
        raise NeedsReconciliation("Cloud motion ledger does not match this approved shot.")
    return row


def run_shot(scene, index, prepared, profile, save, cancelled, *, dispatch_guard=nullcontext,
             retry_motion_job=None, previous_motion=None):
    production, job, folder, _ = prepared
    if retry_motion_job:
        if scene.get("motion_job") != retry_motion_job:
            raise ValueError("Cloud retry checkpoint changed.")
        row = _shot_row(production, scene, profile)
        retryable_motion_job(retry_motion_job)
        if row["state"] == "REJECTED":
            # Owner explicitly authorizes another attempt at the same rejected
            # request; keep original seconds reservation and lifetime call count.
            with closing(_db(True)) as conn, conn:
                changed = conn.execute("UPDATE submission_errors SET retry_at=? WHERE id=?",
                                       (time.time(), retry_motion_job))
                if changed.rowcount != 1:
                    raise NeedsReconciliation("Rejected request has no error receipt.")
        else:
            draft_continuity.clear_motion(scene)
            save()
    if scene.get("motion_sha"):
        _shot_row(production, scene, profile)
        clip_path(scene)
        return
    transport = _transport(profile)
    seconds = _profile_seconds(scene["frames"], profile)
    while True:
        existing = _shot_row(production, scene, profile) if scene.get("motion_job") else None
        if existing and existing["state"] != "REJECTED":
            break
        if existing:
            _wait_rejected(job, existing, save, cancelled)
        endpoint = "image-to-video" if previous_motion is not None or job["production_plan"]["method"] == "hybrid" else "text-to-video"
        if endpoint not in input_modes(profile):
            raise ValueError("Video adapter does not support the approved shot input mode.")
        image, source = _source(job, scene, index, previous_motion, folder)
        if (image is not None) != (endpoint == "image-to-video"):
            raise ValueError("Video shot source does not match the approved input mode.")
        prompt = (scene["image_prompt"] + ". " + draft_continuity.prompt(scene) +
                  "\nAudio direction: " + scene.get("audio", "") +
                  ". Keep the original actions; do not invent dialogue.")[:5000]
        limit = getattr(transport, "MAX_PROMPT_CHARS", None)
        if limit is not None:
            # Preserve the action instead of losing it behind a long image prompt.
            action = draft_continuity.prompt(scene, image_input=image is not None)
            if image is None:
                visual = scene["image_prompt"][:limit * 2 // 5]
                prompt = (visual + ". " + action)[:limit]
            else:
                prompt = action[:limit]
        body = transport.payload(profile["model"], prompt, seconds, image=image, audio=native_audio(profile))
        request_sha = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        ident = existing["id"] if existing else uuid4().hex
        key = _key(profile)
        with dispatch_guard():
            ops_control.require_active()
            if cancelled():
                from agentforge.features.film_studio.draft_pipeline import DraftCancelled
                raise DraftCancelled
            if existing:
                if existing["request_sha"] != request_sha or existing["endpoint"] != endpoint:
                    raise NeedsReconciliation("Cloud retry input changed.")
                _reserve(job, profile, seconds, save, retry=True)
                _rearm(ident, request_sha)
            else:
                _reserve(job, profile, seconds, save)
                scene["motion_job"] = ident
                if source:
                    scene["motion_source"] = source
                save()
                with closing(_db(True)) as conn, conn:
                    conn.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                                 (ident, production, endpoint, profile["model"], seconds, request_sha, "SUBMITTING", None, None))
            try:
                remote = transport.submit_video(body, key, endpoint)
                _state(ident, "SUBMITTED", provider_id=remote)
            except ProviderRequestError as exc:
                if not exc.rejected:
                    raise NeedsReconciliation(str(exc) + "; outcome unknown, do not resubmit.") from None
                reject_submission(ident, exc, automatic=True)
                continue
            except (ValueError, OSError, TypeError, sqlite3.Error):
                raise NeedsReconciliation("Cloud POST outcome uncertain; inspect provider dashboard, never resubmit.") from None
        break
    row = _shot_row(production, scene, profile)
    if row["state"] == "VERIFIED":
        scene["motion_sha"] = row["output_sha"]
        clip_path(scene)
        save()
        return
    if row["state"] == "FAILED":
        raise ValueError("Cloud motion failed; approve a new storyboard to regenerate.")
    if row["state"] != "SUBMITTED":
        raise NeedsReconciliation("Cloud motion submission has no confirmed provider ID.")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if cancelled():
            raise NeedsReconciliation("Cloud job may still be running; reconcile before cancellation.")
        try:
            response = _poll(row, profile)
        except NeedsReconciliation:
            raise
        except (ValueError, OSError, TypeError):
            raise NeedsReconciliation("Cloud status unavailable; resume this job, do not resubmit.") from None
        if response["status"] == "failed":
            _state(row["id"], "FAILED")
            raise ValueError("Cloud provider reported failure.")
        if response["status"] == "completed":
            output = _path(row)
            temp = ensure_local_root(folder / (uuid4().hex + ".part.mp4"))
            try:
                if output.exists():
                    # Recover an interrupted finalization only after technical re-verification.
                    digest = verify_download(output, seconds, profile)
                else:
                    transport.download_video(response, temp, seconds)
                    digest = verify_download(temp, seconds, profile)
                    temp.replace(output)
                _state(row["id"], "VERIFIED", digest=digest)
                scene["motion_sha"] = digest
                save()
                return
            except (ValueError, OSError, KeyError, TypeError):
                raise NeedsReconciliation("Cloud output could not be verified; resume the existing job.") from None
            finally:
                temp.unlink(missing_ok=True)
        time.sleep(5)
    raise NeedsReconciliation("Cloud job still pending; resume the existing job.")


def reconcile_cancelled(job):
    from agentforge.features.film_studio import draft_pipeline as draft
    _, bindings, _ = draft._studio_bindings(job)
    profile = bindings["film.motion"]
    try:
        rows = [_shot_row(job["id"], scene, profile) for scene in job["board"]["scenes"]
                if scene.get("motion_job")]
        owned = {row["id"] for row in rows}
        if any(row["id"] not in owned for row in reconciliation_jobs(job)):
            return False
        if any(row["state"] not in {"VERIFIED", "FAILED", "REJECTED", "CANCELLED_REMOTE_TERMINAL", "SUBMITTED"}
               for row in rows):
            return False
        for row in rows:
            if row["state"] != "SUBMITTED":
                continue
            response = _poll(row, profile)
            if response["status"] not in {"completed", "failed"}:
                return False
            _state(row["id"], "CANCELLED_REMOTE_TERMINAL")
    except (ValueError, OSError, TypeError, KeyError):
        return False
    return True


def retryable_motion_job(ident):
    if _row(ident)["state"] not in {"FAILED", "REJECTED"}:
        raise ValueError("Only explicitly confirmed terminal provider failures can be retried.")
