"""Resolve Studio's supported capabilities from Owner-owned registry profiles."""
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
    def preflight(self, profile: Profile, *, include_profiles: bool = False) -> None: ...
    def release_idle_models(self, profile: Profile) -> bool: ...
    def generate(self, profile: Profile, request: ImageRequest) -> dict: ...


class VideoMotion(Protocol):
    MAX_CLIP_BYTES: int

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
    if not profile or profile.get("provider") != "comfyui" or "flux" not in profile:
        raise ValueError("Studio requires a supported local image profile.")
    return studio_flux


def motion_adapter(profile: Profile | None) -> VideoMotion:
    if not profile or profile.get("provider") != "comfyui":
        raise ValueError("Studio requires a supported local motion profile.")
    return draft_motion


def motion_artifacts() -> VideoMotion:
    """Read or reconcile existing drafts without resolving a newly selected profile."""
    return draft_motion


def motion_output() -> MotionOutput:
    """The production output contract shared by current and stored Studio jobs."""
    return motion_artifacts().output_profile()
