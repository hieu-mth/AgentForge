"""Execute the bound Model Hub image capability through the visual job ledger."""
import hashlib
import http.client
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
from agentforge.features.film_studio import draft_resources
from agentforge.features.media import flux_workflow, visual_jobs
from agentforge.integrations import comfy_service, comfyui
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


def readiness(config, port, *, inspect_all_nodes=False):
    graph = config["workflow"]
    ids = flux_workflow.node_ids(graph)
    try:
        stats = _json("/system_stats", port=port, timeout=5)
        if not any(isinstance(device, dict) and device.get("type") == "cuda"
                   for device in stats["devices"]):
            return "GPU_UNAVAILABLE"
        loaders = {"38": ("unet_name",), "39": ("clip_name1", "clip_name2"), "40": ("vae_name",)}
        for node_id in ids if inspect_all_nodes else loaders:
            fields = loaders.get(node_id, ())
            node = graph[ids[node_id]]
            kind = node["class_type"]
            definitions = _json("/object_info/" + kind, port=port)
            if kind not in definitions:
                return "WORKFLOW_NODE_UNAVAILABLE"
            if inspect_all_nodes:
                groups = definitions[kind]["input"]
                supported = groups.get("required", {}).keys() | groups.get("optional", {}).keys()
                if not node["inputs"].keys() <= supported:
                    return "WORKFLOW_NODE_UNAVAILABLE"
            if not fields:
                continue
            model_fields = definitions[kind]["input"]["required"]
            for field in fields:
                if node["inputs"][field] not in model_fields[field][0]:
                    return "MODEL_UNAVAILABLE"
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, http.client.HTTPException) as exc:
        return comfyui.failure_status(exc)
    return "READY"


def _output(history, ident, output_node):
    if history is None:
        return None
    status = history.get("status", {})
    messages = status.get("messages", [])
    if any(isinstance(row, list) and row and row[0] == "execution_interrupted"
           for row in messages):
        raise JobError("CANCELLED")
    if status.get("status_str") != "success" or status.get("completed") is not True:
        raise JobError("GPU_RESOURCE_FAILURE" if draft_resources.provider_memory_error(status) else "EXECUTION_FAILED")
    images = history.get("outputs", {}).get(output_node, {}).get("images", [])
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
        raise JobError("OUTPUT_MISSING")
    image = images[0]
    filename = image.get("filename")
    if (image.get("subfolder") != "" or image.get("type") != "output"
            or not isinstance(filename, str) or not comfyui.IMAGE_NAME.fullmatch(filename)
            or not filename.startswith("af_" + ident + "_")):
        raise JobError("OUTPUT_INVALID")
    return filename


def _collect(provider_id, ident, port, config, metadata, *, sink=None):
    output_node = flux_workflow.node_ids(config["workflow"])["9"]
    deadline = time.monotonic() + config["timeout_seconds"]
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            history = _json("/history/" + provider_id, port=port, timeout=min(remaining, 5))
        except comfyui.ComfyHTTPError as exc:
            raise JobError(comfyui.failure_status(exc)) from None
        except (OSError, http.client.HTTPException):
            if comfy_service.managed_exited(port):
                raise JobError("COMFYUI_STOPPED") from None
            history = {}
        filename = _output(history.get(provider_id), ident, output_node)
        if filename is not None:
            break
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    else:
        raise JobError("TIMED_OUT")
    query = urlencode({"filename": filename, "subfolder": "", "type": "output"})
    contents = comfyui.request_image_bytes("/view?" + query, port=port, timeout=15,
                                         max_response_bytes=visual_jobs.MAX_IMAGE, sink=sink)
    image_file = io.BytesIO(contents) if sink is None else sink
    image_file.seek(0)
    from PIL import Image
    with Image.open(image_file, formats=["PNG"]) as image:
        if image.size != (metadata["width"], metadata["height"]):
            raise JobError("OUTPUT_INVALID")
        image.verify()
    image_file.seek(0)
    with Image.open(image_file, formats=["PNG"]) as image:
        image.load()
    return contents


def generate(prompt, *, width=None, height=None, steps=None, seed=None, scene=None,
             automated=False, hub_db=None, db_path=None, profile_id=None, expected_revision=None,
             production_job=None, production_revision=None, production_profile=None):
    """Entry point for Studio and trusted Orchestrator callers."""
    ops_control.require_active()
    if production_profile is not None:
        try:
            revision, bindings = model_hub.draft_routes(db_path=hub_db, moving=False)
        except PermissionError as exc:
            raise model_hub.ModelConfigError(str(exc)) from None
        profile = bindings["image.generate"]
        if profile != production_profile:
            raise model_hub.ModelConfigError("Model hoặc workflow tạo ảnh đã đổi. Hãy khôi phục cấu hình đã duyệt.")
    else:
        revision, profile = (model_hub.image_runtime(automated=automated, db_path=hub_db)
                             if profile_id is None else model_hub.flux_probe_profile(
                                 profile_id, expected_revision=expected_revision, db_path=hub_db))
        if production_revision is not None and revision != production_revision:
            raise ValueError("Image routing changed; resume using the updated configuration")
    config = flux_workflow.validate(profile["flux"], profile["model"], profile["base_url"])
    port = urlsplit(profile["base_url"]).port
    if scene is not None and (not isinstance(scene, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9_/-]{0,119}", scene)):
        raise ValueError("Invalid scene reference")
    graph = config["workflow"]
    ids = flux_workflow.node_ids(graph)
    width = graph[ids["27"]]["inputs"]["width"] if width is None else width
    height = graph[ids["27"]]["inputs"]["height"] if height is None else height
    steps = graph[ids["31"]]["inputs"]["steps"] if steps is None else steps
    seed = secrets.randbelow(2**53) if seed is None else seed
    ident = visual_jobs._id(production_job) if production_job is not None else uuid4().hex
    bound = flux_workflow.bind(config, ident, prompt, width, height, seed, steps)
    directory = output_directory(config["output_dir"])
    target = ensure_local_root(directory / (ident + ".png"))
    try:
        import PIL.Image  # Require the decoder before submitting GPU work.
    except ImportError:
        raise ValueError("FLUX image verification requires the AgentForge media extra") from None
    draft_resources.require_gpu("image")
    ready = readiness(config, port)
    if ready == "COMFYUI_UNAVAILABLE":
        try:
            comfy_service.ensure_running(port)
        except (ValueError, PermissionError, OSError) as exc:
            if isinstance(exc, comfy_service.StartupError):
                raise
            raise comfy_service.StartupError(str(exc)) from exc
        ready = readiness(config, port)
    if ready != "READY":
        raise comfy_service.StartupError(ready)
    comfy_service.require_other_queue_idle(port)
    metadata = {
        "prompt": prompt.strip(), "seed": seed, "width": width, "height": height,
        "steps": steps, "scene": scene, "model": profile["model"], "profile_id": profile["id"],
        "model_hub_revision": revision, "workflow": bound,
        "probe": profile_id is not None,
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
        try:
            queue = _json("/queue", port=port)
        except (OSError, RuntimeError, ValueError, http.client.HTTPException):
            raise draft_resources.ResourceBlocked("COMFYUI_QUEUE_UNAVAILABLE") from None
        comfy_service.validate_idle_queue(queue)
        draft_resources.require_gpu("image")
        ensure_local_root(directory).mkdir(parents=True, exist_ok=True)
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
        with ensure_local_root(target).open("xb+") as stream:
            created = True
            _collect(provider_id, ident, port, config, metadata, sink=stream)
            stream.flush()
            os.fsync(stream.fileno())
            stream.seek(0)
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        status = "ASSET_READY"
    except JobError as exc:
        status = exc.status
    except comfyui.ComfyHTTPError as exc:
        status = ("WORKFLOW_REJECTED" if status == "SUBMIT_UNCERTAIN" and exc.status in {400, 422}
                  else comfyui.failure_status(exc))
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError,
            http.client.HTTPException):
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
            "duration_seconds": metadata["duration_seconds"],
            "preview_url": f"/api/visuals/{ident}/preview" if status == "ASSET_READY" else None,
            "workspace_path": f"workspace/{config['output_dir']}/{ident}.png" if status == "ASSET_READY" else None,
            "width": width, "height": height, "seed": seed, "steps": steps}
