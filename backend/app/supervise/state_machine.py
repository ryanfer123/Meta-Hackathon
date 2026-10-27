from dataclasses import dataclass, field
from typing import Literal

from app.predicates import evaluate, stable
from app.schemas import Event, Near, Protocol, Step, Touching
from app.track.geometry import FrameState

Status = Literal["PENDING", "ACTIVE", "DONE", "SKIPPED"]


@dataclass
class StepState:
    status: Status = "PENDING"
    started: float | None = None
    baseline: bool = False
    action_seen: bool = False
    uncertain_frames: int = 0
    emitted: set[str] = field(default_factory=set)


class Supervisor:
    """Replayable rule engine. Advisory model opinions never mutate this object."""

    def __init__(self, protocol: Protocol, smoothing: int = 3) -> None:
        if not 1 <= smoothing <= 10:
            raise ValueError("smoothing must be between 1 and 10 frames")
        self.protocol = protocol
        self.smoothing = smoothing
        self.states = {s.id: StepState() for s in protocol.steps}
        self.window: list[FrameState] = []
        self.events: list[Event] = []
        self.ranks: dict[str, int] = {}
        rank = -1
        last_group: str | None = None
        for step in protocol.steps:
            if step.group is None or step.group != last_group:
                rank += 1
            self.ranks[step.id] = rank
            last_group = step.group

    def emit(
        self, frame: FrameState, step: Step, kind: str, detail: str, confidence: float = 1
    ) -> None:
        state = self.states[step.id]
        if kind in state.emitted:
            return
        state.emitted.add(kind)
        self.events.append(
            Event(
                t=frame.t,
                step_id=step.id,
                kind=kind,  # type: ignore[arg-type]
                confidence=confidence,
                evidence_frame=frame.evidence_frame,
                detail=detail,
            )
        )

    def earlier(self, step: Step) -> list[Step]:
        return [
            s
            for s in self.protocol.steps
            if self.ranks[s.id] < self.ranks[step.id]
            and s.critical
            and self.states[s.id].status not in ("DONE", "SKIPPED")
        ]

    def tick(self, frame: FrameState) -> list[Event]:
        if self.window and frame.t <= self.window[-1].t:
            raise ValueError("frame timestamps must be strictly increasing")
        if frame.width <= 0 or frame.height <= 0:
            raise ValueError("invalid frame dimensions")
        before = len(self.events)
        self.window.append(frame)
        for step in self.protocol.steps:
            state = self.states[step.id]
            if state.status in ("DONE", "SKIPPED"):
                continue
            raw = [evaluate(p, self.window, frame.t) for p in step.post]
            if any(not truth and c >= 0.7 for truth, c, _ in raw):
                state.baseline = True
            pre, _, _ = stable(step.pre, self.window, self.smoothing)
            action, _, _ = stable(step.action, self.window, self.smoothing)
            # Require both preconditions and action within this step's reachable interval.
            reachable = not self.earlier(step)
            if reachable and pre and state.status == "PENDING":
                state.status, state.started = "ACTIVE", frame.t
                self.emit(frame, step, "step_started", "Preconditions stably observed.")
            if reachable and pre and action:
                state.action_seen = True
            post, confidence, reason = stable(step.post, self.window, self.smoothing)
            if (
                post
                and state.baseline
                and (state.action_seen or action)
                and (state.started is not None or pre)
            ):
                earlier = self.earlier(step)
                for missed in earlier:
                    self.states[missed.id].status = "SKIPPED"
                    self.emit(frame, missed, "skipped", f"Later action {step.id} observed first.")
                if earlier and self.protocol.order_strict:
                    self.emit(frame, step, "out_of_order", "Earlier critical action not observed.")
                if state.started is None:
                    state.started = frame.t
                    self.emit(frame, step, "step_started", "Later step observed ahead of sequence.")
                dwell = frame.t - state.started
                if dwell < step.min_dwell_s:
                    self.emit(frame, step, "dwell_too_short", f"Dwell {dwell:.2f}s below minimum.")
                state.status = "DONE"
                self.emit(frame, step, "step_completed", reason, confidence)
                continue
            if state.status == "ACTIVE":
                assert state.started is not None
                if frame.t - state.started > step.max_dwell_s:
                    self.emit(frame, step, "dwell_exceeded", "Maximum observable dwell exceeded.")
                self.wrong_object(frame, step)
                if any(c < 0.7 for _, c, _ in raw):
                    state.uncertain_frames += 1
                    if state.uncertain_frames >= 4:
                        self.emit(
                            frame, step, "uncertain", "Occlusion or low-confidence evidence.", 0.5
                        )
                else:
                    state.uncertain_frames = 0
        return self.events[before:]

    def wrong_object(self, frame: FrameState, step: Step) -> None:
        classes = {o.name: o.obj_class for o in self.protocol.objects}
        for action in step.action + step.post:
            if not isinstance(action, (Touching, Near)):
                continue
            for alternate in self.protocol.objects:
                if (
                    alternate.name in (action.a, action.b)
                    or classes[alternate.name] != classes[action.b]
                ):
                    continue
                changed = action.model_copy(update={"b": alternate.name})
                truth, confidence, _ = stable([changed], self.window, self.smoothing)
                if truth:
                    self.emit(
                        frame,
                        step,
                        "wrong_object",
                        f"Expected {action.b}; observed {alternate.name}.",
                        confidence,
                    )

    def finish(self) -> list[Event]:
        before = len(self.events)
        if self.window:
            for step in self.protocol.steps:
                if self.states[step.id].status not in ("DONE", "SKIPPED"):
                    self.emit(
                        self.window[-1], step, "uncertain", "Recording ended before completion.", 0
                    )
        return self.events[before:]
