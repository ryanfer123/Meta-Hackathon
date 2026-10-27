from functools import lru_cache
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from app.learn.validate import replay
from app.schemas import Protocol
from app.track.geometry import Detection, FrameState

SAMPLES = {
    "skipped-cap": "Skipped cap",
    "clean": "Clean procedure",
    "wrong-tube": "Wrong tube",
    "swapped-order": "Swapped order",
    "slow-action": "Excessive dwell",
    "occlusion": "Partial occlusion",
}


def sample_protocol() -> Protocol:
    objects = [
        {"name": n, "sam_prompt": p, "class": c}
        for n, p, c in [
            ("tube_1", "blue labelled tube", "tube"),
            ("tube_2", "red labelled tube", "tube"),
            ("tube_3", "yellow labelled tube", "tube"),
            ("tube_4", "green labelled tube", "tube"),
            ("dropper", "dropper", "dropper"),
            ("holder", "dropper holder", "holder"),
            ("cap_1", "blue cap", "cap"),
            ("label_1", "white adhesive label", "label"),
        ]
    ]
    steps = [
        {
            "id": "approach",
            "title": "Approach tube 1",
            "narration_hint": "Position the dropper at the blue tube.",
            "action": [{"op": "touching", "a": "hand", "b": "dropper"}],
            "post": [{"op": "touching", "a": "dropper", "b": "tube_1", "max_gap_px": 4}],
            "max_dwell_s": 7,
        },
        {
            "id": "return",
            "title": "Return the dropper",
            "narration_hint": "Place the dropper in its holder.",
            "action": [{"op": "touching", "a": "hand", "b": "dropper"}],
            "post": [{"op": "inside", "a": "dropper", "b": "holder"}],
            "max_dwell_s": 7,
        },
        {
            "id": "cap",
            "title": "Cap tube 1",
            "narration_hint": "Bring the blue cap into contact with tube 1.",
            "action": [{"op": "touching", "a": "hand", "b": "cap_1"}],
            "post": [{"op": "touching", "a": "cap_1", "b": "tube_1", "max_gap_px": 4}],
            "max_dwell_s": 7,
        },
        {
            "id": "label",
            "title": "Place the label",
            "narration_hint": "Place the label on tube 1.",
            "action": [{"op": "touching", "a": "hand", "b": "label_1"}],
            "post": [{"op": "inside", "a": "label_1", "b": "tube_1"}],
            "max_dwell_s": 7,
        },
    ]
    return Protocol.model_validate(
        {"name": "Colored-water handling", "objects": objects, "steps": steps}
    )


@lru_cache(maxsize=256)
def rect(x: int, y: int, w: int, h: int, width: int = 640, height: int = 360) -> NDArray[np.bool_]:
    mask = np.zeros((height, width), dtype=np.bool_)
    mask[y : y + h, x : x + w] = True
    return mask


def sample_frames(name: str, shift: int = 0) -> list[FrameState]:
    if name not in SAMPLES:
        raise ValueError("unknown sample")
    result: list[FrameState] = []
    protocol = sample_protocol()
    classes = {o.name: o.obj_class for o in protocol.objects}
    for idx in range(49):
        t = idx / 2
        positions = {
            "tube_1": (130, 145, 35, 100),
            "tube_2": (210, 145, 35, 100),
            "tube_3": (290, 145, 35, 100),
            "tube_4": (370, 145, 35, 100),
            "holder": (480, 140, 55, 110),
            "dropper": (50, 175, 12, 70),
            "cap_1": (430, 75, 32, 15),
            "label_1": (270, 300, 22, 30),
            "hand": (55, 290, 45, 30),
        }
        approach_at = 12 if name == "slow-action" else 4
        if approach_at <= t < approach_at + 2:
            positions["dropper"] = (215 if name == "wrong-tube" else 140, 130, 12, 70)
            dx, dy, _, _ = positions["dropper"]
            positions["hand"] = (dx - 10, dy - 20, 30, 35)
        return_at = 16 if name == "slow-action" else 8
        cap_at = 16 if name == "swapped-order" else 12
        label_at = 12 if name == "swapped-order" else 16
        if t >= return_at:
            positions["dropper"] = (500, 160, 12, 70)
            if t < return_at + 2:
                positions["hand"] = (492, 145, 35, 35)
        if t >= cap_at and name != "skipped-cap":
            positions["cap_1"] = (131, 136, 32, 15)
            if t < cap_at + 2:
                positions["hand"] = (125, 110, 45, 35)
        if t >= label_at:
            positions["label_1"] = (137, 175, 20, 30)
            if t < label_at + 2:
                positions["hand"] = (130, 195, 35, 35)
        objects: dict[str, Detection | None] = {
            n: Detection(rect(x + shift, y, w, h), 0.95, classes[n])
            for n, (x, y, w, h) in positions.items()
        }
        if name == "occlusion" and 11 <= t <= 15:
            objects["cap_1"] = None
        result.append(FrameState(t, objects, 640, 360, f"synthetic:{name}:{idx}", complete=True))
    return result


def wire_frame(frame: FrameState) -> dict[str, Any]:
    objects: dict[str, Any] = {}
    for name, d in frame.objects.items():
        if d is None or d.mask is None or not d.mask.any():
            objects[name] = None
            continue
        contours, _ = cv2.findContours(
            d.mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        ys, xs = np.nonzero(d.mask)
        objects[name] = {
            "x": int(np.min(xs)),
            "y": int(np.min(ys)),
            "w": int(np.max(xs) - np.min(xs) + 1),
            "h": int(np.max(ys) - np.min(ys) + 1),
            "score": d.score,
            "class": d.obj_class,
            "contours": [c.reshape(-1, 2).tolist() for c in contours],
        }
    return {"t": frame.t, "width": frame.width, "height": frame.height, "objects": objects}


def sample_run(name: str) -> dict[str, Any]:
    protocol = sample_protocol()
    frames = sample_frames(name)
    supervisor = replay(protocol, frames)
    return {
        "id": "sample-" + name,
        "name": SAMPLES[name],
        "provenance": "synthetic",
        "protocol": protocol.model_dump(by_alias=True),
        "frames": [wire_frame(f) for f in frames],
        "duration": frames[-1].t,
        "events": [e.model_dump() for e in supervisor.events],
        "states": {k: v.status for k, v in supervisor.states.items()},
        "metrics": {
            "model_calls": 0,
            "shadow_agreement": None,
            "egress_percent": None,
            "latency_ms": None,
            "note": "Synthetic masks; no Meta model outputs or real-video metrics.",
        },
        "validation": {
            "checks": {
                k: None for k in ("discriminative", "compile_replay", "held_out", "counterfactual")
            },
            "verified": False,
            "repair_rounds": 0,
            "scope": "Real expert recordings pending",
        },
    }
