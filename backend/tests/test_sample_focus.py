"""Headline selection is metadata; the deterministic event log remains unchanged."""

import pytest
from app.audit.chain import build_chain, verify_entries
from app.learn.validate import replay
from app.samples import sample_frames, sample_protocol, sample_run


@pytest.mark.parametrize(
    ("name", "kind", "t", "step_id"),
    [
        ("skipped-cap", "skipped", 17.0, "cap"),
        ("wrong-tube", "wrong_object", 5.0, "approach"),
        ("slow-action", "dwell_exceeded", 7.5, "approach"),
        ("swapped-order", "skipped", 13.0, "cap"),
        ("occlusion", "uncertain", 12.5, "cap"),
        ("clean", None, None, None),
    ],
)
def test_sample_focus_matches_event_without_changing_chain(
    name: str, kind: str | None, t: float | None, step_id: str | None
) -> None:
    # The baseline has no presentation metadata: it is a fresh rules-only replay.
    baseline = replay(sample_protocol(), sample_frames(name))
    baseline_events = [event.model_dump() for event in baseline.events]
    baseline_chain, baseline_root = build_chain(baseline_events, {})

    run = sample_run(name)
    if kind is None:
        assert "focus" not in run
    else:
        assert run["focus"] == {"kind": kind, "t": t, "step_id": step_id}
        assert any(
            all(event[key] == value for key, value in run["focus"].items())
            for event in run["events"]
        )

    assert run["events"] == baseline_events
    chain, root = build_chain(run["events"], {})
    assert (chain, root) == (baseline_chain, baseline_root)
    assert verify_entries(chain, baseline_root)

    # Changing/removing focus cannot change or invalidate the event chain.
    run["focus"] = {"kind": "uncertain", "t": 0.0, "step_id": "presentation-only"}
    assert build_chain(run["events"], {}) == (baseline_chain, baseline_root)
    del run["focus"]
    assert build_chain(run["events"], {}) == (baseline_chain, baseline_root)
