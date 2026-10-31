"""Diagnostics explain unknowns without turning final-state opinions into completion."""

import json
from dataclasses import replace

from app.audit.report import render_report
from app.samples import sample_frames, sample_protocol, sample_run
from app.schemas import Event, Present
from app.supervise.review_context import review_prompt
from app.supervise.state_machine import Supervisor


def test_finish_names_missing_evidence_and_blocking_step_without_changing_states():
    protocol = sample_protocol()
    engine = Supervisor(protocol)
    for frame in sample_frames("clean")[:3]:
        engine.tick(replace(frame, objects={name: None for name in frame.objects}))
    before = {key: state.status for key, state in engine.states.items()}
    events = engine.finish()
    assert "not stably satisfied" in events[0].detail
    assert "unobserved" in events[0].detail
    assert protocol.steps[0].title in events[1].detail
    assert all(event.kind == "uncertain" for event in events)
    assert before == {key: state.status for key, state in engine.states.items()}
    assert engine.finish() == []


def test_finish_identifies_already_true_completion_condition():
    protocol = sample_protocol()
    step = protocol.steps[0].model_copy(
        update={"pre": [], "action": [], "post": [Present(obj="dropper")]}
    )
    protocol = protocol.model_copy(update={"steps": [step]})
    engine = Supervisor(protocol)
    for frame in sample_frames("clean")[:4]:
        engine.tick(frame)
    assert "No clear before-to-after change" in engine.finish()[0].detail
    assert engine.states[step.id].status != "DONE"


def test_review_is_step_scoped_and_includes_unknown_measurements_and_timestamps():
    protocol = sample_protocol()
    frames = sample_frames("clean")[:4]
    frames = [replace(f, objects={}) for f in frames]
    step = protocol.steps[0]
    event = Event(t=frames[-1].t, step_id=step.id, kind="uncertain", confidence=0, detail="unknown")
    prompt = review_prompt(step, event, frames, [frames[-1].t])
    context = json.loads(prompt.split("\n", 1)[1])
    assert context["target_step"]["id"] == step.id
    assert "protocol" not in context
    assert context["frame_timestamps_s"] == [frames[-1].t]
    assert all(check["confidence"] == 0 for check in context["measurements"][0]["checks"])
    assert "does not prove earlier actions" in prompt
    assert "require direct temporal evidence" in prompt


def test_report_collapses_and_escapes_advisories_without_mutating_hashed_events():
    run = sample_run("clean")
    event = {
        "t": 1,
        "step_id": "cap",
        "kind": "uncertain",
        "tier": "glimmer",
        "detail": "<script>override</script>",
    }
    run["events"] = [event]
    before = json.dumps(run["events"])
    report = render_report(run, "trusted-root")
    assert "<summary>Read model opinion</summary>" in report
    assert "&lt;script&gt;override&lt;/script&gt;" in report
    assert "<script>override</script>" not in report
    assert "Rules remain unchanged" in report
    assert json.dumps(run["events"]) == before


def test_review_window_uses_observed_start_and_never_future_frames():
    from pathlib import Path

    from app.supervise.review_context import review_window

    paths = [(float(i), Path(f"{i}.jpg")) for i in range(20)]
    start = Event(t=2, step_id="cap", kind="step_started", confidence=1, detail="observed")
    event = Event(t=12, step_id="cap", kind="uncertain", confidence=0, detail="unknown")
    assert [t for t, _ in review_window(paths, [start, event], event)] == [2, 7, 12]
    assert [t for t, _ in review_window(paths, [], event)] == [11, 12]
