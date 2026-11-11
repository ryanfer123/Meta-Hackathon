"""A tracking choice is scoped to one authorized job, with no budget changes."""

import json

import pytest
from app import main
from app.config import Settings
from app.main import create_app
from app.samples import sample_protocol
from fastapi.testclient import TestClient


@pytest.mark.parametrize("route", ["run", "validate"])
@pytest.mark.parametrize("mode", [None, "image", "video", "invalid"])
def test_tracking_choice_scoped_to_job(tmp_path, monkeypatch, route, mode):
    job = "a" * 32
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "original.mp4").write_bytes(b"mock-original")
    protocol = sample_protocol()
    (folder / "protocol.json").write_text(protocol.model_dump_json(by_alias=True))
    config = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auth_required=False,
        replay_mode=False,
        model_api_key="mock-no-network",
        sam_mode="image",
        max_run_cost_usd=0.25,
    )
    observed = []
    monkeypatch.setattr(main, "process_run", lambda *args: observed.append(args[0]))
    monkeypatch.setattr(main, "process_validation", lambda *args: observed.append(args[0]))
    monkeypatch.setattr(main, "probe_video", lambda *_: {"duration_s": 20})
    data = {} if mode is None else {"tracking_mode": mode}
    if route == "run":
        url, field = "/api/runs", "video"
        data["protocol_id"] = job
    else:
        url, field = f"/api/protocols/{job}/validate", "heldout"
        data.update(
            ranges_confirmed="true",
            ranges=json.dumps(
                {s.id: {"start": i * 3, "end": i * 3 + 2} for i, s in enumerate(protocol.steps)}
            ),
        )
    with TestClient(create_app(config)) as api:
        response = api.post(url, data=data, files={field: ("input.mp4", b"mock", "video/mp4")})
    assert response.status_code == (422 if mode == "invalid" else 202)
    if mode == "invalid":
        assert not observed
    else:
        assert observed[0].sam_mode == (mode or "image")
        assert observed[0].max_run_cost_usd == 0.25
        assert observed[0].auth_required is False
    assert config.sam_mode == "image"


def test_fast_tracking_cannot_bypass_auth(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, auth_required=True)
    with TestClient(create_app(settings)) as api:
        assert api.post("/api/runs", data={"tracking_mode": "video"}).status_code == 401
