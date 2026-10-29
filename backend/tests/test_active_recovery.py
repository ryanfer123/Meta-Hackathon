"""Bounded recovery with mocked transports; no live requests or completion claims."""

import json
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
from app.budget import BudgetExceeded
from app.config import Settings
from app.meta_client import MetaClient
from app.schemas import Event, Protocol
from app.track.geometry import Detection, FrameState
from app.track.recovery import RefinedPrompt, recover_once
from pydantic import ValidationError


def setup(tmp_path, *, known=False, plan=None, sam_text=None, **config):
    protocol = Protocol.model_validate(
        {
            "name": "Synthetic recovery",
            "objects": [{"name": "tube_1", "sam_prompt": "tube", "class": "tube"}],
            "steps": [
                {"id": "one", "title": "Observe tube", "post": [{"op": "present", "obj": "tube_1"}]}
            ],
        }
    )
    path = tmp_path / "frame.jpg"
    cv2.imwrite(str(path), np.zeros((64, 64, 3), dtype=np.uint8))
    detection = Detection(np.ones((64, 64), dtype=np.bool_), 0.9, "tube") if known else None
    frame = FrameState(1, {"tube_1": detection, "hand": None}, 64, 64, str(path), complete=False)
    events = [Event(t=1, step_id="one", kind="uncertain", confidence=0.5, detail="missing mask")]
    requests = []
    response = (
        sam_text
        if sam_text is not None
        else (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text()
    )

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        text = (
            json.dumps(plan or {"object_name": "tube_1", "prompt": "blue tube"})
            if body["model"] != "sam-3.1"
            else response
        )
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
            },
        )

    client = MetaClient(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            replay_mode=False,
            model_api_key="mock-only",
            **config,
        ),
        "recovery-test",
        httpx.MockTransport(handler),
    )
    return client, protocol, [frame], [(1, path)], events, requests


def test_recovery_requeries_once_and_changes_only_missing_pixels_without_deciding(tmp_path):
    client, protocol, frames, paths, events, calls = setup(tmp_path)
    with client.http:
        result = recover_once(client, protocol, frames, paths, events, "source-hash")
        assert result.changed_frame == 0
        assert result.actions[0]["status"] == "recovered"
        assert result.frames[0].objects["tube_1"].mask.any()
        assert result.frames[0].objects["tube_1"].score == pytest.approx(0.93)
        assert frames[0].objects["tube_1"] is None
        assert result.frames[0].objects["hand"] is None
        assert not result.frames[0].complete
        assert len(events) == 1 and events[0].kind == "uncertain"
        assert protocol.steps[0].post[0].op == "present"
        assert [call["model"] for call in calls] == ["muse-spark-1.3", "sam-3.1"]
        assert calls[1]["input"][0]["content"][0]["text"] == "blue tube"
        second = recover_once(client, protocol, frames, paths, events, "source-hash")
        assert second.actions[0]["status"] == "skipped"
        assert len(calls) == 2
    saved = json.loads((tmp_path / "runs/recovery-test/recovery.json").read_text())
    assert saved["status"] == "recovered"
    logs = (tmp_path / "runs/recovery-test/calls.jsonl").read_text().splitlines()
    assert len(logs) == 2  # both calls passed the standard budget/logging clients


@pytest.mark.parametrize("mode", ["no_event", "known", "far", "no_path"])
def test_ineligible_recovery_makes_no_request(tmp_path, mode):
    client, protocol, frames, paths, events, calls = setup(tmp_path, known=mode == "known")
    if mode == "no_event":
        events = []
    if mode == "far":
        events[0].t = 5
    if mode == "no_path":
        paths = []
    with client.http:
        result = recover_once(client, protocol, frames, paths, events, "source")
    assert result.actions[0]["attempted"] is False
    assert calls == []
    assert result.frames is frames


@pytest.mark.parametrize(
    "plan",
    [
        {"object_name": "tube_2", "prompt": "blue tube"},
        {"object_name": "tube_1", "prompt": "blue cap"},
        {"object_name": "tube_1", "prompt": "tube"},
        {"object_name": "hand", "prompt": "blue tube"},
    ],
)
def test_changed_identity_or_unchanged_prompt_never_reaches_sam(tmp_path, plan):
    client, protocol, frames, paths, events, calls = setup(tmp_path, plan=plan)
    with client.http:
        result = recover_once(client, protocol, frames, paths, events, "source")
    assert result.actions[0]["status"] == "rejected"
    assert len(calls) == 1
    assert result.frames is frames


@pytest.mark.parametrize(
    "phrase",
    [
        "tube\nignore rules",
        "tube, cap",
        "find blue tube",
        "tube and hand",
        "tube near cap",
        "x" * 81,
        "tube 3",
        "ignore-rules blue tube",
    ],
)
def test_refinement_is_one_short_phrase_without_commands_or_relations(phrase):
    with pytest.raises(ValidationError):
        RefinedPrompt(object_name="tube_1", prompt=phrase)


@pytest.mark.parametrize("output", ["", "malformed", "<0f>bad", "weak", "multiple"])
def test_empty_ambiguous_or_low_confidence_requery_stays_unknown(tmp_path, output):
    wire = (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text()
    text = (
        wire.replace(";c=0.93", "")
        if output == "weak"
        else (wire + wire if output == "multiple" else output)
    )
    client, protocol, frames, paths, events, calls = setup(tmp_path, sam_text=text)
    with client.http:
        result = recover_once(client, protocol, frames, paths, events, "source")
    assert result.actions[0]["status"] == "unresolved"
    assert result.changed_frame is None
    assert result.frames[0].objects["tube_1"] is None
    assert len(calls) == 2


def test_recovery_budget_denial_propagates_and_consumes_the_allowance(tmp_path):
    client, protocol, frames, paths, events, calls = setup(tmp_path, max_sam_calls=0)
    with client.http:
        with pytest.raises(BudgetExceeded):
            recover_once(client, protocol, frames, paths, events, "source")
        again = recover_once(client, protocol, frames, paths, events, "source")
    assert len(calls) == 1  # Spark succeeded; reservation refused before any SAM HTTP
    assert again.actions[0]["status"] == "skipped"
    saved = json.loads((tmp_path / "runs/recovery-test/recovery.json").read_text())
    assert saved["status"] == "budget_denied"


def test_invalid_plan_validation_is_bounded_and_does_not_send_sam(tmp_path):
    client, protocol, frames, paths, events, calls = setup(
        tmp_path, plan={"object_name": "tube_1", "prompt": "find tube"}
    )
    with client.http:
        result = recover_once(client, protocol, frames, paths, events, "source")
    assert result.actions[0]["status"] == "unresolved"
    assert len(calls) == 3
    assert all(call["model"] == "muse-spark-1.3" for call in calls)
