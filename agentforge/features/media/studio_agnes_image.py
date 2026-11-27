"""Agnes image generation using the shared durable visual asset ledger."""
import hashlib
import json
import time
from contextlib import closing
from uuid import uuid4

from agentforge import ops_control
from agentforge.features.film_studio import studio_agnes
from agentforge.features.film_studio.draft_resources import NeedsReconciliation
from agentforge.features.media import visual_jobs
from agentforge.paths import ensure_local_root

ADAPTER_ID = "agnes-image-flash"


def supports(profile):
    return profile.get("provider") == "agnes" and profile.get("model") == studio_agnes.IMAGE_MODEL


def output_limits(profile):
    return {"format": "png", "batch": 1, "size": "1K", "ratios": ["16:9", "9:16", "1:1"]}


def workflow_sha(profile):
    return None


def registry_readiness(profile):
    return "CLOUD_IMAGE_NOT_PROBED"


def preflight(profile, *, include_profiles=False):
    if not supports(profile):
        raise ValueError("Unsupported Agnes image model.")
    studio_agnes.key(profile)


def release_idle_models(profile):
    return False


def generate(profile, request):
    preflight(profile)
    token = studio_agnes.key(profile)
    body = studio_agnes.image_payload(request.prompt, request.ratio)
    ident = visual_jobs._id(request.job_id)
    target = ensure_local_root(visual_jobs.OUTPUTS / (ident + ".png"))
    staged = ensure_local_root(target.with_name(uuid4().hex + ".tmp"))
    started = time.monotonic()
    with request.dispatch_guard():
        ops_control.require_active()
        target.parent.mkdir(parents=True, exist_ok=True)
        with closing(visual_jobs._db(create=True)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM visual_jobs WHERE job_id=?", (ident,)).fetchone():
                raise NeedsReconciliation("Image submission already reserved; do not send again.")
            now = visual_jobs._now()
            db.execute("INSERT INTO visual_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (ident, ident, "video" if request.scene else "image", 0, request.prompt,
                        profile["model"], None, "SUBMITTING", None, None, now, now))
            metadata = {"provider": "agnes", "probe": not bool(request.scene),
                        "profile_sha": hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest(),
                        "scene": request.scene, "prompt": request.prompt}
            db.execute("INSERT INTO visual_runtime(job_id,metadata) VALUES(?,?)", (ident, json.dumps(metadata)))
        try:
            data = studio_agnes.image_bytes(body, token, visual_jobs.MAX_IMAGE)
            digest = hashlib.sha256(data).hexdigest()
            with staged.open("xb") as stream:
                stream.write(data)
            staged.replace(target)
            with closing(visual_jobs._db(create=True)) as db, db:
                db.execute("UPDATE visual_jobs SET status='ASSET_READY',asset_sha=?,updated_at=? WHERE job_id=?",
                           (digest, visual_jobs._now(), ident))
                metadata["duration_seconds"] = round(time.monotonic() - started, 3)
                db.execute("UPDATE visual_runtime SET metadata=? WHERE job_id=?", (json.dumps(metadata), ident))
        except studio_agnes.AgnesHTTPError as exc:
            metadata["error"] = str(exc)
            with closing(visual_jobs._db(create=True)) as db, db:
                db.execute("UPDATE visual_jobs SET status=?,updated_at=? WHERE job_id=?",
                           ("REJECTED" if exc.rejected else "SUBMIT_UNCERTAIN", visual_jobs._now(), ident))
                db.execute("UPDATE visual_runtime SET metadata=? WHERE job_id=?", (json.dumps(metadata), ident))
            if exc.rejected:
                raise
            raise NeedsReconciliation(str(exc) + "; image outcome uncertain.") from None
        except Exception:
            with closing(visual_jobs._db(create=True)) as db, db:
                db.execute("UPDATE visual_jobs SET status='SUBMIT_UNCERTAIN',updated_at=? WHERE job_id=?",
                           (visual_jobs._now(), ident))
            raise NeedsReconciliation("Agnes image outcome uncertain; do not resubmit.") from None
        finally:
            staged.unlink(missing_ok=True)
    return {"job_id": ident, "status": "ASSET_READY", "sha256": digest,
            "duration_seconds": round(time.monotonic() - started, 3),
            "preview_url": "/api/visuals/" + ident + "/preview"}
