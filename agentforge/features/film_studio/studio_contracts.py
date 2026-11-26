"""Data exchanged between the Studio pipeline and its runtime adapters."""
from dataclasses import dataclass
from contextlib import AbstractContextManager, nullcontext
from typing import Callable

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
