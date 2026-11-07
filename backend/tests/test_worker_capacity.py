"""Protect the small worker before uploads or paid processing; no network."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from app import main
from app.config import Settings
from fastapi.testclient import TestClient


def test_worker_refuses_overlapping_work_and_releases_slot_after_failure(tmp_path, monkeypatch):
    started, release = Event(), Event()
    calls = []

    def operation(settings, job, *args):
        calls.append(job)
        started.set()
        assert release.wait(timeout=10)
        raise RuntimeError("test operation failed")

    monkeypatch.setattr(main, "process_learn", operation)
    config = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auth_required=False,
        replay_mode=False,
        model_api_key="mock-only",
    )
    with TestClient(main.create_app(config), raise_server_exceptions=False) as api:
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(
                api.post, "/api/protocols", files={"video": ("teaching.mp4", b"test")}
            )
            assert started.wait(timeout=5)
            try:
                refused = api.post("/api/protocols", files={"video": ("other.mp4", b"test")})
                assert refused.status_code == 503
                assert refused.headers["retry-after"] == "30"
                assert "no analysis was started" in refused.json()["detail"]
                assert len(calls) == 1
                assert len(list((tmp_path / "jobs").iterdir())) == 1
                assert api.get("/api/samples").status_code == 200
            finally:
                release.set()
                first.result(timeout=5)

        def complete(settings, job, *args):
            calls.append(job)
            (settings.data_dir / "jobs" / job / "status.json").write_text(
                json.dumps({"id": job, "status": "ready"})
            )

        monkeypatch.setattr(main, "process_learn", complete)
        accepted = api.post("/api/protocols", files={"video": ("retry.mp4", b"test")})
        assert accepted.status_code == 202
        assert len(calls) == 2


def test_persistence_refusal_does_not_leak_worker_slot(tmp_path, monkeypatch):
    attempts = []

    class Cloud:
        def __init__(self, *args):
            pass

        def begin(self, *args):
            attempts.append(args)
            if len(attempts) == 1:
                raise RuntimeError("Test persistence refusal")

        def archive(self, *args):
            pass

        def close(self):
            pass

    monkeypatch.setattr(main, "CloudJobs", Cloud)
    monkeypatch.setattr(main, "process_learn", lambda *args: None)
    config = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auth_required=False,
        cloud_jobs=True,
        replay_mode=False,
        model_api_key="mock-only",
    )
    with TestClient(main.create_app(config)) as api:
        assert api.post("/api/protocols", files={"video": ("a.mp4", b"test")}).status_code == 409
        assert api.post("/api/protocols", files={"video": ("b.mp4", b"test")}).status_code == 202
    assert len(attempts) == 2
