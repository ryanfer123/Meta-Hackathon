import json
from types import SimpleNamespace

import numpy as np
from app import main, service
from app.checkpoints import checkpoint_key, load_frames, save_frames
from app.config import Settings
from app.learn.frames import file_hash
from app.samples import sample_protocol
from app.track.geometry import Detection, FrameState
from fastapi.testclient import TestClient


def test_exact_checkpoint_restores_pixels_identity_absence_and_interactions(tmp_path):
    mask = np.zeros((17, 19), dtype=np.bool_)
    mask[3:7, 4:13] = True
    frame = FrameState(
        1.5,
        {
            "item": Detection(mask, 0.5, "part"),
            "unknown": None,
            "absent": Detection(None, 0.8, "part", True),
        },
        19,
        17,
        "old/path.jpg",
        False,
        {"item": 1.0},
    )
    path = tmp_path / "tracking.npz"
    save_frames(path, "key", [frame])
    assert load_frames(path, "different-inputs", [(1.5, tmp_path / "new.jpg")], 10000) is None
    loaded = load_frames(path, "key", [(1.5, tmp_path / "new.jpg")], 10000)[0]
    assert loaded.evidence_frame == str(tmp_path / "new.jpg")
    assert loaded.interactions == frame.interactions and not loaded.complete
    assert loaded.objects["unknown"] is None
    assert loaded.objects["absent"].known_absent
    assert loaded.objects["item"].score == 0.5
    np.testing.assert_array_equal(loaded.objects["item"].mask, mask)


def test_completed_tracking_is_reused_without_provider_calls(tmp_path, monkeypatch):
    config = Settings(_env_file=None, data_dir=tmp_path)
    video = tmp_path / "original.mp4"
    video.write_bytes(b"source")
    (tmp_path / "resume.json").write_text("{}")
    protocol = sample_protocol()
    paths = [(0.0, tmp_path / "frame.jpg")]
    expected = [FrameState(0, {"hand": None}, 16, 16)]
    calls = []
    monkeypatch.setattr(service, "track", lambda *a: (calls.append("tracking"), expected)[1])
    for _ in range(2):
        frames = service.tracked_stage(
            config,
            tmp_path,
            "tracking",
            SimpleNamespace(),
            protocol,
            video,
            paths,
            file_hash(video),
        )
        assert frames[0].objects == expected[0].objects
    assert calls == ["tracking"]
    before = checkpoint_key(config, protocol, video, False)
    protocol.objects[0].sam_prompt = "changed"
    assert checkpoint_key(config, protocol, video, False) != before


def test_resume_uses_same_job_budget_and_rejects_changed_sources(tmp_path, monkeypatch):
    job = "a" * 32
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    original = folder / "original.mp4"
    original.write_bytes(b"source")
    (folder / "resume.json").write_text(
        json.dumps(
            {
                "operation": "learn",
                "turns": [],
                "narration_text": "intent",
                "video_sha256": file_hash(original),
            }
        )
    )
    (folder / "status.json").write_text('{"status":"error"}')
    seen = []

    def process(settings, job_id, turns, text):
        seen.append((job_id, text))
        (folder / "status.json").write_text('{"status":"ready"}')

    monkeypatch.setattr(main, "process_learn", process)
    config = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auth_required=False,
        replay_mode=False,
        model_api_key="mock",
    )
    with TestClient(main.create_app(config)) as api:
        assert api.post(f"/api/jobs/{job}/resume").status_code == 202
        assert api.post(f"/api/jobs/{job}/resume").status_code == 409
        (folder / "status.json").write_text('{"status":"error"}')
        original.write_bytes(b"changed")
        assert api.post(f"/api/jobs/{job}/resume").status_code == 409
        assert api.post("/api/jobs/sample-clean/resume").status_code == 404
    assert seen == [(job, "intent")]


def test_checkpoint_rejects_hostile_array_header_before_numpy_allocates(tmp_path, monkeypatch):
    import io
    import zipfile

    header = io.BytesIO()
    np.lib.format.write_array_header_1_0(
        header, {"descr": "|u1", "fortran_order": False, "shape": (2**50,)}
    )
    path = tmp_path / "hostile.npz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("metadata.npy", header.getvalue())
    monkeypatch.setattr(
        np,
        "load",
        lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("Must reject header before allocation")
        ),
    )
    import pytest

    with pytest.raises(ValueError, match="header"):
        load_frames(path, "key", [], 10000)


def test_new_worker_restores_cloud_checkpoint_and_does_not_track_twice(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    import cv2
    import httpx
    from app import cloud, service
    from app.schemas import Opinion, Protocol
    from fastapi import HTTPException

    owner = "11111111-1111-4111-8111-111111111111"
    rows, objects = {}, {}

    def handle(request):
        path = request.url.path
        if path.endswith("/analysis_jobs"):
            if request.method == "POST":
                value = json.loads(request.content)
                rows[value["id"]] = {**value, "created_at": datetime.now(UTC).isoformat()}
                return httpx.Response(201, json=[value])
            job = request.url.params["id"].removeprefix("eq.")
            if request.method == "PATCH":
                rows[job].update(json.loads(request.content))
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[rows[job]] if job in rows else [])
        name = path.split("analysis-artifacts/", 1)[1]
        if request.method == "POST":
            objects[name] = request.content
            return httpx.Response(200, json={})
        return httpx.Response(200, content=objects[name])

    def factory(settings, token, who):
        store = cloud.CloudJobs(settings, token, who)
        store.http.close()
        store.http = httpx.Client(
            base_url="https://cloud.test/", transport=httpx.MockTransport(handle)
        )
        return store

    async def auth(settings, header):
        if header == "Bearer owner":
            return owner
        raise HTTPException(401, "Sign in")

    monkeypatch.setattr(main, "CloudJobs", factory)
    monkeypatch.setattr(main, "authenticate", auth)
    old = tmp_path / "worker1"
    settings = Settings(
        _env_file=None, data_dir=old, cloud_jobs=True, replay_mode=False, model_api_key="mock"
    )
    proto = Protocol.model_validate(
        {
            "name": "Generated test only",
            "objects": [{"name": "cap", "sam_prompt": "cap", "class": "cap"}],
            "steps": [
                {"id": "s", "title": "Observe cap", "post": [{"op": "present", "obj": "cap"}]}
            ],
        }
    )
    protocol_id = "b" * 32
    folder = old / "jobs" / protocol_id
    folder.mkdir(parents=True)
    (folder / "owner.txt").write_text(owner)
    (folder / "protocol.json").write_text(proto.model_dump_json(by_alias=True))
    movie = tmp_path / "input.avi"
    writer = cv2.VideoWriter(str(movie), cv2.VideoWriter_fourcc(*"MJPG"), 4, (64, 64))
    assert writer.isOpened()
    for i in range(12):
        writer.write(np.full((64, 64, 3), i * 10, dtype=np.uint8))
    writer.release()
    calls = []

    def tracking(client, protocol, paths, sha, *args):
        calls.append("tracking")
        return [
            FrameState(
                t,
                {"cap": Detection(np.ones((64, 64), dtype=np.bool_), 0.9, "cap"), "hand": None},
                64,
                64,
                str(p),
            )
            for t, p in paths
        ]

    monkeypatch.setattr(service, "track", tracking)
    recovery = service.recover_once
    monkeypatch.setattr(
        service,
        "recover_once",
        lambda *a: (_ for _ in ()).throw(
            RuntimeError("Simulated interruption after saved tracking")
        ),
    )
    monkeypatch.setattr(
        service.MetaClient,
        "structured",
        lambda *a, **kw: Opinion(completed=True, confidence=0.9, reason="mock"),
    )
    with TestClient(main.create_app(settings)) as api:
        result = api.post(
            "/api/runs",
            headers={"Authorization": "Bearer owner"},
            data={"protocol_id": protocol_id},
            files={"video": ("input.mp4", movie.read_bytes(), "video/mp4")},
        )
        assert result.status_code == 202
        job = result.json()["run_id"]
        assert rows[job]["status"] == "error" and rows[job]["result"]["resumable"]
    monkeypatch.setattr(service, "recover_once", recovery)
    # A fresh worker has no local inputs, caches, masks or logs.
    fresh = settings.model_copy(update={"data_dir": tmp_path / "worker2"})
    with TestClient(main.create_app(fresh)) as api:
        assert api.post(f"/api/jobs/{job}/resume").status_code == 401
        response = api.post(f"/api/jobs/{job}/resume", headers={"Authorization": "Bearer owner"})
        assert response.status_code == 202, response.text
        assert rows[job]["status"] == "ready", rows[job]
        assert (
            api.get(f"/api/runs/{job}", headers={"Authorization": "Bearer owner"}).json()["states"][
                "s"
            ]
            == "ACTIVE"  # A vacuous always-present condition must remain unconfirmed.
        )
    assert calls == ["tracking"]
    assert (fresh.data_dir / "jobs" / job / "original.mp4").read_bytes() == movie.read_bytes()
