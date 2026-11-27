"""Data exchanged between the Studio pipeline and its runtime adapters."""
from dataclasses import dataclass
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any, BinaryIO, Callable, Protocol

BRIEF_LIMIT = 20_000

DispatchGuard = Callable[[], AbstractContextManager[int | None]]


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    ratio: str
    scene: str
    job_id: str
    revision: int
    dispatch_guard: DispatchGuard = nullcontext


@dataclass(frozen=True)
class MotionOutput:
    fps: int
    max_frames: int
    resolution: tuple[int, int]


Profile = dict[str, Any]
PreparedMotion = tuple[str, Any, Path, str]


class TextInference(Protocol):
    def infer_structured(self, profile: Profile, instructions: str, data: dict, schema: dict, *,
                         cpu_only: bool = False, extended_plan: bool = False) -> Any: ...


class ImageGeneration(Protocol):
    ADAPTER_ID: str

    def output_limits(self, profile: Profile) -> dict: ...
    def workflow_sha(self, profile: Profile) -> str | None: ...
    def supports(self, profile: Profile) -> bool: ...
    def preflight(self, profile: Profile, *, include_profiles: bool = False) -> None: ...
    def release_idle_models(self, profile: Profile) -> bool: ...
    def generate(self, profile: Profile, request: ImageRequest) -> dict: ...


class VideoMotion(Protocol):
    ADAPTER_ID: str
    MAX_CLIP_BYTES: int

    def supports(self, profile: Profile) -> bool: ...
    def workflow_sha(self, profile: Profile) -> str: ...
    def check_legacy_workflow(self, folder: Path) -> None: ...
    def weights_identity(self, profile: Profile) -> dict[str, str]: ...
    def output_profile(self, profile: Profile) -> MotionOutput: ...
    def input_modes(self, profile: Profile) -> tuple[str, ...]: ...
    def registry_readiness(self, profile: Profile) -> str: ...
    def bind(self, profile: Profile) -> Profile: ...
    def prepare(self, job: dict, folder: Path) -> PreparedMotion: ...
    def run_shot(self, scene: dict, index: int, prepared: PreparedMotion, profile: Profile,
                 save: Callable[[], None], cancelled: Callable[[], bool], *,
                 dispatch_guard: DispatchGuard, retry_motion_job: str | None = None,
                 previous_motion: dict | None = None) -> None: ...
    def require_resolved_ledger(self, job: dict) -> None: ...
    def require_draft_removable(self, ident: str) -> None: ...
    def reconcile_cancelled(self, job: dict) -> bool: ...
    def clip_path(self, scene: dict) -> Path: ...
    def verify_clip(self, scene: dict, stream: BinaryIO) -> None: ...


class ProviderRequestError(ValueError):
    """Adapter-classified response; messages must be sanitized before construction.

    Rejection is positive evidence that a new remote job was not accepted.
    Unknown outcomes must never authorize an automatic resubmission.
    """

    def __init__(self, message, *, rejected=False, retryable=False, retry_after=None):
        if retryable and not rejected:
            raise ValueError("A retryable provider error must be a definite rejection")
        self.rejected = rejected
        self.retryable = retryable
        self.retry_after = retry_after
        super().__init__(message)
