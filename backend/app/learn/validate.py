from dataclasses import replace

from pydantic import Field

from app.predicates import evaluate
from app.schemas import Protocol, StrictModel
from app.supervise.state_machine import Supervisor
from app.track.geometry import FrameState


class StepRange(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)


def replay(protocol: Protocol, frames: list[FrameState]) -> Supervisor:
    supervisor = Supervisor(protocol)
    for frame in frames:
        supervisor.tick(frame)
    supervisor.finish()
    return supervisor


def clean(protocol: Protocol, frames: list[FrameState]) -> bool:
    return clean_engine(replay(protocol, frames))


def clean_engine(engine: Supervisor) -> bool:
    return all(s.status == "DONE" for s in engine.states.values()) and all(
        e.kind in ("step_started", "step_completed") for e in engine.events
    )


def rebase(frames: list[FrameState], fps: float = 2) -> list[FrameState]:
    return [replace(f, t=i / fps, interactions={}) for i, f in enumerate(frames)]


def mutate(
    frames: list[FrameState],
    ranges: dict[str, StepRange],
    step_id: str,
    swap_with: str | None = None,
) -> list[FrameState]:
    a = ranges[step_id]
    if a.end <= a.start:
        raise ValueError("invalid step range")
    if swap_with is None:
        return rebase([f for f in frames if not a.start <= f.t <= a.end])
    b = ranges[swap_with]
    if a.end >= b.start:
        raise ValueError("swap ranges must be ordered and nonoverlapping")
    first = [f for f in frames if a.start <= f.t <= a.end]
    second = [f for f in frames if b.start <= f.t <= b.end]
    middle = [f for f in frames if a.end < f.t < b.start]
    before = [f for f in frames if f.t < a.start]
    after = [f for f in frames if f.t > b.end]
    return rebase(before + second + middle + first + after)


def validate_protocol(
    protocol: Protocol,
    expert_a: list[FrameState],
    expert_b: list[FrameState],
    ranges: dict[str, StepRange],
) -> dict[str, object]:
    if set(ranges) != {s.id for s in protocol.steps}:
        raise ValueError("explicit timestamp ranges required for every step")
    discriminative: dict[str, bool] = {}
    for step in protocol.steps:
        r = ranges[step.id]
        if r.end <= r.start:
            raise ValueError("range end must follow start")
        before = [f for f in expert_a if f.t <= r.start]
        after = [f for f in expert_a if f.t <= r.end]
        start_vals = [evaluate(p, before, r.start) for p in step.post]
        end_vals = [evaluate(p, after, r.end) for p in step.post]
        discriminative[step.id] = any(not v and c >= 0.7 for v, c, _ in start_vals) and all(
            v and c >= 0.7 for v, c, _ in end_vals
        )
    controls: list[dict[str, object]] = []
    steps = protocol.steps
    for step in steps:
        # A cut-only mutation may retain a lasting postcondition later in the video.
        # If so it must fail validation, not be relabelled a successful negative control.
        engine = replay(protocol, mutate(expert_a, ranges, step.id))
        caught = any(
            e.step_id == step.id and e.kind in ("skipped", "out_of_order") for e in engine.events
        )
        controls.append(
            {
                "mutation": "cut",
                "step": step.id,
                "flagged": caught,
                "eligible": step.critical and step != steps[-1],
            }
        )
    for a, b in zip(steps, steps[1:]):
        if a.group is not None and a.group == b.group:
            continue
        engine = replay(protocol, mutate(expert_a, ranges, a.id, b.id))
        caught = any(e.kind == "out_of_order" for e in engine.events)
        controls.append(
            {
                "mutation": "swap",
                "step": a.id,
                "swap_with": b.id,
                "flagged": caught,
                "eligible": protocol.order_strict,
            }
        )
    eligible = [c for c in controls if c["eligible"]]
    compile_engine = replay(protocol, expert_a)
    held_out_engine = replay(protocol, expert_b)
    checks = {
        "discriminative": all(discriminative.values()),
        "compile_replay": clean_engine(compile_engine),
        "held_out": bool(expert_b) and clean_engine(held_out_engine),
        "counterfactual": bool(eligible) and all(bool(c["flagged"]) for c in eligible),
    }
    trace: dict[str, list[dict[str, object]]] = {}
    for step in protocol.steps:
        trace[step.id] = []
        for i in range(0, len(expert_a), max(1, len(expert_a) // 12)):
            frame = expert_a[i]
            values = [evaluate(p, expert_a[: i + 1], frame.t) for p in step.post]
            trace[step.id].append({"t": frame.t, "post": values})
    protocol.verified = all(checks.values())
    return {
        "checks": checks,
        "replay_states": {
            "compile_replay": {key: state.status for key, state in compile_engine.states.items()},
            "held_out": {key: state.status for key, state in held_out_engine.states.items()},
        },
        "steps": discriminative,
        "predicate_trace": trace,
        "counterfactuals": controls,
        "verified": protocol.verified,
        "repair_rounds": 0,
        "scope": "observed geometry only; end-of-recording omission remains uncertain",
    }
