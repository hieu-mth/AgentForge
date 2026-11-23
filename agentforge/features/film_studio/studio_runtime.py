"""Resolve Studio's supported capabilities from Owner-owned registry profiles."""
from dataclasses import asdict
import hashlib
import os.path
from pathlib import Path
from typing import Any, BinaryIO, Callable, Protocol

from agentforge.features.film_studio import draft_motion, studio_ollama
from agentforge.features.film_studio.draft_resources import NeedsReconciliation
from agentforge.features.film_studio.studio_contracts import ImageRequest, MotionOutput
from agentforge.features.media import studio_flux

Profile = dict[str, Any]
PreparedMotion = tuple[str, str, Path, str]


class TextInference(Protocol):
    def infer_structured(self, profile: Profile, instructions: str, data: dict, schema: dict, *,
                         cpu_only: bool = False, extended_plan: bool = False) -> Any: ...


class ImageGeneration(Protocol):
    def supports(self, profile: Profile) -> bool: ...
    def preflight(self, profile: Profile, *, include_profiles: bool = False) -> None: ...
    def release_idle_models(self, profile: Profile) -> bool: ...
    def generate(self, profile: Profile, request: ImageRequest) -> dict: ...


class VideoMotion(Protocol):
    ADAPTER_ID: str
    MAX_CLIP_BYTES: int

    def supports(self, profile: Profile) -> bool: ...
    def workflow_sha(self) -> str: ...
    def check_legacy_workflow(self, folder: Path) -> None: ...
    def weights_identity(self) -> dict[str, str]: ...
    def output_profile(self) -> MotionOutput: ...
    def bind(self, profile: Profile) -> Profile: ...
    def prepare(self, job: dict, folder: Path) -> PreparedMotion: ...
    def run_shot(self, scene: dict, index: int, prepared: PreparedMotion, profile: Profile,
                 save: Callable[[], None], cancelled: Callable[[], bool]) -> None: ...
    def require_resolved_ledger(self, job: dict) -> None: ...
    def require_draft_removable(self, ident: str) -> None: ...
    def reconcile_cancelled(self, job: dict) -> bool: ...
    def clip_path(self, scene: dict) -> Path: ...
    def verify_clip(self, scene: dict, stream: BinaryIO) -> None: ...


def text_adapter(profile: Profile | None) -> TextInference:
    if not profile or profile.get("provider") != "ollama":
        raise ValueError("Studio requires a supported local text profile.")
    return studio_ollama


def image_adapter(profile: Profile | None) -> ImageGeneration:
    if not profile or not studio_flux.supports(profile):
        raise ValueError("Studio requires a compatible local image checkpoint and workflow.")
    return studio_flux


MOTION_ADAPTERS: tuple[VideoMotion, ...] = (draft_motion,)
LEGACY_MOTION_OUTPUT = MotionOutput(24, 49, (512, 288))


def motion_adapter(profile: Profile | None) -> VideoMotion:
    matches = [adapter for adapter in MOTION_ADAPTERS if profile and adapter.supports(profile)]
    if len(matches) != 1:
        raise ValueError("Studio requires a compatible local motion checkpoint and workflow.")
    return matches[0]


def motion_identity(adapter: VideoMotion, profile: Profile) -> dict:
    output = asdict(adapter.output_profile())
    output["resolution"] = list(output["resolution"])
    encoder = profile.get("motion_encoder")
    encoder_path_sha = (hashlib.sha256(os.path.normcase(os.path.normpath(encoder)).encode()).hexdigest()
                        if encoder else None)
    return {"adapter": adapter.ADAPTER_ID, "model": profile["model"], "profile": profile.get("id"),
            "endpoint": profile.get("base_url"),
            "encoder_path_sha": encoder_path_sha,
            "workflow_sha": adapter.workflow_sha(), "weights": adapter.weights_identity(), "output": output}


def motion_artifacts(job=None) -> VideoMotion:
    """Locate artifacts by stored adapter identity, independent of current routing."""
    identity = (job or {}).get("approved_motion") or (job or {}).get("motion_plan")
    if identity is None:
        return draft_motion
    matches = [adapter for adapter in MOTION_ADAPTERS if adapter.ADAPTER_ID == identity["adapter"]]
    if len(matches) != 1:
        raise ValueError("Stored motion adapter unavailable.")
    return matches[0]


def job_output(job) -> MotionOutput:
    identity = job.get("motion_plan") or job.get("approved_motion")
    if not identity:
        return LEGACY_MOTION_OUTPUT
    output = identity["output"]
    return MotionOutput(output["fps"], output["max_frames"], tuple(output["resolution"]))
