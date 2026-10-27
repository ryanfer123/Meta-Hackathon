from dataclasses import replace

import numpy as np
import pytest
from app.learn.validate import StepRange, clean, mutate, validate_protocol
from app.predicates import evaluate, stable
from app.samples import rect, sample_frames, sample_protocol
from app.schemas import Absent, Count, Inside, Moved, Near, Order, Present, Protocol, Touching
from app.supervise.state_machine import Supervisor
from app.track.geometry import Detection, FrameState, containment, distance
from pydantic import ValidationError


def frame(t=0, score=0.95, missing=False):
    return FrameState(
        t,
        {
            "a": None if missing else Detection(rect(10, 10, 10, 10, 64, 64), score, "tube"),
            "b": Detection(rect(15, 15, 20, 20, 64, 64), 0.95, "tube"),
        },
        64,
        64,
        complete=True,
    )


@pytest.mark.parametrize(
    "score,expected", [(0, False), (0.49, False), (0.5, True), (0.7, True), (1, True)]
)
def test_present_threshold(score, expected):
    assert evaluate(Present(obj="a"), [frame(score=score)], 0)[0] is expected


@pytest.mark.parametrize(
    "op",
    [
        Present(obj="a"),
        Absent(obj="a"),
        Inside(a="a", b="b"),
        Touching(a="a", b="b"),
        Near(a="a", b="b"),
        Moved(obj="a"),
    ],
)
def test_occlusion_is_unknown(op):
    assert evaluate(op, [frame(missing=True)], 0)[:2] == (False, 0)


def test_absence_requires_coverage():
    f = replace(frame(), objects={"a": Detection(None, 0.95, known_absent=True)})
    assert evaluate(Absent(obj="a"), [f], 0)[0]
    assert evaluate(Absent(obj="a"), [replace(f, complete=False)], 0)[1] == 0


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_smoothing_requires_consecutive_frames(n):
    frames = [frame(i) for i in range(n)]
    assert stable([Present(obj="a")], frames, 3)[0] == (n >= 3)


def test_flicker_resets_window():
    assert not stable([Present(obj="a")], [frame(0), frame(1, missing=True), frame(2)])[0]


def test_low_confidence_not_stably_true():
    assert not stable([Present(obj="a")], [frame(i, score=0.6) for i in range(3)])[0]


@pytest.mark.parametrize(
    "gap,threshold,expected", [(1, 1, True), (2, 1, False), (0, 0, True), (8, 8, True)]
)
def test_mask_gap_boundary(gap, threshold, expected):
    a = rect(0, 0, 5, 5, 64, 64)
    b = rect(4 + gap, 0, 5, 5, 64, 64)
    assert (distance(a, b) <= threshold) is expected


def test_containment_bbox():
    assert containment(rect(12, 12, 3, 3, 64, 64), rect(10, 10, 20, 20, 64, 64)) == 1
    assert containment(rect(0, 0, 3, 3, 64, 64), rect(10, 10, 20, 20, 64, 64)) == 0


def test_empty_mask_geometry():
    assert distance(np.zeros((8, 8), dtype=bool), np.ones((8, 8), dtype=bool)) == float("inf")


def test_count_requires_scene_coverage():
    assert evaluate(Count(obj_class="tube", eq=2), [frame()], 0)[0]
    assert evaluate(Count(obj_class="tube", eq=2), [replace(frame(), complete=False)], 0)[1] == 0


def test_moved_time_window():
    f1 = frame(0)
    f2 = replace(frame(2), objects={"a": Detection(rect(40, 10, 10, 10, 64, 64), 0.95)})
    assert evaluate(Moved(obj="a", min_dist_norm=0.2), [f1, f2], 2)[0]
    assert evaluate(Moved(obj="a", within_s=1), [f1, f2], 2)[1] == 0


def test_order_uses_history():
    f1 = replace(frame(0), interactions={"a": 0})
    f2 = replace(frame(2), interactions={"b": 2})
    assert evaluate(Order(first="a", then="b"), [f1, f2], 2)[0]
    assert not evaluate(Order(first="b", then="a"), [f1, f2], 2)[0]


@pytest.mark.parametrize(
    "mutation",
    ["unknown", "duplicate_step", "duplicate_object", "empty_post", "bad_dwell", "extra", "group"],
)
def test_protocol_rejects_invalid_contract(mutation):
    p = sample_protocol().model_dump(by_alias=True)
    if mutation == "unknown":
        p["steps"][0]["post"][0]["a"] = "ghost"
    if mutation == "duplicate_step":
        p["steps"][1]["id"] = p["steps"][0]["id"]
    if mutation == "duplicate_object":
        p["objects"].append(p["objects"][0])
    if mutation == "empty_post":
        p["steps"][0]["post"] = []
    if mutation == "bad_dwell":
        p["steps"][0]["min_dwell_s"] = 999
    if mutation == "extra":
        p["hallucination"] = True
    if mutation == "group":
        p["steps"][0]["group"] = "g"
        p["steps"][2]["group"] = "g"
    with pytest.raises(ValidationError):
        Protocol.model_validate(p)


def test_hand_added_implicitly():
    p = sample_protocol().model_dump(by_alias=True)
    p["objects"] = [o for o in p["objects"] if o["name"] != "hand"]
    assert sum(o.name == "hand" for o in Protocol.model_validate(p).objects) == 1


@pytest.mark.parametrize(
    "name,expected",
    [
        ("clean", None),
        ("skipped-cap", "skipped"),
        ("wrong-tube", "wrong_object"),
        ("swapped-order", "out_of_order"),
        ("slow-action", "dwell_exceeded"),
        ("occlusion", "uncertain"),
    ],
)
def test_scenario_deviations(name, expected):
    engine = Supervisor(sample_protocol())
    for f in sample_frames(name):
        engine.tick(f)
    engine.finish()
    if expected is None:
        assert all(s.status == "DONE" for s in engine.states.values())
        assert all(e.kind in ("step_started", "step_completed") for e in engine.events)
    else:
        assert any(e.kind == expected for e in engine.events)


def test_replay_is_deterministic():
    frames = sample_frames("skipped-cap")
    engines = [Supervisor(sample_protocol()), Supervisor(sample_protocol())]
    for e in engines:
        for f in frames:
            e.tick(f)
    assert engines[0].events == engines[1].events


def test_vacuous_post_does_not_complete():
    p = sample_protocol()
    p.steps[0].post = [Present(obj="tube_1")]
    e = Supervisor(p)
    for f in sample_frames("clean")[:16]:
        e.tick(f)
    assert e.states["approach"].status != "DONE"


def test_nonmonotonic_frames_rejected():
    e = Supervisor(sample_protocol())
    e.tick(sample_frames("clean")[0])
    with pytest.raises(ValueError):
        e.tick(sample_frames("clean")[0])


def test_short_dwell_recorded():
    p = sample_protocol()
    p.steps[0].min_dwell_s = 6
    e = Supervisor(p)
    for f in sample_frames("clean"):
        e.tick(f)
    assert any(v.kind == "dwell_too_short" for v in e.events)


def test_unordered_group_allows_reverse_order():
    p = sample_protocol()
    p.steps[2].group = p.steps[3].group = "finish"
    p.steps[2].max_dwell_s = p.steps[3].max_dwell_s = 20
    assert clean(p, sample_frames("swapped-order"))


def test_held_out_not_optional_for_verification():
    p = sample_protocol()
    ranges = {s.id: StepRange(start=i * 4 + 2, end=i * 4 + 5.5) for i, s in enumerate(p.steps)}
    result = validate_protocol(p, sample_frames("clean"), [], ranges)
    assert not result["verified"] and not p.verified


def test_mutation_rebases_time():
    frames = sample_frames("clean")
    out = mutate(frames, {"s": StepRange(start=4, end=6)}, "s")
    assert len(out) == len(frames) - 5
    assert [f.t for f in out] == [i / 2 for i in range(len(out))]


def test_irregular_masks_use_real_pixel_distance():
    import cv2

    a = np.zeros((64, 64), dtype=np.uint8)
    b = np.zeros((64, 64), dtype=np.uint8)
    cv2.circle(a, (15, 20), 5, 1, -1)
    cv2.circle(b, (27, 20), 5, 1, -1)
    assert distance(a.astype(bool), b.astype(bool)) == pytest.approx(2)
