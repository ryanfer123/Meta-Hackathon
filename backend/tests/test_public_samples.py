import json

import pytest
from app import main, sample_access
from app.budget import Budget
from app.cloud import CloudJobs
from app.config import Settings
from app.meta_client import MetaClient
from app.sample_access import SampleRateLimiter, is_public_sample
from app.samples import SAMPLES
from fastapi.testclient import TestClient


def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, auth_required=True, cloud_jobs=True)


@pytest.mark.parametrize("name", SAMPLES)
def test_public_samples_never_use_accounts_models_cloud_or_budget(tmp_path, monkeypatch, name):
    def forbidden(*args, **kwargs):
        pytest.fail("Public samples must not contact Auth, models, cloud storage or budgets")

    monkeypatch.setattr(main, "authenticate", forbidden)
    monkeypatch.setattr(MetaClient, "__init__", forbidden)
    monkeypatch.setattr(CloudJobs, "__init__", forbidden)
    monkeypatch.setattr(Budget, "reserve", forbidden)
    with TestClient(main.create_app(settings(tmp_path))) as client:
        assert len(client.get("/api/samples").json()) == 6
        # Direct reads work on a fresh worker without a prior POST or cloud archive.
        run = client.get(f"/api/runs/sample-{name}").json()
        assert run["provenance"] == "synthetic"
        assert run["metrics"]["model_calls"] == 0
        assert client.post(f"/api/runs/sample/{name}").json() == run
        assert client.get(f"/api/runs/sample-{name}/report").status_code == 200
        verified = client.post(
            f"/api/runs/sample-{name}/verify", data={"trusted_root": run["chain_root"]}
        )
        assert verified.json()["valid"]
        assert not client.post(
            f"/api/runs/sample-{name}/verify", data={"trusted_root": "0" * 64}
        ).json()["valid"]
        # No original recording is invented for a synthetic scene.
        assert client.get(f"/api/media/sample-{name}/original.mp4").status_code == 404
        assert not (tmp_path / "budget.sqlite").exists()
        assert not (tmp_path / "runs").exists()


def test_real_and_lookalike_jobs_remain_private(tmp_path):
    job = "a" * 32
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps({"private": True}))
    (folder / "report.html").write_text("private-report")
    (folder / "original.mp4").write_bytes(b"private-video")
    with TestClient(main.create_app(settings(tmp_path))) as client:
        for path in [
            f"/api/runs/{job}",
            f"/api/runs/{job}/report",
            f"/api/media/{job}/original.mp4",
            f"/api/protocols/{job}",
            "/api/runs/sample-unknown",
            "/api/runs/sample-clean-extra/report",
            "/api/media/sample-clean/owner.txt",
            "/api/protocols/sample-clean",
        ]:
            assert client.get(path).status_code in (401, 404)
        assert client.post(f"/api/runs/{job}/verify").status_code == 401
        assert client.post("/api/runs", files={"video": ("v.mp4", b"x")}).status_code == 401
        assert client.post("/api/protocols", files={"video": ("v.mp4", b"x")}).status_code == 401
        assert client.post("/api/protocols/sample-clean/validate").status_code == 401
        assert client.post("/api/runs/sample/unknown").status_code in (401, 404)


def test_sample_public_route_allowlist_is_method_and_path_specific():
    assert is_public_sample("POST", "/api/runs/sample-clean/verify")
    for method, path in [
        ("DELETE", "/api/runs/sample-clean"),
        ("POST", "/api/runs/sample-clean"),
        ("GET", "/api/runs/sample/clean"),
        ("GET", "/api/runs/sample-clean/../" + "a" * 32),
        ("GET", "/api/runs/sample-clean/report/extra"),
        ("GET", "/api/runs/sample-clean%2freport"),
        ("GET", "/api/media/sample-clean/../../owner.txt"),
    ]:
        assert not is_public_sample(method, path)


def test_rate_limit_recovers_after_window_and_does_not_trust_forwarded_ip(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(sample_access.time, "monotonic", lambda: now[0])
    app = main.create_app(settings(tmp_path))
    with TestClient(app, client=("192.0.2.1", 1000)) as client:
        for n in range(30):
            assert (
                client.get(
                    "/api/samples", headers={"X-Forwarded-For": f"198.51.100.{n}"}
                ).status_code
                == 200
            )
        response = client.post("/api/runs/sample/clean")
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/runs/" + "a" * 32).status_code == 401
        with TestClient(app, client=("192.0.2.2", 1001)) as peer:
            assert peer.get("/api/samples").status_code == 200
        now[0] += 60
        assert client.get("/api/samples").status_code == 200


def test_limiter_storage_is_bounded(monkeypatch):
    monkeypatch.setattr(sample_access.time, "monotonic", lambda: 100.0)
    limiter = SampleRateLimiter()
    for n in range(5000):
        assert limiter.retry_after(str(n)) == 0
    assert len(limiter.clients) == 4096


def test_public_sample_exemption_keeps_multipart_size_guard(tmp_path):
    with TestClient(main.create_app(settings(tmp_path))) as client:
        response = client.post(
            "/api/runs/sample-clean/verify",
            content=b"small-body",
            headers={
                "content-type": "multipart/form-data; boundary=test",
                "content-length": str((settings(tmp_path).max_upload_mb + 2) * 1024 * 1024),
            },
        )
        assert response.status_code == 413
