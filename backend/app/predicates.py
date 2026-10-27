from math import dist, hypot

from app.schemas import Absent, Count, Inside, Moved, Near, Order, Predicate, Present, Touching
from app.track.geometry import Detection, FrameState, centroid, containment, distance

Result = tuple[bool, float, str]


def visible(d: Detection | None) -> bool:
    return d is not None and d.mask is not None and d.score >= 0.5 and int(d.mask.sum()) >= 4


def evaluate(pred: Predicate, window: list[FrameState], t: float) -> Result:
    history = [f for f in window if f.t <= t]
    if not history:
        return False, 0, "no observations"
    frame = history[-1]
    if isinstance(pred, Count):
        if not frame.complete:
            return False, 0, "count requires complete scene coverage"
        ds = [d for d in frame.objects.values() if d and d.obj_class == pred.obj_class]
        return (
            sum(visible(d) for d in ds) == pred.eq,
            min([d.score for d in ds] or [1]),
            "visible instance count",
        )
    if isinstance(pred, Order):
        first_touch: dict[str, float] = {}
        for f in history:
            first_touch.update({k: v for k, v in f.interactions.items() if k not in first_touch})
            hand = f.objects.get("hand")
            if visible(hand) and hand is not None and hand.mask is not None:
                for name in (pred.first, pred.then):
                    d = f.objects.get(name)
                    if visible(d) and d is not None and d.mask is not None:
                        if distance(d.mask, hand.mask) <= 8:
                            first_touch.setdefault(name, f.t)
        if pred.first not in first_touch or pred.then not in first_touch:
            return False, 0, "interaction sequence not fully observed"
        return first_touch[pred.first] < first_touch[pred.then], 0.9, "first observed hand contacts"
    if isinstance(pred, (Present, Absent, Moved)):
        d = frame.objects.get(pred.obj)
        if isinstance(pred, Absent):
            if d is not None and d.known_absent and frame.complete:
                return True, d.score, "explicit absence with scene coverage"
            if visible(d):
                return False, d.score if d else 0, "object visible"
            return False, 0, "missing mask is not evidence of absence"
        if not visible(d) or d is None or d.mask is None:
            return False, 0, "object occluded or not detected"
        if isinstance(pred, Present):
            return True, d.score, "object visible"
        candidates = [f.objects.get(pred.obj) for f in history if t - pred.within_s <= f.t]
        points = [
            centroid(x.mask)
            for x in candidates
            if visible(x) and x is not None and x.mask is not None
        ]
        if len(points) < 2:
            return False, 0, "insufficient movement history"
        displacement = dist(points[0], points[-1]) / hypot(frame.width, frame.height)
        return displacement >= pred.min_dist_norm, d.score, f"displacement={displacement:.3f}"
    a, b = frame.objects.get(pred.a), frame.objects.get(pred.b)
    if (
        not visible(a)
        or not visible(b)
        or a is None
        or b is None
        or a.mask is None
        or b.mask is None
    ):
        return False, 0, "one or both objects unobserved"
    confidence = min(a.score, b.score)
    if isinstance(pred, Inside):
        ratio = containment(a.mask, b.mask)
        return ratio >= pred.min_containment, confidence, f"containment={ratio:.3f} (bbox)"
    if isinstance(pred, Touching):
        gap = distance(a.mask, b.mask)
        return gap <= pred.max_gap_px, confidence, f"mask gap={gap:.1f}px"
    assert isinstance(pred, Near)
    gap_norm = dist(centroid(a.mask), centroid(b.mask)) / hypot(frame.width, frame.height)
    return gap_norm <= pred.max_dist_norm, confidence, f"centroid distance={gap_norm:.3f}"


def stable(preds: list[Predicate], window: list[FrameState], n: int = 3) -> Result:
    if not preds:
        return True, 1, "no preconditions"
    if len(window) < n:
        return False, 0, "warming temporal window"
    results = [
        evaluate(p, window[: i + 1], window[i].t)
        for i in range(len(window) - n, len(window))
        for p in preds
    ]
    return (
        all(v and c >= 0.7 for v, c, _ in results),
        min(c for _, c, _ in results),
        "; ".join(dict.fromkeys(reason for _, _, reason in results)),
    )
