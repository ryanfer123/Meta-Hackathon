from dataclasses import dataclass, field

import cv2
import numpy as np
from numpy.typing import NDArray

Mask = NDArray[np.bool_]


@dataclass(frozen=True)
class Detection:
    mask: Mask | None
    score: float
    obj_class: str = "object"
    known_absent: bool = False


@dataclass(frozen=True)
class FrameState:
    t: float
    objects: dict[str, Detection | None]
    width: int
    height: int
    evidence_frame: str | None = None
    complete: bool = False
    interactions: dict[str, float] = field(default_factory=dict)


def centroid(mask: Mask) -> tuple[float, float]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        raise ValueError("empty mask has no centroid")
    return float(xs.mean()), float(ys.mean())


def distance(a: Mask, b: Mask) -> float:
    if a.shape != b.shape:
        raise ValueError("masks must share frame dimensions")
    if not a.any() or not b.any():
        return float("inf")
    if np.any(a & b):
        return 0
    ay, ax = np.nonzero(a)
    by, bx = np.nonzero(b)
    x0, x1, y0, y1 = int(np.min(ax)), int(np.max(ax)), int(np.min(ay)), int(np.max(ay))
    u0, u1, v0, v1 = int(np.min(bx)), int(np.max(bx)), int(np.min(by)), int(np.max(by))
    if int(a.sum()) == (x1 - x0 + 1) * (y1 - y0 + 1) and int(b.sum()) == (u1 - u0 + 1) * (
        v1 - v0 + 1
    ):
        return float(np.hypot(max(0, x0 - u1, u0 - x1), max(0, y0 - v1, v0 - y1)))
    transform = cv2.distanceTransform((~b).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return float(np.min(transform[a]))


def containment(a: Mask, b: Mask) -> float:
    if a.shape != b.shape:
        raise ValueError("masks must share frame dimensions")
    if not a.any() or not b.any():
        return 0
    ys, xs = np.nonzero(b)
    bbox = np.zeros_like(b)
    bbox[int(np.min(ys)) : int(np.max(ys)) + 1, int(np.min(xs)) : int(np.max(xs)) + 1] = True
    return int(np.count_nonzero(a & bbox)) / int(np.count_nonzero(a))
