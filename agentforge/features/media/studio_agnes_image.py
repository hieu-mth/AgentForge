"""Agnes image generation using the shared durable visual asset ledger."""
import hashlib
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


def output_limits():
    return {"format": "png", "batch": 1, "size": "1K", "ratios": ["16:9", "9:16", "1:1"]}


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
        try:
            data = studio_agnes.image_bytes(body, token, visual_jobs.MAX_IMAGE)
            digest = hashlib.sha256(data).hexdigest()
            with staged.open("xb") as stream:
                stream.write(data)
            staged.replace(target)
            with closing(visual_jobs._db(create=True)) as db, db:
                db.execute("UPDATE visual_jobs SET status='ASSET_READY',asset_sha=?,updated_at=? WHERE job_id=?",
                           (digest, visual_jobs._now(), ident))
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
