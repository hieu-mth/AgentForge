"""Data exchanged between the Studio pipeline and its runtime adapters."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    ratio: str
    scene: str
    job_id: str
    revision: int


@dataclass(frozen=True)
class MotionOutput:
    fps: int
    max_frames: int
    resolution: tuple[int, int]
