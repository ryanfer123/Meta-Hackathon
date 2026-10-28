"""Mask fidelity and bounded stored memory; synthetic data, never live model calls."""

import gc
import json
import sys
import weakref
from dataclasses import FrozenInstanceError
from pathlib import Path

import cv2
import numpy as np
import pytest
from app.predicates import evaluate
from app.replay_cache import canonical
from app.samples import MAX_CONTOUR_POINTS, SAMPLES, sample_run, wire_frame
from app.schemas import Inside, Present, Touching
from app.service import evidence_overlays, finalize_run
from app.track import geometry
from app.track.geometry import Detection, FrameState


@pytest.mark.parametrize("shape", [(3, 5), (0, 0), (1, 17), (768, 1024)])
def test_packed_masks_round_trip_non_byte_aligned_and_empty_shapes(shape):
    original = np.random.default_rng(4).integers(0, 2, shape, dtype=np.uint8).astype(np.bool_)
    detection = Detection(original, 0.81, "tube", False)
    assert detection.mask_shape == shape
    assert len(detection.packed_mask) == (original.size + 7) // 8
    np.testing.assert_array_equal(detection.mask, original)
    assert detection.mask.dtype == np.bool_
    assert detection.score == 0.81 and detection.obj_class == "tube"
    assert not detection.known_absent


def test_constructor_snapshots_views_and_preserves_none_and_explicit_absence():
    source = np.ones((20, 40), dtype=np.bool_)
    view = source[::2, ::3]
    expected = view.copy()
    source_ref = weakref.ref(source)
    detection = Detection(mask=view, score=0.7, obj_class="cap", known_absent=False)
    source[:] = False
    np.testing.assert_array_equal(detection.mask, expected)
    del source, view
    assert source_ref() is None
    with pytest.raises(ValueError, match="read-only"):
        detection.mask[0, 0] = False
    with pytest.raises(FrozenInstanceError):
        detection.score = 0.1
    for absent in (True, False):
        missing = Detection(None, 0.9, "cap", absent)
        assert missing.mask is None and missing.packed_mask is None and missing.mask_shape is None
        assert missing.known_absent is absent


def test_weak_instance_cache_does_not_retain_every_decoded_history_mask():
    original = np.ones((768, 1024), dtype=np.bool_)
    detection = Detection(original, 0.9)
    decoded = detection.mask
    assert decoded is detection.mask
    ref = weakref.ref(decoded)
    del decoded
    fillers = [Detection(original, 0.9) for _ in range(12)]
    for other in fillers:
        assert other.mask.all()
    gc.collect()
    assert ref() is None
    assert detection.mask.all()
    assert sum(mask.nbytes for mask in geometry._decoded_masks.values()) <= 8 * 1024 * 1024


def noisy_mask():
    rng = np.random.default_rng(42)
    mask = np.zeros((768, 1024), dtype=np.bool_)
    mask[150:450, 300:600] = True
    mask[rng.integers(0, 768, 1600), rng.integers(0, 1024, 1600)] = True
    return mask


def test_180_frames_eight_objects_store_less_than_200_mb_after_every_mask_is_read(record_property):
    source = noisy_mask()
    frames = [
        FrameState(
            i / 2,
            {f"object_{j}": Detection(source, 0.9) for j in range(8)},
            1024,
            768,
        )
        for i in range(180)
    ]
    detections = [d for frame in frames for d in frame.objects.values()]
    for detection in detections:
        assert detection.mask.shape == source.shape
    # Count actual packed bytes plus their headers, detection metadata and retained
    # decoded payloads. Reading every mask must not restore a 1.1 GB history cache.
    stored_bytes = sum(
        sys.getsizeof(d)
        + sys.getsizeof(d.packed_mask)
        + sys.getsizeof(d.mask_shape)
        + sys.getsizeof(d._mask_cache)
        for d in detections
    )
    stored_bytes += sum(
        mask.nbytes + sys.getsizeof(mask) for mask in geometry._decoded_masks.values()
    )
    record_property("stored_mask_bytes_including_cache", stored_bytes)
    assert stored_bytes < 200_000_000
    assert len({id(d.packed_mask) for d in detections}) == 180 * 8


def test_noisy_90_second_run_json_has_bounded_display_contours_without_changing_predicates(
    record_property,
    tmp_path,
):
    mask = noisy_mask()
    detection = Detection(mask, 0.9, "tube")
    state = FrameState(0, {"a": detection, "b": Detection(mask.copy(), 0.95, "rack")}, 1024, 768)
    predicates = [Present(obj="a"), Touching(a="a", b="b"), Inside(a="a", b="b")]
    before = [evaluate(predicate, [state], 0) for predicate in predicates]
    wire = wire_frame(state)
    obj = wire["objects"]["a"]
    assert obj["contours_truncated"] is True
    assert obj["contour_tolerance_px"] >= 1.5
    assert sum(len(c) for c in obj["contours"]) <= MAX_CONTOUR_POINTS
    np.testing.assert_array_equal(detection.mask, mask)
    assert [evaluate(predicate, [state], 0) for predicate in predicates] == before
    run = sample_run("clean")
    # 180 observations sampled at 2 fps from a 90-second synthetic source; eight objects.
    run["frames"] = [
        {**wire, "t": i / 2, "objects": {f"object_{j}": obj for j in range(8)}} for i in range(180)
    ]
    run["duration"] = 90
    finalize_run(tmp_path, run, {})
    size = (tmp_path / "run.json").stat().st_size
    assert size == len(canonical(run))
    record_property("synthetic_90s_run_json_bytes", size)
    assert size < 20_000_000


@pytest.mark.parametrize("name", SAMPLES)
def test_synthetic_samples_keep_exact_existing_exported_outputs(tmp_path, name):
    baseline = json.loads(
        (
            Path(__file__).resolve().parents[2] / "frontend/public/samples" / f"{name}.json"
        ).read_text()
    )
    run = sample_run(name)
    finalize_run(tmp_path, run, {})
    assert run == baseline


def test_evidence_overlay_uses_unpacked_exact_masks(tmp_path):
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    source = tmp_path / "frame_0.0.jpg"
    assert cv2.imwrite(str(source), image)
    mask = np.zeros((48, 64), dtype=np.bool_)
    mask[20:35, 15:40] = True
    detection = Detection(mask, 0.9)
    frame = FrameState(0, {"cap": detection}, 64, 48, str(source))
    evidence = evidence_overlays([frame], [(0, source)], tmp_path)
    assert str(source) in evidence
    overlay = cv2.imdecode(np.frombuffer(evidence[str(source)], dtype=np.uint8), cv2.IMREAD_COLOR)
    assert overlay[20, 20].any()
    np.testing.assert_array_equal(detection.mask, mask)


def test_hsv_fallback_retains_exact_mask_and_unknown_when_color_is_missing():
    from app.schemas import ObjectSpec
    from app.track.fallback_color import segment_color

    image = np.zeros((40, 60, 3), dtype=np.uint8)
    image[10:25, 20:35] = (0, 0, 255)
    obj = ObjectSpec.model_validate(
        {
            "name": "red_cap",
            "sam_prompt": "red cap",
            "class": "cap",
            "hsv_lower": (0, 150, 150),
            "hsv_upper": (5, 255, 255),
        }
    )
    detection = segment_color(image, obj)
    expected = np.zeros((40, 60), dtype=np.bool_)
    expected[10:25, 20:35] = True
    np.testing.assert_array_equal(detection.mask, expected)
    assert detection.obj_class == "cap" and detection.score == 0.8
    assert isinstance(detection.packed_mask, bytes)
    missing = segment_color(np.zeros_like(image), obj)
    assert missing.mask is None and not missing.known_absent
