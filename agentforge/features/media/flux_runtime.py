"""Execute the bound Model Hub image capability through the visual job ledger."""
import hashlib
import io
import json
import os
import re
import secrets
import time
from contextlib import closing
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

from agentforge import ops_control
from agentforge.ai import model_hub
from agentforge.features.media import flux_workflow, visual_jobs
from agentforge.integrations import comfyui
from agentforge.paths import WORKSPACE_DIR, ensure_local_root


class JobError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(status)


def output_directory(folder):
    if not isinstance(folder, str) or not flux_workflow.FOLDER.fullmatch(folder):
        raise ValueError("Invalid workspace output folder")
    return ensure_local_root(WORKSPACE_DIR / folder)


def _json(path, *, port, body=None, timeout=5):
    return json.loads(comfyui.request_image_bytes(
        path, body=body, port=port, timeout=timeout))


def readiness(config, port):
    graph = config["workflow"]
    try:
        stats = _json("/system_stats", port=port)
        if not any(isinstance(device, dict) and device.get("type") == "cuda"
                   for device in stats["devices"]):
            return "GPU_UNAVAILABLE"
        for node_id, fields in (("38", ("unet_name",)), ("39", ("clip_name1", "clip_name2")),
                                ("40", ("vae_name",))):
            node = graph[node_id]
            kind = node["class_type"]
            model_fields = _json("/object_info/" + kind, port=port)[kind]["input"]["required"]
            for field in fields:
                if node["inputs"][field] not in model_fields[field][0]:
                    return "MODEL_UNAVAILABLE"
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return "COMFYUI_UNAVAILABLE"
    return "READY"


def _output(history, ident):
    if history is None:
        return None
    status = history.get("status", {})
    messages = status.get("messages", [])
    if any(isinstance(row, list) and row and row[0] == "execution_interrupted"
           for row in messages):
        raise JobError("CANCELLED")
    if status.get("status_str") != "success" or status.get("completed") is not True:
        raise JobError("EXECUTION_FAILED")
    images = history.get("outputs", {}).get("9", {}).get("images", [])
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
        raise JobError("OUTPUT_MISSING")
    image = images[0]
    filename = image.get("filename")
    if (image.get("subfolder") != "" or image.get("type") != "output"
            or not isinstance(filename, str) or not comfyui.IMAGE_NAME.fullmatch(filename)
            or not filename.startswith("af_" + ident + "_")):
        raise JobError("OUTPUT_INVALID")
    return filename


def _collect(provider_id, ident, port, config, metadata):
    deadline = time.monotonic() + config["timeout_seconds"]
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            history = _json("/history/" + provider_id, port=port, timeout=min(remaining, 5))
        except (OSError, RuntimeError):
            history = {}
        filename = _output(history.get(provider_id), ident)
        if filename is not None:
            break
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    else:
        raise JobError("TIMED_OUT")
    query = urlencode({"filename": filename, "subfolder": "", "type": "output"})
    contents = comfyui.request_image_bytes("/view?" + query, port=port, timeout=15,
                                         max_response_bytes=visual_jobs.MAX_IMAGE)
    from PIL import Image
    with Image.open(io.BytesIO(contents), formats=["PNG"]) as image:
        if image.size != (metadata["width"], metadata["height"]):
            raise JobError("OUTPUT_INVALID")
        image.verify()
    with Image.open(io.BytesIO(contents), formats=["PNG"]) as image:
        image.load()
    return contents


def generate(prompt, *, width=None, height=None, steps=None, seed=None, scene=None,
             automated=False, hub_db=None, db_path=None):
    """Entry point for Studio and trusted Orchestrator callers."""
    ops_control.require_active()
    revision, profile = model_hub.image_runtime(automated=automated, db_path=hub_db)
    config = flux_workflow.validate(profile["flux"], profile["model"], profile["base_url"])
    port = urlsplit(profile["base_url"]).port
    if scene is not None and (not isinstance(scene, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9_/-]{0,119}", scene)):
        raise ValueError("Invalid scene reference")
    graph = config["workflow"]
    width = graph["27"]["inputs"]["width"] if width is None else width
    height = graph["27"]["inputs"]["height"] if height is None else height
    steps = graph["31"]["inputs"]["steps"] if steps is None else steps
    seed = secrets.randbelow(2**53) if seed is None else seed
    ident = uuid4().hex
    bound = flux_workflow.bind(config, ident, prompt, width, height, seed, steps)
    directory = output_directory(config["output_dir"])
    directory.mkdir(parents=True, exist_ok=True)
    target = ensure_local_root(directory / (ident + ".png"))
    from PIL import Image  # Fail before dispatch when the media extra is absent.
    ready = readiness(config, port)
    if ready != "READY":
        raise ValueError(ready)
    metadata = {
        "prompt": prompt.strip(), "seed": seed, "width": width, "height": height,
        "steps": steps, "scene": scene, "model": profile["model"], "profile_id": profile["id"],
        "model_hub_revision": revision, "workflow": bound,
        "workflow_sha256": hashlib.sha256(json.dumps(bound, sort_keys=True).encode()).hexdigest(),
        "output_dir": config["output_dir"], "duration_seconds": None,
    }
    def snapshot():
        return json.dumps(metadata, ensure_ascii=False, allow_nan=False)

    with closing(visual_jobs._db(db_path, create=True)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("""SELECT 1 FROM visual_jobs WHERE status IN
                      ('SUBMITTING','SUBMITTED','COLLECTING') LIMIT 1""").fetchone():
            raise PermissionError("An AgentForge visual job is already outstanding")
        queue = _json("/queue", port=port)
        if queue["queue_running"] or queue["queue_pending"]:
            raise PermissionError("ComfyUI GPU queue is busy")
        now = visual_jobs._now()
        db.execute("INSERT INTO visual_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
            ident, ident, "video" if scene else "image", 0, prompt.strip(), profile["model"],
            None, "SUBMITTING", None, None, now, now))
        db.execute("INSERT INTO visual_runtime(job_id,metadata) VALUES(?,?)", (ident, snapshot()))
    started = time.monotonic()
    provider_id = None
    digest = None
    created = False
    status = "SUBMIT_UNCERTAIN"
    try:
        response = _json("/prompt", body={"prompt": bound}, port=port, timeout=12)
        provider_id = str(UUID(response["prompt_id"]))
        if response.get("node_errors"):
            raise JobError("EXECUTION_FAILED")
        with closing(visual_jobs._db(db_path, create=True)) as db, db:
            db.execute("UPDATE visual_jobs SET provider_id=?,status='SUBMITTED',updated_at=? WHERE job_id=?",
                       (provider_id, visual_jobs._now(), ident))
        status = "OUTPUT_INVALID"
        contents = _collect(provider_id, ident, port, config, metadata)
        digest = hashlib.sha256(contents).hexdigest()
        with ensure_local_root(target).open("xb") as stream:
            created = True
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        status = "ASSET_READY"
    except JobError as exc:
        status = exc.status
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError):
        pass
    finally:
        metadata["duration_seconds"] = round(time.monotonic() - started, 3)
        try:
            with closing(visual_jobs._db(db_path, create=True)) as db, db:
                db.execute("""UPDATE visual_jobs SET status=?,asset_sha=?,updated_at=? WHERE job_id=?""",
                           (status, digest if status == "ASSET_READY" else None, visual_jobs._now(), ident))
                db.execute("UPDATE visual_runtime SET metadata=? WHERE job_id=?", (snapshot(), ident))
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise
        if created and status != "ASSET_READY":
            target.unlink(missing_ok=True)
    return {"job_id": ident, "provider_id": provider_id, "status": status,
            "sha256": digest if status == "ASSET_READY" else None,
            "duration_seconds": metadata["duration_seconds"]}
