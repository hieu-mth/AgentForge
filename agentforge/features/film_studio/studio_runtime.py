"""Resolve Studio's supported capabilities from Owner-owned registry profiles."""
from dataclasses import asdict
import hashlib
import json
import os.path
from agentforge.ai import registry
from agentforge.features.film_studio.studio_contracts import (
    ImageRequest as ImageRequest, MotionOutput, Profile, TextInference, ImageGeneration, VideoMotion,
)


def routing_identity(bindings, *, moving):
    """Fingerprint selected profiles only, without storing their endpoint or configuration twice."""
    return {capability: hashlib.sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False,
                                                   separators=(",", ":")).encode()).hexdigest()
            for capability, profile in bindings.items() if moving or capability != "film.motion"}


def text_adapter(profile: Profile | None) -> TextInference:
    return registry.resolve("text", profile)


def image_adapter(profile: Profile | None) -> ImageGeneration:
    return registry.resolve("image", profile)


def motion_adapter(profile: Profile | None) -> VideoMotion:
    return registry.resolve("video", profile)


# Historical receipts without an adapter identifier predate the registry.
LEGACY_MOTION_OUTPUT = MotionOutput(24, 49, (512, 288))
_LEGACY_MOTION_ADAPTER_ID = "agentforge.film.comfy.ltx_i2v.v1"


def motion_identity(adapter: VideoMotion, profile: Profile) -> dict:
    output = asdict(adapter.output_profile(profile))
    output["resolution"] = list(output["resolution"])
    encoder = profile.get("motion_encoder")
    encoder_path_sha = (hashlib.sha256(os.path.normcase(os.path.normpath(encoder)).encode()).hexdigest()
                        if encoder else None)
    return {"adapter": adapter.ADAPTER_ID, "model": profile["model"], "profile": profile.get("id"),
            "endpoint": profile.get("base_url"),
            "encoder_path_sha": encoder_path_sha,
            "workflow_sha": adapter.workflow_sha(profile), "weights": adapter.weights_identity(profile), "output": output}


def motion_artifacts(job=None) -> VideoMotion:
    """Locate artifacts by stored adapter identity, independent of current routing."""
    identity = (job or {}).get("approved_motion") or (job or {}).get("motion_plan")
    return registry.by_id("video", identity["adapter"] if identity else _LEGACY_MOTION_ADAPTER_ID)


def job_output(job) -> MotionOutput:
    identity = job.get("motion_plan") or job.get("approved_motion")
    if not identity:
        return LEGACY_MOTION_OUTPUT
    output = identity["output"]
    return MotionOutput(output["fps"], output["max_frames"], tuple(output["resolution"]))
