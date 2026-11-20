"""Local-first ComfyUI image jobs for Film Studio source assets.

GPU submission requires Owner approval; ambiguous jobs never retry.
"""
import hashlib
import io
import json
import os
import re
import sqlite3
import urllib.parse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from agentforge import ops_control
from agentforge.paths import REPOSITORY_ROOT, ensure_local_root
from agentforge.features.media import comfy_image

ROOT = REPOSITORY_ROOT
DB = ROOT / "data" / "company" / "visual_jobs_v3.sqlite3"
OUTPUTS = ROOT / "workspace" / "visuals"
ID = re.compile(r"[a-f0-9]{32}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
PURPOSES = {"video", "image"}
MAX_JOBS = 5
MAX_IMAGE = comfy_image.MAX_IMAGE


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid visual job ID")
    return value


def _db(path=None, *, create=False):
    target = Path(path) if path is not None else DB
    ensure_local_root(target)
    if not create and not target.is_file():
        return None
    if create:
        target.parent.mkdir(parents=True, exist_ok=True)
        ensure_local_root(target.parent)
    db = sqlite3.connect(target, timeout=20)
    db.row_factory = sqlite3.Row
    if create:
        db.execute("""CREATE TABLE IF NOT EXISTS visual_jobs (
            job_id TEXT PRIMARY KEY, package_id TEXT NOT NULL,
            purpose TEXT NOT NULL, scene_index INTEGER NOT NULL,
            prompt TEXT NOT NULL, checkpoint TEXT NOT NULL,
            provider_id TEXT, status TEXT NOT NULL,
            asset_sha TEXT, source_sha TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS visual_runtime (
            job_id TEXT PRIMARY KEY REFERENCES visual_jobs(job_id),
            metadata TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0)""")
        db.commit()
    return db


def runtime_details(job_id, *, db_path=None):
    db = _db(db_path)
    if db is None:
        return None
    with closing(db):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='visual_runtime'").fetchone():
            return None
        row = db.execute("SELECT * FROM visual_runtime WHERE job_id=?", (_id(job_id),)).fetchone()
    return {**json.loads(row["metadata"]), "approved": bool(row["reviewed"])} if row else None


def approve(job_id, sha256, *, db_path=None):
    row = _row(job_id, db_path=db_path)
    if row["asset_sha"] != sha256 or row["status"] != "ASSET_READY":
        raise PermissionError("Visual asset changed")
    image_for_job(job_id, db_path=db_path)
    with closing(_db(db_path, create=True)) as db, db:
        if db.execute("UPDATE visual_runtime SET reviewed=1 WHERE job_id=?", (job_id,)).rowcount != 1:
            raise ValueError("No FLUX visual to approve")
    return {"job_id": job_id, "approved": True}


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
    # The Owner's subject and scene define the style; never impose commerce imagery.
    prefix = "Original AI film frame. "
    suffix = (" No embedded text, logos or watermark. "
              "Keep the main subject and composition visible.")
    shot = f" Scene {index + 1}: "
    scene_budget = min(210, 450 - len(prefix + "Subject: " + shot + "." + suffix) - 40)
    scene_text = scene.strip()[:scene_budget]
    fixed = prefix + "Subject: " + shot + scene_text + "." + suffix
    topic_budget = 450 - len(fixed)
    if topic_budget < 1:
        raise ValueError("Visual prompt cannot fit the scene brief")
    value = (prefix + "Subject: " + topic.strip()[:topic_budget]
             + shot + scene_text + "." + suffix)
    if len(value) > 450:
        raise ValueError("Visual prompt exceeds limit")
    return value


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
    if not isinstance(checkpoint, str) or not comfy_image.CHECKPOINT.fullmatch(checkpoint):
        raise ValueError("Invalid image checkpoint")
    ready = comfy_image.health(opener=opener)
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
        raw = comfy_image._request(
            "/prompt", payload={"prompt": comfy_image._workflow(ident, prompt, checkpoint)},
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
    raw = comfy_image._request("/history/" + row["provider_id"],
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
            or not comfy_image.IMAGE_FILE.fullmatch(item["filename"])
            or not item["filename"].startswith("af_" + job_id + "_")):
        raise PermissionError("Untrusted ComfyUI output image")
    with closing(_db(db_path, create=True)) as db, db:
        changed = db.execute("UPDATE visual_jobs SET status='COLLECTING',updated_at=? "
                             "WHERE job_id=? AND status='SUBMITTED'", (_now(), job_id))
        if changed.rowcount != 1:
            raise PermissionError("Visual import already claimed")
    query = urllib.parse.urlencode({"filename": item["filename"],
                                    "subfolder": "", "type": "output"})
    contents = comfy_image._request("/view?" + query, max_bytes=MAX_IMAGE,
                                     timeout=15, opener=opener)
    from PIL import Image
    with Image.open(io.BytesIO(contents)) as decoded:
        if (decoded.format != "PNG" or not 256 <= decoded.width <= 2048
                or not 256 <= decoded.height <= 2048):
            raise ValueError("Generated AI image has invalid PNG dimensions")
        decoded.verify()
    output_root = Path(output_root) if output_root is not None else OUTPUTS
    target = output_root / (job_id + ".png")
    ensure_local_root(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    ensure_local_root(target.parent)
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


@contextmanager
def open_image_for_job(job_id, *, db_path=None, output_root=None):
    row = _row(job_id, db_path=db_path)
    if row["status"] != "ASSET_READY" or not row["asset_sha"]:
        raise PermissionError("AI visual image is not ready")
    runtime = runtime_details(job_id, db_path=db_path)
    if runtime is not None:
        from agentforge.features.media.flux_runtime import output_directory
        root = output_directory(runtime["output_dir"])
    else:
        root = Path(output_root) if output_root is not None else OUTPUTS
    path = root / (_id(job_id) + ".png")
    ensure_local_root(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_IMAGE:
        raise PermissionError("Missing/oversized visual image")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != row["asset_sha"]:
            raise PermissionError("AI image hash changed")
        stream.seek(0)
        yield stream, row["asset_sha"]


def image_for_job(job_id, *, db_path=None, output_root=None):
    with open_image_for_job(job_id, db_path=db_path, output_root=output_root) as (stream, _):
        data = stream.read(MAX_IMAGE + 1)
        if len(data) > MAX_IMAGE:
            raise PermissionError("Oversized visual image")
        return data, "image/png"


def report(*, db_path=None):
    db = _db(db_path)
    if db is None:
        return {"jobs": []}
    with closing(db):
        rows = [dict(x) for x in db.execute(
            "SELECT job_id,package_id,purpose,scene_index,status,asset_sha,source_sha,checkpoint,"
            "created_at,updated_at FROM visual_jobs ORDER BY created_at DESC LIMIT 80")]
        runtime_rows = {}
        if rows and db.execute("SELECT 1 FROM sqlite_master WHERE name='visual_runtime'").fetchone():
            placeholders = ",".join("?" for _ in rows)
            runtime_rows = {row["job_id"]: row for row in db.execute(
                f"SELECT * FROM visual_runtime WHERE job_id IN ({placeholders})",
                [row["job_id"] for row in rows])}
    for row in rows:
        stored = runtime_rows.get(row["job_id"])
        if stored:
            runtime = json.loads(stored["metadata"])
            row.update({key: runtime[key] for key in (
                "prompt", "seed", "width", "height", "steps", "scene", "workflow_sha256",
                "duration_seconds")})
            row["approved"] = bool(stored["reviewed"])
            row["probe"] = runtime.get("probe", False)
    return {"jobs": rows, "no_auto_publication": True, "auto_retry": False}
