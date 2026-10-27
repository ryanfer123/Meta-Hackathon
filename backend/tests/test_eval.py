import json

import pytest

from eval.run_eval import evaluate, freeze, match_events, wilson


def test_one_prediction_cannot_match_two_labels():
    t = [{"kind": "skipped", "step_id": "a", "t": 1}, {"kind": "skipped", "step_id": "a", "t": 2}]
    assert match_events(t, t[:1]) == (1, 0, 1)


def test_matching_uses_augmenting_paths():
    truth = [
        {"kind": "skipped", "step_id": "a", "t": 2},
        {"kind": "skipped", "step_id": "a", "t": 0},
    ]
    pred = [
        {"kind": "skipped", "step_id": "a", "t": 1},
        {"kind": "skipped", "step_id": "a", "t": 3},
    ]
    assert match_events(truth, pred, 1) == (2, 0, 0)


@pytest.mark.parametrize("difference", ["kind", "step_id", "t"])
def test_event_identity_and_tolerance(difference):
    truth = {"kind": "skipped", "step_id": "a", "t": 1}
    pred = {**truth, difference: {"kind": "uncertain", "step_id": "b", "t": 4}[difference]}
    assert match_events([truth], [pred]) == (0, 1, 1)


def test_empty_eval_cannot_generate_success(tmp_path):
    m = tmp_path / "labels.json"
    m.write_text(json.dumps({"runs": []}))
    with pytest.raises(ValueError):
        evaluate(m, tmp_path / "frozen.json", tmp_path / "out.md")
    with pytest.raises(ValueError):
        freeze(m, {"runs": []})
    assert not (tmp_path / "out.md").exists()


def test_wilson_small_sample_not_overconfident():
    assert wilson(0, 0) == "N/A"
    assert wilson(1, 1) == "[0.207, 1.000]"
