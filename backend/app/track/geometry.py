from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from weakref import ReferenceType, ref

import cv2
import numpy as np
from numpy.typing import NDArray

Mask = NDArray[np.bool_]


# Full rasters are transient views, not retained once for every historical detection.
_DECODED_CACHE_LIMIT = 8 * 1024 * 1024
_decoded_masks: OrderedDict[int, Mask] = OrderedDict()
_decoded_bytes = 0
_decoded_lock = Lock()


def _retain_decoded(key: int, mask: Mask) -> None:
    global _decoded_bytes
    with _decoded_lock:
        previous = _decoded_masks.pop(key, None)
        if previous is not None:
            _decoded_bytes -= previous.nbytes
        if mask.nbytes > _DECODED_CACHE_LIMIT:
            return
        while _decoded_masks and _decoded_bytes + mask.nbytes > _DECODED_CACHE_LIMIT:
            _, removed = _decoded_masks.popitem(last=False)
            _decoded_bytes -= removed.nbytes
        _decoded_masks[key] = mask
        _decoded_bytes += mask.nbytes


@dataclass(frozen=True, slots=True, init=False)
class Detection:
    """Immutable bit-packed geometry with a backwards-compatible mask constructor.

    Each instance keeps a weak reference to its last unpacked mask. Only an 8 MiB
    process-wide LRU holds strong references, so replaying an entire history cannot
    turn every detection back into a permanently resident full raster. Callers may
    hold temporary decoded masks; these are read-only snapshots of the packed bits.
    """

    packed_mask: bytes | None = field(repr=False)
    mask_shape: tuple[int, int] | None
    score: float
    obj_class: str
    known_absent: bool
    _mask_cache: ReferenceType[Mask] | None = field(repr=False, compare=False)

    def __init__(
        self,
        mask: Mask | None,
        score: float,
        obj_class: str = "object",
        known_absent: bool = False,
    ) -> None:
        packed: bytes | None = None
        shape: tuple[int, int] | None = None
        if mask is not None:
            array = np.asarray(mask, dtype=np.bool_)
            if array.ndim != 2:
                raise ValueError("Detection masks must be two-dimensional")
            shape = (int(array.shape[0]), int(array.shape[1]))
            packed = np.packbits(array, axis=None, bitorder="big").tobytes()
        object.__setattr__(self, "packed_mask", packed)
        object.__setattr__(self, "mask_shape", shape)
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "obj_class", obj_class)
        object.__setattr__(self, "known_absent", known_absent)
        object.__setattr__(self, "_mask_cache", None)

    @property
    def mask(self) -> Mask | None:
        if self.packed_mask is None or self.mask_shape is None:
            return None
        decoded = self._mask_cache() if self._mask_cache is not None else None
        if decoded is None:
            height, width = self.mask_shape
            decoded = (
                np.unpackbits(
                    np.frombuffer(self.packed_mask, dtype=np.uint8),
                    count=height * width,
                    bitorder="big",
                )
                .reshape(height, width)
                .view(np.bool_)
            )
            decoded.setflags(write=False)
            object.__setattr__(self, "_mask_cache", ref(decoded))
        _retain_decoded(id(self), decoded)
        return decoded


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
