"""Disk-backed private archives and pre-analysis upload guards; no network."""

import io
import json
import zipfile

import httpx
import pytest
from app import cloud, main
from app.cloud import CloudJobs
from app.config import Settings
from app.samples import sample_protocol
from fastapi.testclient import TestClient


def store(monkeypatch, payload=b""):
    client = CloudJobs(
        Settings(_env_file=None, supabase_url="https://example.test"), "mock", "owner"
    )
    monkeypatch.setattr(client, "get", lambda job: {"artifact_path": "owner/" + job + ".zip"})
    monkeypatch.setattr(client, "request", lambda *a, **kw: httpx.Response(200, content=payload))
    return client


def test_archive_streams_bounded_chunks_and_excludes_private_files(tmp_path, monkeypatch):
    (tmp_path / "status.json").write_text('{"status":"ready"}')
    (tmp_path / "original.mp4").write_bytes(b"video" * 40000)
    (tmp_path / "private-token.txt").write_text("not public")
    client = store(monkeypatch)
    uploaded = []

    def request(method, path, **kwargs):
        if method == "POST":
            assert not isinstance(kwargs["content"], bytes)
            chunks = list(kwargs["content"])
            assert max(map(len, chunks)) <= cloud.STREAM_CHUNK_BYTES
            payload = b"".join(chunks)
            assert len(payload) == int(kwargs["headers"]["Content-Length"])
            uploaded.append(payload)
        return httpx.Response(200)

    monkeypatch.setattr(client, "request", request)
    client.archive("job", tmp_path, "learn")
    with zipfile.ZipFile(io.BytesIO(uploaded[0])) as archive:
        assert set(archive.namelist()) == {"status.json", "original.mp4"}
        assert archive.read("original.mp4") == b"video" * 40000
    monkeypatch.setattr(cloud, "ARCHIVE_MAX_BYTES", 10)
    with pytest.raises(RuntimeError, match="storage limit"):
        client.archive("job", tmp_path, "learn")
    assert len(uploaded) == 1
    client.close()


@pytest.mark.parametrize("failure", ["unexpected", "duplicate", "crc", "expanded"])
def test_restore_rejects_invalid_archive_without_overwriting_inputs(tmp_path, monkeypatch, failure):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("original.mp4", "replacement-video")
        if failure == "unexpected":
            archive.writestr("../escape", "bad")
        if failure == "duplicate":
            with pytest.warns(UserWarning):
                archive.writestr("original.mp4", "duplicate")
    payload = output.getvalue()
    if failure == "crc":
        payload = payload.replace(b"replacement-video", b"corrupt-----video")
    if failure == "expanded":
        monkeypatch.setattr(cloud, "ARCHIVE_MAX_BYTES", len(payload) + 1)
        # Claim an expanded member beyond the limit in the central-directory header.
        data = bytearray(payload)
        index = data.index(b"PK\x01\x02")
        data[index + 24 : index + 28] = (len(payload) + 2).to_bytes(4, "little")
        payload = bytes(data)
    folder = tmp_path / "existing"
    folder.mkdir()
    (folder / "original.mp4").write_bytes(b"keep-me")
    client = store(monkeypatch, payload)
    with pytest.raises((ValueError, zipfile.BadZipFile)):
        client.restore("job", folder)
    assert (folder / "original.mp4").read_bytes() == b"keep-me"
    assert not (tmp_path / "escape").exists()
    assert not list(tmp_path.glob(".restore-*"))
    client.close()


@pytest.mark.parametrize(
    "content,mime,status",
    [
        (b"1234567", "video/mp4", 413),
        (b"", "video/mp4", 422),
        (b"new", "text/plain", 415),
        (b"123456", "video/mp4", 202),
    ],
)
def test_replacement_preflight_preserves_previous_video_and_confirmation(
    tmp_path, monkeypatch, content, mime, status
):
    calls = []

    class Cloud:
        def __init__(self, *args):
            pass

        def begin(self, *args):
            calls.append("begin")

        def archive(self, *args):
            calls.append("archive")

        def close(self):
            pass

    monkeypatch.setattr(main, "CloudJobs", Cloud)
    monkeypatch.setattr(main, "CLOUD_SOURCE_MAX_BYTES", 10)
    monkeypatch.setattr(main, "probe_video", lambda *a: {"duration_s": 30})
    monkeypatch.setattr(main, "process_validation", lambda *a, **kw: calls.append("process"))
    job = "a" * 32
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "original.mp4").write_bytes(b"1234")
    (folder / "heldout.mp4").write_bytes(b"old-video")
    (folder / "protocol.json").write_text(sample_protocol().model_dump_json(by_alias=True))
    (folder / "status.json").write_text('{"status":"ready"}')
    (folder / "boundary_confirmation.json").write_text('{"previous":true}')
    ranges = {
        step.id: {"start": i * 3, "end": i * 3 + 2}
        for i, step in enumerate(sample_protocol().steps)
    }
    config = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auth_required=False,
        cloud_jobs=True,
        replay_mode=False,
        model_api_key="mock-only",
    )
    with TestClient(main.create_app(config)) as api:
        result = api.post(
            f"/api/protocols/{job}/validate",
            data={"ranges": json.dumps(ranges), "ranges_confirmed": "true"},
            files={"heldout": ("second.mp4", content, mime)},
        )
    assert result.status_code == status, result.text
    assert not list(folder.glob("*.upload"))
    if status == 202:
        assert calls == ["begin", "process", "archive"]
        assert (folder / "heldout.mp4").read_bytes() == content
    else:
        assert not calls
        assert (folder / "heldout.mp4").read_bytes() == b"old-video"
        assert json.loads((folder / "boundary_confirmation.json").read_text()) == {"previous": True}
        assert json.loads((folder / "status.json").read_text()) == {"status": "ready"}


def test_cloud_limit_refuses_before_paid_work_and_local_limit_stays_configurable(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(main, "process_learn", lambda *a: calls.append("process"))
    monkeypatch.setattr(main, "CLOUD_SOURCE_MAX_BYTES", 4)
    config = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auth_required=False,
        replay_mode=False,
        cloud_jobs=True,
        model_api_key="mock",
    )
    with TestClient(main.create_app(config)) as api:
        assert (
            api.post("/api/protocols", files={"video": ("video.mp4", b"12345")}).status_code == 413
        )
        assert not calls
        assert api.get("/api/health").json()["max_cloud_source_bytes"] == 4
    with TestClient(main.create_app(config.model_copy(update={"cloud_jobs": False}))) as api:
        assert (
            api.post("/api/protocols", files={"video": ("video.mp4", b"12345")}).status_code == 202
        )
        assert api.get("/api/health").json()["max_cloud_source_bytes"] is None
    assert calls == ["process"]
