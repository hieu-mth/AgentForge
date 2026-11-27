"""ComfyUI image adapter using validated image workflow dialects."""
import time
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

from agentforge.features.film_studio import draft_resources
from agentforge.features.media import flux_runtime, comfy_image_workflow
from agentforge.integrations import comfy_service, comfyui


ADAPTER_ID = "comfyui_flux_gguf"  # Stable legacy receipt identifier.


def local_image_config(profile):
    return comfy_image_workflow.profile_config(profile)


def output_limits(profile):
    config = local_image_config(profile)
    return {"format": "png", "batch": 1, "min_resolution": 256,
            "max_resolution": config["max_resolution"], "dimension_multiple": 16,
            "min_steps": 1, "max_steps": config["max_steps"]}


def workflow_sha(profile):
    graph = json.dumps(local_image_config(profile)["workflow"], sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(graph).hexdigest()


def supports(profile):
    if profile.get("provider") != "comfyui" or "motion_encoder" in profile:
        return False
    try:
        local_image_config(profile)
    except (ValueError, KeyError, TypeError):
        return False
    return True


def registry_readiness(profile):
    return flux_runtime.readiness(local_image_config(profile), urlsplit(profile["base_url"]).port, inspect_all_nodes=True)


def check_metadata(profile, *, opener=None):
    return {"profile_id": profile["id"],
            "status": flux_runtime.readiness(local_image_config(profile), urlsplit(profile["base_url"]).port),
            "checked_at": datetime.now(timezone.utc).isoformat(), "inference_invoked": False}


def preflight(profile, *, include_profiles=False):
    port = urlsplit(profile["base_url"]).port
    if include_profiles:
        comfy_service.require_other_queue_idle(port, include_profiles=True)
    else:
        comfy_service.require_other_queue_idle(port)
    comfy_service.require_idle_queue(port, allow_offline=True)


def release_idle_models(profile):
    if not draft_resources.can_release_models(draft_resources.snapshot()):
        return False
    port = urlsplit(profile["base_url"]).port
    try:
        queue = flux_runtime._json("/queue", port=port)
        if queue.get("queue_running") != [] or queue.get("queue_pending") != []:
            return False
        def reserved():
            stats = flux_runtime._json("/system_stats", port=port)
            return sum(device.get("torch_vram_total", 0) for device in stats.get("devices", [])
                       if device.get("type") == "cuda")
        initial = reserved()
        comfyui.request_image_bytes("/free", body={"unload_models": True, "free_memory": True}, port=port)
        for _ in range(8):
            time.sleep(1)
            remaining = reserved()
            if remaining == 0 or remaining < initial:
                return True
    except (OSError, ValueError, RuntimeError):
        return False
    return False


def generate(profile, request):
    limit = local_image_config(profile)["max_resolution"]
    long = min(768, limit // 16 * 16)
    short = max(256, (long * 9 // 16) // 16 * 16)
    width, height = (short, long) if request.ratio == "9:16" else (long, short)
    return flux_runtime.generate(request.prompt, width=width, height=height, automated=True,
                                 scene=request.scene, production_job=request.job_id,
                                 production_revision=request.revision, production_profile=profile,
                                 dispatch_guard=request.dispatch_guard)
