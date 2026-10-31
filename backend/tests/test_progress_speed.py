"""Bounded I/O concurrency and honest stage progress; no provider calls."""

import json
from pathlib import Path
from threading import Barrier, Lock

import cv2
import httpx
import numpy as np
import pytest
from app.budget import BudgetExceeded
from app.config import Settings
from app.main import create_app
from app.meta_client import MetaClient
from app.progress import JobProgress, with_progress
from app.samples import sample_protocol
from app.track.sam import track
from fastapi.testclient import TestClient


def test_progress_estimates_from_stage_work_and_resets_between_stages(tmp_path, monkeypatch):
    from app import progress

    now = [100.0]
    monkeypatch.setattr(progress.time, "time", lambda: now[0])
    writer = JobProgress(tmp_path)
    writer.update("First video", 0, 10, "frames")
    assert with_progress({"status": "validating"}, tmp_path)["progress"]["eta_seconds"] is None
    now[0] = 120
    writer.update("First video", 2, 10, "frames")
    result = with_progress({"status": "processing"}, tmp_path)
    assert result["progress"]["eta_seconds"] == 80
    writer.update("Second video", 0, 20, "frames")
    assert with_progress({"status": "processing"}, tmp_path)["progress"]["eta_seconds"] is None
    assert with_progress({"status": "ready"}, tmp_path) == {"status": "ready"}
    assert with_progress({"status": "error"}, tmp_path) == {"status": "error"}


def test_progress_is_returned_on_private_job_status_routes(tmp_path):
    job = "a" * 32
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    for name in ("status.json", "run.json"):
        (folder / name).write_text(json.dumps({"status": "processing"}))
    JobProgress(folder).update("Finding objects", 3, 10, "frames")
    settings = Settings(_env_file=None, data_dir=tmp_path, auth_required=False)
    with TestClient(create_app(settings)) as api:
        for path in (f"/api/protocols/{job}", f"/api/runs/{job}"):
            response = api.get(path)
            assert response.status_code == 200
            assert response.json()["progress"]["completed"] == 3
    with TestClient(create_app(settings.model_copy(update={"auth_required": True}))) as api:
        assert api.get(f"/api/protocols/{job}").status_code == 401


def tracking_setup(tmp_path, workers, cap=100):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        replay_mode=False,
        model_api_key="mock-only",
        sam_image_workers=workers,
        max_sam_calls=cap,
    )
    protocol = sample_protocol()
    protocol = protocol.model_copy(update={"objects": protocol.objects[:3]})
    path = tmp_path / "frame.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.zeros((64, 64, 3), dtype=np.uint8))
    return settings, protocol, [(0.0, path), (0.5, path)]


def test_parallel_tracking_matches_serial_and_logs_every_reserved_request(tmp_path):
    wire = (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text()
    outputs = []
    for workers in (1, 3):
        settings, protocol, frames = tracking_setup(tmp_path / str(workers), workers)
        lock, barrier = Lock(), Barrier(workers)
        active = peak = 0

        def handler(request):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait(timeout=5)
            with lock:
                active -= 1
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [{"content": [{"type": "output_text", "text": wire}]}],
                },
            )

        client = MetaClient(settings, "job", httpx.MockTransport(handler))
        updates = []
        client.tracking_progress = lambda *args: updates.append(args)
        try:
            states = track(client, protocol, frames, "hash")
        finally:
            client.close()
        outputs.append(states)
        assert peak == workers
        assert updates == [(0, 2, "frames"), (1, 2, "frames"), (2, 2, "frames")]
        calls = [
            json.loads(line) for line in client.budget.log_path("job").read_text().splitlines()
        ]
        assert len(calls) == 6
        assert all(call["reserved_usd"] == 0.0025 for call in calls)
    for serial, parallel in zip(*outputs, strict=True):
        assert list(serial.objects) == list(parallel.objects)
        for name in serial.objects:
            assert serial.objects[name].score == parallel.objects[name].score
            assert np.array_equal(serial.objects[name].mask, parallel.objects[name].mask)


def test_parallel_tracking_cannot_overrun_atomic_budget(tmp_path):
    settings, protocol, frames = tracking_setup(tmp_path, 3, cap=2)
    wire = (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text()
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"content": [{"type": "output_text", "text": wire}]}],
            },
        )

    client = MetaClient(settings, "capped", httpx.MockTransport(handler))
    try:
        with pytest.raises(BudgetExceeded):
            track(client, protocol, frames, "hash")
    finally:
        client.close()
    assert len(requests) == 2


@pytest.mark.parametrize("workers", [0, 5])
def test_workers_are_bounded(workers):
    with pytest.raises(ValueError):
        Settings(_env_file=None, sam_image_workers=workers)


def test_hosted_progress_requires_owner_and_an_active_worker(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import UTC, datetime
    from threading import Event

    from app import main
    from fastapi import HTTPException

    ready, release = Event(), Event()
    rows = {}
    current_job = []

    async def authenticate(settings, header):
        if header == "Bearer owner":
            return "owner-id"
        if header == "Bearer peer":
            return "peer-id"
        raise HTTPException(401, "Sign in")

    class Cloud:
        def __init__(self, settings, token, owner):
            self.owner = owner

        def begin(self, job, kind, existing=False):
            rows[job] = {
                "owner": self.owner,
                "status": "processing",
                "created_at": datetime.now(UTC).isoformat(),
                "result": {"status": "processing"},
            }

        def get(self, job):
            return rows.get(job) if rows.get(job, {}).get("owner") == self.owner else None

        def archive(self, job, folder, kind):
            rows[job]["status"] = "ready"
            rows[job]["result"] = {"status": "ready"}

        def close(self):
            pass

    def operation(settings, job, *args):
        JobProgress(settings.data_dir / "jobs" / job).update("Finding objects", 2, 8, "frames")
        current_job.append(job)
        ready.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr(main, "authenticate", authenticate)
    monkeypatch.setattr(main, "CloudJobs", Cloud)
    monkeypatch.setattr(main, "process_learn", operation)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        cloud_jobs=True,
        replay_mode=False,
        model_api_key="mock-only",
    )
    with TestClient(create_app(settings)) as api, ThreadPoolExecutor(max_workers=1) as pool:
        upload = pool.submit(
            lambda: api.post(
                "/api/protocols",
                headers={"Authorization": "Bearer owner"},
                files={"video": ("video.mp4", b"mock-video", "video/mp4")},
            )
        )
        try:
            assert ready.wait(timeout=5)
            path = f"/api/protocols/{current_job[0]}"
            result = api.get(path, headers={"Authorization": "Bearer owner"})
            assert result.json()["progress"]["completed"] == 2
            assert api.get(path, headers={"Authorization": "Bearer peer"}).status_code == 404
        finally:
            release.set()
        assert upload.result(timeout=5).status_code == 202
        assert "progress" not in api.get(path, headers={"Authorization": "Bearer owner"}).json()
