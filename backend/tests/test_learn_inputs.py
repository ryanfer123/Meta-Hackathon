"""Narration and timing input guards; all media/model edges are mocked."""

import json

import pytest
from app.config import Settings
from app.learn.boundaries import validate_step_ranges
from app.learn.validate import StepRange
from app.main import create_app
from app.samples import sample_protocol
from app.schemas import TranscriptTurn
from fastapi.testclient import TestClient


def settings(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        auth_required=False,
        replay_mode=False,
        model_api_key="mock-no-network",
    )


def valid_ranges():
    return {
        step.id: StepRange(start=float(index * 3), end=float(index * 3 + 2))
        for index, step in enumerate(sample_protocol().steps)
    }


@pytest.mark.parametrize("source", ["plain", "json", "audio"])
def test_learn_narration_precedence_and_actual_full_duration(tmp_path, monkeypatch, source):
    from app import service

    job = "learn-inputs"
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    calls = []
    frames = [(0.0, folder / "first.jpg"), (9.5, folder / "last.jpg")]
    monkeypatch.setattr(service, "sample", lambda *_: frames)
    monkeypatch.setattr(service, "keyframes", lambda *_: [])

    def probe(*_):
        calls.append("probe")
        return {"duration_s": 10.25}

    monkeypatch.setattr(service, "probe_video", probe)
    monkeypatch.setattr(service, "extract_audio", lambda *_: calls.append("extract"))
    audio_turns = [TranscriptTurn(start=2, end=3, text="Actual audio narration")]
    monkeypatch.setattr(service, "transcribe", lambda *_: (calls.append("asr"), audio_turns)[1])
    seen = []
    monkeypatch.setattr(
        service,
        "compile_protocol",
        lambda client, paths, turns: (seen.extend(turns), sample_protocol())[1],
    )
    supplied = (
        [TranscriptTurn(start=1, end=4, text="Supplied timestamped narration")]
        if source == "json"
        else []
    )
    plain = "  Explain the whole procedure  " if source != "audio" else "  "
    service.process_learn(settings(tmp_path), job, supplied, plain)
    status = json.loads((folder / "status.json").read_text())
    assert status["status"] == "ready"
    assert not status["protocol"]["verified"]
    if source == "plain":
        assert seen == [TranscriptTurn(start=0, end=10.25, text="Explain the whole procedure")]
        assert calls == ["probe"]
    elif source == "json":
        assert seen == supplied
        assert calls == []
    else:
        assert seen == audio_turns
        assert calls == ["extract", "asr"]
    assert json.loads((folder / "narration.json").read_text()) == [
        turn.model_dump() for turn in seen
    ]


def test_api_accepts_plain_narration_and_rejects_over_4000_before_job_creation(
    tmp_path, monkeypatch
):
    from app import main

    observed = []
    monkeypatch.setattr(main, "process_learn", lambda *args: observed.append(args))
    with TestClient(create_app(settings(tmp_path))) as client:
        too_long = client.post(
            "/api/protocols",
            data={"narration_text": "a" * 4001},
            files={"video": ("expert.mp4", b"mock", "video/mp4")},
        )
        assert too_long.status_code == 422
        assert observed == []
        assert not (tmp_path / "jobs").exists() or not list((tmp_path / "jobs").iterdir())
        accepted = client.post(
            "/api/protocols",
            data={"narration_text": "a" * 4000},
            files={"video": ("expert.mp4", b"mock", "video/mp4")},
        )
        assert accepted.status_code == 202
        assert observed[0][2] == []
        assert observed[0][3] == "a" * 4000


def test_worker_rejects_oversized_plain_narration_before_sampling_or_compile(tmp_path, monkeypatch):
    from app import service

    folder = tmp_path / "jobs" / "too-long"
    folder.mkdir(parents=True)
    monkeypatch.setattr(service, "sample", lambda *_: pytest.fail("must reject before sampling"))
    monkeypatch.setattr(service, "compile_protocol", lambda *_: pytest.fail("no paid compile"))
    service.process_learn(settings(tmp_path), "too-long", [], "a" * 4001)
    status = json.loads((folder / "status.json").read_text())
    assert status["status"] == "error"
    assert "4000" in status["error"]


def test_actual_duration_boundary_is_inclusive_and_errors_name_the_step():
    protocol = sample_protocol()
    ranges = valid_ranges()
    ranges["label"] = StepRange(start=9, end=10.25)
    validate_step_ranges(protocol, ranges, 10.25)
    ranges["label"] = StepRange(start=9, end=10.251)
    with pytest.raises(ValueError, match="Place the label.*10.25 seconds"):
        validate_step_ranges(protocol, ranges, 10.25)


@pytest.mark.parametrize("count", [1, 4])
def test_identical_zero_one_placeholders_are_rejected_even_when_confirmed(count):
    protocol = sample_protocol().model_copy(update={"steps": sample_protocol().steps[:count]})
    ranges = {step.id: StepRange(start=0, end=1) for step in protocol.steps}
    with pytest.raises(ValueError, match="placeholders"):
        validate_step_ranges(protocol, ranges, 20)


@pytest.mark.parametrize("bad", ["outside", "placeholders", "reversed"])
def test_api_rejects_bad_ranges_before_upload_or_model_work(tmp_path, monkeypatch, bad):
    from app import main

    job = "b" * 32
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "protocol.json").write_text(sample_protocol().model_dump_json(by_alias=True))
    monkeypatch.setattr(main, "probe_video", lambda *_: {"duration_s": 12.0})
    monkeypatch.setattr(main, "process_validation", lambda *_: pytest.fail("no paid validation"))
    ranges = {key: value.model_dump() for key, value in valid_ranges().items()}
    if bad == "outside":
        ranges["cap"] = {"start": 6, "end": 12.1}
    elif bad == "reversed":
        ranges["cap"] = {"start": 7, "end": 6}
    else:
        ranges = {key: {"start": 0, "end": 1} for key in ranges}
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            f"/api/protocols/{job}/validate",
            data={"ranges": json.dumps(ranges), "ranges_confirmed": "true"},
            files={"heldout": ("heldout.mp4", b"mock", "video/mp4")},
        )
        assert response.status_code == 422
        assert (
            "Cap tube 1" in response.json()["detail"]
            if bad != "placeholders"
            else "placeholders" in response.json()["detail"]
        )
    assert not (folder / "heldout.mp4").exists()
    assert not (folder / "boundary_confirmation.json").exists()
    assert not (tmp_path / "runs").exists()


def test_api_allows_reviewed_end_exactly_at_actual_duration(tmp_path, monkeypatch):
    from app import main

    job = "c" * 32
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "protocol.json").write_text(sample_protocol().model_dump_json(by_alias=True))
    monkeypatch.setattr(main, "probe_video", lambda *_: {"duration_s": 11.0})
    observed = []
    monkeypatch.setattr(main, "process_validation", lambda *args: observed.append(args))
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            f"/api/protocols/{job}/validate",
            data={
                "ranges": json.dumps(
                    {key: value.model_dump() for key, value in valid_ranges().items()}
                ),
                "ranges_confirmed": "true",
            },
            files={"heldout": ("heldout.mp4", b"mock", "video/mp4")},
        )
        assert response.status_code == 202
    assert observed[0][2]["label"].end == 11


@pytest.mark.parametrize("bad", ["outside", "placeholders", "incomplete"])
def test_worker_refuses_invalid_ranges_before_tracking(tmp_path, monkeypatch, bad):
    from app import service

    job = "guarded-validation"
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "original.mp4").write_bytes(b"compile")
    (folder / "heldout.mp4").write_bytes(b"heldout")
    (folder / "protocol.json").write_text(sample_protocol().model_dump_json(by_alias=True))
    monkeypatch.setattr(service, "probe_video", lambda *_: {"duration_s": 12.0})
    monkeypatch.setattr(
        service, "sample", lambda *_: pytest.fail("refuse before sampling/tracking")
    )
    monkeypatch.setattr(service, "track", lambda *_: pytest.fail("no paid tracking"))
    monkeypatch.setattr(service, "track_video", lambda *_: pytest.fail("no paid tracking"))
    ranges = valid_ranges()
    if bad == "outside":
        ranges["cap"] = StepRange(start=6, end=12.1)
    elif bad == "placeholders":
        ranges = {key: StepRange(start=0, end=1) for key in ranges}
    else:
        ranges = {}
    service.process_validation(settings(tmp_path), job, ranges, False)
    status = json.loads((folder / "status.json").read_text())
    assert status["status"] == "error"
    assert not (folder / "self_check.json").exists()
