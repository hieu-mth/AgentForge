"""Local-first reusable ComfyUI visual jobs for video, images and web assets.

Uses the trusted Image Studio ComfyUI workflow, without requiring an applied
website. Each GPU submission is explicitly authorized; no automatic retry.
"""
import hashlib
import io
import json
import os
import re
import sqlite3
import urllib.parse
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from agentforge import ops_control, product_builder
from agentforge.features.websites import image_studio

ROOT = product_builder.ROOT
DB = ROOT / "data" / "company" / "visual_jobs_v3.sqlite3"
OUTPUTS = ROOT / "workspace" / "visuals"
ID = re.compile(r"[a-f0-9]{32}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
PURPOSES = {"video", "image", "website"}
MAX_JOBS = 5
MAX_IMAGE = image_studio.MAX_IMAGE


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid visual job ID")
    return value


def _db(path=None, *, create=False):
    target = Path(path) if path is not None else DB
    product_builder._check_path_chain(target)
    if not create and not target.is_file():
        return None
    if create:
        target.parent.mkdir(parents=True, exist_ok=True)
        product_builder._check_path_chain(target.parent)
    db = sqlite3.connect(target, timeout=20)
    db.row_factory = sqlite3.Row
    if create:
        db.execute("""CREATE TABLE IF NOT EXISTS visual_jobs (
            job_id TEXT PRIMARY KEY, package_id TEXT NOT NULL,
            purpose TEXT NOT NULL, scene_index INTEGER NOT NULL,
            prompt TEXT NOT NULL, checkpoint TEXT NOT NULL,
            provider_id TEXT, status TEXT NOT NULL,
            asset_sha TEXT, source_sha TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        db.commit()
    return db


def _row(job_id, *, db_path=None):
    ident = _id(job_id)
    db = _db(db_path)
    if db is None:
        raise KeyError("Visual job not found")
    with closing(db):
        row = db.execute("SELECT * FROM visual_jobs WHERE job_id=?", (ident,)).fetchone()
    if row is None:
        raise KeyError("Visual job not found")
    return dict(row)


def _prompt(topic, scene, index, purpose):
    if not isinstance(topic, str) or not topic.strip() or len(topic) > 450:
        raise ValueError("Visual topic must be 1-450 characters")
    if not isinstance(scene, str) or not scene.strip() or len(scene) > 300:
        raise ValueError("Visual scene must be 1-300 characters")
    # Subject is grounded in the user's brief. The image model is responsible
    # for pixels; no unverified brand/logo or health/price claims.
    value = (
        "Commercial editorial photography, realistic product and environment, "
        "excellent lighting and composition. "
        f"Product/subject: {topic.strip()}. Shot {index+1}: {scene.strip()}. "
        "No text, logos, watermark, price, medical claims or UI. "
        "Full scene, clearly visible subject."
    )
    return value[:450]


def submit(purpose, topic, scenes, checkpoint, *, confirm_generation=False,
           source_sha=None,
           db_path=None, opener=None):
    if confirm_generation is not True:
        raise PermissionError("Owner must authorize image GPU calls")
    ops_control.require_active()
    if source_sha is not None and (not isinstance(source_sha, str) or not SHA.fullmatch(source_sha)):
        raise ValueError("Invalid source SHA")
    if purpose not in PURPOSES:
        raise ValueError("Unknown visual purpose")
    if (not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_JOBS
            or any(not isinstance(x, str) for x in scenes)):
        raise ValueError("Visual batch must contain 1-5 shots")
    prompts = [_prompt(topic, scene, i, purpose) for i, scene in enumerate(scenes)]
    if not isinstance(checkpoint, str) or not image_studio.CHECKPOINT.fullmatch(checkpoint):
        raise ValueError("Invalid image checkpoint")
    ready = image_studio.health(opener=opener)
    if ready["status"] != "READY" or checkpoint not in ready["checkpoints"]:
        raise PermissionError("Configured local ComfyUI checkpoint unavailable")
    package_id = uuid4().hex
    planned = []
    # Persist one job *before* each network call. If dispatch is uncertain,
    # never auto resend; any earlier accepted jobs stay visible to the Owner.
    for index, prompt in enumerate(prompts):
        ident = uuid4().hex
        with closing(_db(db_path, create=True)) as db, db:
            db.execute("INSERT INTO visual_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (ident, package_id, purpose, index, prompt, checkpoint,
                        None, "SUBMITTING", None, source_sha, _now(), _now()))
        planned.append(ident)
        raw = image_studio._request(
            "/prompt", payload={"prompt": image_studio._workflow(ident, prompt, checkpoint)},
            max_bytes=65536, timeout=12, opener=opener)
        data = json.loads(raw)
        provider_id = str(UUID(data["prompt_id"]))
        with closing(_db(db_path, create=True)) as db, db:
            updated = db.execute(
                "UPDATE visual_jobs SET provider_id=?,status='SUBMITTED',updated_at=? "
                "WHERE job_id=? AND status='SUBMITTING'",
                (provider_id, _now(), ident))
            if updated.rowcount != 1:
                raise RuntimeError("Visual job dispatch ledger changed")
    return {"package_id": package_id, "purpose": purpose,
            "job_ids": planned, "status": "SUBMITTED",
            "gpu_jobs_submitted": len(planned), "auto_retry": False}


def collect(job_id, *, confirm_import=False, db_path=None, output_root=None, opener=None):
    if confirm_import is not True:
        raise PermissionError("Owner must authorize importing local AI image")
    ops_control.require_active()
    row = _row(job_id, db_path=db_path)
    if row["status"] == "ASSET_READY":
        return {"job_id": job_id, "status": "ASSET_READY", "sha256": row["asset_sha"]}
    if row["status"] != "SUBMITTED" or not row["provider_id"]:
        raise PermissionError("No submitted visual image to import")
    raw = image_studio._request("/history/" + row["provider_id"],
                                max_bytes=131072, timeout=5, opener=opener)
    history = json.loads(raw).get(row["provider_id"])
    if history is None:
        return {"job_id": job_id, "status": "PROCESSING"}
    if (not isinstance(history, dict)
            or not isinstance(history.get("status"), dict)
            or history["status"].get("status_str") != "success"
            or history["status"].get("completed") is not True):
        raise PermissionError("AI image generation failed or is incomplete")
    images = history.get("outputs", {}).get("7", {}).get("images", [])
    if (not isinstance(images, list) or len(images) != 1
            or not isinstance(images[0], dict)):
        raise ValueError("Expected exactly one ComfyUI image")
    item = images[0]
    if (item.get("subfolder") != "" or item.get("type") != "output"
            or not isinstance(item.get("filename"), str)
            or not image_studio.IMAGE_FILE.fullmatch(item["filename"])
            or not item["filename"].startswith("af_" + job_id + "_")):
        raise PermissionError("Untrusted ComfyUI output image")
    with closing(_db(db_path, create=True)) as db, db:
        changed = db.execute("UPDATE visual_jobs SET status='COLLECTING',updated_at=? "
                             "WHERE job_id=? AND status='SUBMITTED'", (_now(), job_id))
        if changed.rowcount != 1:
            raise PermissionError("Visual import already claimed")
    query = urllib.parse.urlencode({"filename": item["filename"],
                                    "subfolder": "", "type": "output"})
    contents = image_studio._request("/view?" + query, max_bytes=MAX_IMAGE,
                                     timeout=15, opener=opener)
    from PIL import Image
    with Image.open(io.BytesIO(contents)) as decoded:
        if (decoded.format != "PNG" or not 256 <= decoded.width <= 2048
                or not 256 <= decoded.height <= 2048):
            raise ValueError("Generated AI image has invalid PNG dimensions")
        decoded.verify()
    output_root = Path(output_root) if output_root is not None else OUTPUTS
    target = output_root / (job_id + ".png")
    product_builder._check_path_chain(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    product_builder._check_path_chain(target.parent)
    with target.open("xb") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())
    digest = hashlib.sha256(contents).hexdigest()
    with closing(_db(db_path, create=True)) as db, db:
        changed = db.execute(
            "UPDATE visual_jobs SET status='ASSET_READY',asset_sha=?,updated_at=? "
            "WHERE job_id=? AND status='COLLECTING'", (digest, _now(), job_id))
        if changed.rowcount != 1:
            raise RuntimeError("Visual image receipt changed")
    return {"job_id": job_id, "status": "ASSET_READY", "sha256": digest,
            "owner_review_required": True}


def image_for_job(job_id, *, db_path=None, output_root=None):
    row = _row(job_id, db_path=db_path)
    if row["status"] != "ASSET_READY" or not row["asset_sha"]:
        raise PermissionError("AI visual image is not ready")
    root = Path(output_root) if output_root is not None else OUTPUTS
    path = root / (_id(job_id) + ".png")
    product_builder._check_path_chain(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_IMAGE:
        raise PermissionError("Missing/oversized visual image")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != row["asset_sha"]:
        raise PermissionError("AI image hash changed")
    return data, "image/png"


def website_subject(slug):
    """Get grounded visual subject from an already applied local static site."""
    from html.parser import HTMLParser
    from agentforge import web_assets
    project = web_assets._project(slug)
    source = project / "index.html"
    product_builder._check_path_chain(source)
    if not 0 < source.stat().st_size <= 600_000:
        raise ValueError("Website source is missing or oversized")
    class Content(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []
            self.include = False
            self.skip = 0
        def handle_starttag(self, tag, attrs):
            if tag in {"script", "style"}:
                self.skip += 1
            if tag in {"title", "h1", "h2", "p"} and self.skip == 0:
                self.include = True
        def handle_endtag(self, tag):
            if tag in {"script", "style"} and self.skip:
                self.skip -= 1
            if tag in {"title", "h1", "h2", "p"}:
                self.include = False
        def handle_data(self, data):
            if self.include and not self.skip and data.strip():
                self.parts.append(data.strip())
    parsed = Content()
    parsed.feed(source.read_text(encoding="utf-8"))
    subject = " ".join(parsed.parts)[:300].strip()
    if len(subject) < 8:
        raise ValueError("Website has insufficient content for an AI image prompt")
    return subject


def attach_website(job_id, slug, image_sha, html_sha, *,
                   confirm_attach=False, db_path=None):
    """Bridge a reviewed standalone GPU image into existing SHA-gated web attach.

    Uses the original Image Studio website-attach quality gate/backups rather
    than editing HTML directly here. No external deploy, model, or subprocess.
    """
    if confirm_attach is not True:
        raise PermissionError("Explicit Owner consent to attach visual required")
    ops_control.require_active()
    from agentforge import web_assets
    row = _row(job_id, db_path=db_path)
    if (row["status"] != "ASSET_READY" or row["purpose"] != "website"
            or not isinstance(image_sha, str) or image_sha != row["asset_sha"]
            or not isinstance(html_sha, str) or not SHA.fullmatch(html_sha)):
        raise PermissionError("Incorrect website visual receipt or SHA")
    contents, mime = image_for_job(job_id, db_path=db_path)
    if mime != "image/png":
        raise ValueError("Only reviewed PNG may be attached to static website")
    project = web_assets._project(slug)
    original = project / "index.html"
    product_builder._check_path_chain(original)
    existing = original.read_bytes()
    if hashlib.sha256(existing).hexdigest() != html_sha:
        raise PermissionError("Website source changed since Owner review")
    if b'af-ai-hero-style' in existing:
        raise PermissionError("Website already contains an AI hero; review manually")
    images = web_assets.list_images(slug)
    if (len(images) >= web_assets.MAX_IMAGES
            or sum(x["bytes"] for x in images) + len(contents) > web_assets.MAX_ALL_BYTES):
        raise ValueError("Website image asset budget reached")
    name = "af-ai-" + job_id + ".png"
    target = web_assets._path(slug, name)
    # Retry an uncertain promotion must never overwrite an existing image.
    if target.exists():
        raise FileExistsError("Image was already promoted; inspect existing job")
    with closing(image_studio._connect(create=True)) as db:
        if db.execute("SELECT 1 FROM jobs WHERE job_id=?", (job_id,)).fetchone():
            raise FileExistsError("Image already registered for website")
    target.parent.mkdir(parents=True, exist_ok=True)
    product_builder._check_path_chain(target.parent)
    with target.open("xb") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())
    # Persist a compatible Image Studio receipt. If attaching fails, it is
    # recoverable from Projects & Files without re-generating the AI image.
    with closing(image_studio._connect(create=True)) as db, db:
        db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, slug, "ASSET_READY", hashlib.sha256(row["prompt"].encode()).hexdigest(),
                    row["checkpoint"], None, name, image_sha, None, _now(), _now()))
    result = image_studio.attach(job_id, image_sha, html_sha,
                                 confirm_attach=True)
    return {**result, "source": "auto_visual_v3"}


def report(*, db_path=None):
    db = _db(db_path)
    if db is None:
        return {"jobs": []}
    with closing(db):
        rows = [dict(x) for x in db.execute(
            "SELECT job_id,package_id,purpose,scene_index,status,asset_sha,source_sha,checkpoint,"
            "created_at,updated_at FROM visual_jobs ORDER BY created_at DESC LIMIT 80")]
    return {"jobs": rows, "no_auto_publication": True, "auto_retry": False}
