"""Scalar caching preserves exact geometry and never retains a historical raster."""

import gc
import weakref
from collections import OrderedDict

import numpy as np
import pytest
from app.predicates import evaluate, stable, visible
from app.schemas import Moved
from app.track import geometry
from app.track.geometry import Detection, FrameState, centroid


def test_scalar_geometry_uses_immutable_bits_and_matches_existing_functions():
    source = np.zeros((100, 100), dtype=np.bool_)
    source[10:14, 20:24] = True
    detection = Detection(source, 0.95)
    original = detection.packed_mask
    source[:] = False
    assert detection.area == int(detection.mask.sum()) == 16
    assert detection.center == centroid(detection.mask) == (21.5, 11.5)
    assert detection.packed_mask == original
    for shape in [(1, 1), (7, 11), (128, 64)]:
        mask = np.random.default_rng(0).random(shape) > 0.7
        d = Detection(mask, 1)
        assert d.area == int(mask.sum())
        if mask.any():
            assert d.center == centroid(mask)
        else:
            with pytest.raises(ValueError, match="no centroid"):
                _ = d.center
    assert Detection(None, 0).area == 0
    with pytest.raises(ValueError, match="no centroid"):
        _ = Detection(None, 0).center


@pytest.mark.parametrize("score,area,expected", [(0.49, 4, False), (0.5, 4, True), (1, 3, False)])
def test_cached_visibility_keeps_confidence_and_area_boundaries(score, area, expected):
    mask = np.zeros((4, 4), dtype=np.bool_)
    mask.flat[:area] = True
    d = Detection(mask, score)
    assert visible(d) is expected
    assert visible(d) == (d.mask is not None and d.score >= 0.5 and int(d.mask.sum()) >= 4)
    assert not visible(None)
    assert not visible(Detection(None, 1, known_absent=True))


def test_scalar_cache_does_not_keep_the_unpacked_mask_alive():
    with geometry._decoded_lock:
        previous, previous_bytes = geometry._decoded_masks, geometry._decoded_bytes
        geometry._decoded_masks, geometry._decoded_bytes = OrderedDict(), 0
    try:
        mask = np.ones((100, 100), dtype=np.bool_)
        d = Detection(mask, 1)
        raster = d.mask
        reference = weakref.ref(raster)
        assert d.area == 10000 and d.center == (49.5, 49.5)
        del raster
        with geometry._decoded_lock:
            geometry._decoded_masks.clear()
            geometry._decoded_bytes = 0
        gc.collect()
        assert reference() is None
        assert d.area == 10000 and d.center == (49.5, 49.5)
        assert d._mask_cache() is None
    finally:
        with geometry._decoded_lock:
            geometry._decoded_masks, geometry._decoded_bytes = previous, previous_bytes


def test_scalar_optimization_preserves_conservative_movement_smoothing():
    def frame(t, x):
        mask = np.zeros((100, 100), dtype=np.bool_)
        mask[10:14, x : x + 4] = True
        return FrameState(t, {"part": Detection(mask, 0.95)}, 100, 100)

    frames = [frame(0, 10), frame(0.5, 10), frame(1, 40), frame(1.5, 10), frame(2, 10)]
    pred = Moved(obj="part", min_dist_norm=0.15, within_s=3)
    assert evaluate(pred, frames[:3], 1)[0]
    assert not evaluate(pred, frames, 2)[0]
    assert not stable([pred], frames)[0]
    missing = FrameState(3, {"part": None}, 100, 100)
    assert evaluate(pred, [*frames, missing], 3)[:2] == (False, 0)
