"""Step-scoped advisory evidence. Never interprets opinions as rule decisions."""

import json
from pathlib import Path

from app.predicates import evaluate
from app.schemas import Event, Step
from app.track.geometry import FrameState


def review_window(
    paths: list[tuple[float, Path]], events: list[Event], event: Event
) -> list[tuple[float, Path]]:
    """Show start/middle/end of an observed active step, never frames after the event."""
    starts = [
        e.t
        for e in events
        if e.step_id == event.step_id and e.kind == "step_started" and e.t <= event.t
    ]
    start = max(starts) if starts else max(0, event.t - 1)
    candidates = [(t, path) for t, path in paths if start <= t <= event.t]
    if len(candidates) <= 3:
        return candidates
    return [candidates[0], candidates[len(candidates) // 2], candidates[-1]]


def review_prompt(step: Step, event: Event, frames: list[FrameState], times: list[float]) -> str:
    observations = []
    for t in times:
        window = [frame for frame in frames if frame.t <= t]
        observations.append(
            {
                "t": t,
                "checks": [
                    {
                        "predicate": pred.model_dump(),
                        "observed": truth,
                        "confidence": confidence,
                        "measurement": reason,
                    }
                    for pred in step.action + step.post
                    for truth, confidence, reason in [evaluate(pred, window, t)]
                ],
            }
        )
    return (
        "Review ONLY the target step using the attached frames in timestamp order. "
        "You are advisory; deterministic rules remain unchanged. "
        "A final shape does not prove earlier actions, movement, hidden contact or step order. "
        "Do not infer that a step occurred because a later state would normally require it. "
        "For movement or order, require direct temporal evidence in these frames. "
        "Missing or low-confidence masks are unknown, not proof of failure. "
        "completed=true means this step's action and completion checks are directly supported "
        "in the supplied window; otherwise completed=false and explain the evidence gap. "
        "Do not claim pixel thresholds are met by visually guessing them. "
        "Never claim to override rules. Reason: at most two short sentences about this step only.\n"
        + json.dumps(
            {
                "target_step": step.model_dump(),
                "rule_event": event.model_dump(),
                "frame_timestamps_s": times,
                "measurements": observations,
            }
        )
    )
