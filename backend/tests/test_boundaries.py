import json

from app.config import Settings
from app.learn.boundaries import suggest_boundaries
from app.main import create_app
from app.samples import sample_protocol
from app.schemas import TranscriptTurn
from fastapi.testclient import TestClient


def turn(start, end, text):
    return TranscriptTurn(start=start, end=end, text=text)


def test_unique_narration_suggests_padded_times_without_verifying_protocol():
    protocol = sample_protocol()
    suggestions = suggest_boundaries(
        protocol,
        [
            turn(2, 4, "Position the dropper at the blue tube"),
            turn(8, 10, "Bring the blue cap to tube 1"),
        ],
        20,
    )
    assert suggestions["approach"].model_dump() == {"start": 1.5, "end": 4.5}
    assert suggestions["cap"].model_dump() == {"start": 7.5, "end": 10.5}
    assert "label" not in suggestions
    assert not protocol.verified


def test_ambiguous_repeated_compound_negative_or_out_of_clip_narration_is_unassigned():
    protocol = sample_protocol()
    for turns in [
        [turn(1, 2, "Bring the blue cap to tube 1"), turn(6, 7, "Bring the blue cap to tube 1")],
        [turn(1, 2, "Bring the blue cap to tube 1 and place the label on tube 1")],
        [
            turn(1, 2, "Bring the blue cap to tube 1 and place the label on tube 1"),
            turn(6, 7, "Bring the blue cap to tube 1"),
        ],
        [turn(1, 2, "Do not bring the blue cap to tube 1")],
        [turn(20, 22, "Bring the blue cap to tube 1")],
        [turn(1, 2, "tube 1")],
    ]:
        assert suggest_boundaries(protocol, turns, 10) == {}


def test_overlapping_proposals_stay_unassigned():
    assert (
        suggest_boundaries(
            sample_protocol(),
            [
                turn(2, 4, "Position the dropper at the blue tube"),
                turn(4.5, 6, "Bring the blue cap to tube 1"),
            ],
            20,
        )
        == {}
    )


def test_learn_saves_original_narration_and_proposals(tmp_path, monkeypatch):
    from app import service

    job = "learn-narration"
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    frames = [(0.0, folder / "0.jpg"), (10.0, folder / "10.jpg")]
    monkeypatch.setattr(service, "sample", lambda *_: frames)
    monkeypatch.setattr(service, "keyframes", lambda *_: [])
    monkeypatch.setattr(service, "compile_protocol", lambda *_: sample_protocol())
    monkeypatch.setattr(
        service, "transcribe", lambda *_: (_ for _ in ()).throw(AssertionError("no network"))
    )
    turns = [turn(2, 4, "Bring the blue cap to tube 1")]
    service.process_learn(Settings(_env_file=None, data_dir=tmp_path), job, turns)
    status = json.loads((folder / "status.json").read_text())
    assert status["status"] == "ready"
    assert status["boundary_suggestions"]["cap"] == {"start": 1.5, "end": 4.5}
    assert json.loads((folder / "narration.json").read_text()) == [turns[0].model_dump()]
    assert status["validation"] is None
    assert not status["protocol"]["verified"]


def test_validation_rejects_unconfirmed_or_missing_times_before_paid_work(tmp_path):
    job = "a" * 32
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "protocol.json").write_text(sample_protocol().model_dump_json(by_alias=True))
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auth_required=False,
        replay_mode=False,
        model_api_key="mock-only",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            f"/api/protocols/{job}/validate",
            data={"ranges": "{}"},
            files={"heldout": ("clip.mp4", b"mock", "video/mp4")},
        )
        assert response.status_code == 422
        assert "confirm" in response.json()["detail"]
        response = client.post(
            f"/api/protocols/{job}/validate",
            data={"ranges": "{}", "ranges_confirmed": "true"},
            files={"heldout": ("clip.mp4", b"mock", "video/mp4")},
        )
        assert response.status_code == 422
        assert "every protocol step" in response.json()["detail"]
    assert not (folder / "heldout.mp4").exists()
    assert not (tmp_path / "runs").exists()


def test_private_archive_roundtrips_narration_and_boundary_review(tmp_path, monkeypatch):
    import httpx
    from app.cloud import CloudJobs

    owner = "11111111-1111-4111-8111-111111111111"
    store = CloudJobs(
        Settings(_env_file=None, supabase_url="https://test.supabase.co"), "mock-token", owner
    )
    source = tmp_path / "source"
    source.mkdir()
    (source / "status.json").write_text('{"id":"test","status":"ready"}')
    for name in ("narration.json", "boundary_suggestions.json", "boundary_confirmation.json"):
        (source / name).write_text('{"test":"private-review"}')
    archive = b""

    def request(method, path, **kwargs):
        nonlocal archive
        if method == "POST" and "storage/" in path:
            archive = kwargs["content"]
        return httpx.Response(200, content=archive if method == "GET" else b"{}")

    monkeypatch.setattr(store, "request", request)
    monkeypatch.setattr(store, "get", lambda job: {"artifact_path": f"{owner}/{job}.zip"})
    store.archive("test", source, "learn")
    target = tmp_path / "target"
    assert store.restore("test", target)
    for name in ("narration.json", "boundary_suggestions.json", "boundary_confirmation.json"):
        assert (target / name).read_text() == (source / name).read_text()
    store.close()
