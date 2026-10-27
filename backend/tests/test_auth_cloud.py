import asyncio
import io
import json
import zipfile

import httpx
import pytest
from app import auth, budget, main
from app.auth import authenticate
from app.budget import Budget, BudgetExceeded
from app.cloud import CloudJobs
from app.config import Settings
from app.meta_client import MetaClient
from fastapi import HTTPException
from fastapi.testclient import TestClient

OWNER = "11111111-1111-4111-8111-111111111111"
PEER = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize(
    "payload,status,expected",
    [
        ({"id": OWNER, "email_confirmed_at": "2026-10-27"}, 200, OWNER),
        ({"id": OWNER, "email_confirmed_at": None}, 200, 403),
        ({"id": OWNER, "email_confirmed_at": "yes", "is_anonymous": True}, 200, 403),
        ({"id": OWNER}, 401, 401),
        ({}, 500, 503),
        ({"id": "../../escape", "email_confirmed_at": "yes"}, 200, 503),
    ],
)
def test_auth_validates_server_identity(monkeypatch, payload, status, expected):
    original = httpx.AsyncClient

    def handler(request):
        assert request.url.path == "/auth/v1/user"
        assert request.headers["authorization"] == "Bearer test-jwt"
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(
        auth.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    settings = Settings(
        _env_file=None,
        supabase_url="https://test.supabase.co",
        supabase_publishable_key="public-test",
    )
    if isinstance(expected, int):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(authenticate(settings, "Bearer test-jwt"))
        assert exc.value.status_code == expected
    else:
        assert asyncio.run(authenticate(settings, "Bearer test-jwt")) == expected


def test_auth_required_and_owner_scoped_media(tmp_path, monkeypatch):
    async def verify(config, header):
        if header == "Bearer owner":
            return OWNER
        if header == "Bearer peer":
            return PEER
        raise HTTPException(401, "Sign in")

    monkeypatch.setattr(main, "authenticate", verify)
    job = "a" * 32
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "owner.txt").write_text(OWNER)
    (folder / "status.json").write_text('{"status":"ready"}')
    (folder / "original.mp4").write_bytes(b"owner-private-media")
    config = Settings(_env_file=None, data_dir=tmp_path)
    with TestClient(main.create_app(config)) as client:
        assert client.get("/api/health").status_code == 200
        for path in ["/api/samples", f"/api/protocols/{job}", f"/api/media/{job}/original.mp4"]:
            assert client.get(path).status_code == 401
        assert (
            client.get(
                f"/api/protocols/{job}", headers={"Authorization": "Bearer peer"}
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/media/{job}/original.mp4", headers={"Authorization": "Bearer peer"}
            ).status_code
            == 404
        )
        response = client.get(
            f"/api/media/{job}/original.mp4", headers={"Authorization": "Bearer owner"}
        )
        assert response.content == b"owner-private-media"
        assert response.headers["cache-control"] == "no-store"
        rejected = client.get(
            "/api/samples", headers={"Origin": "https://apprentice-meta.onrender.com"}
        )
        assert (
            rejected.headers["access-control-allow-origin"]
            == "https://apprentice-meta.onrender.com"
        )


def test_budget_denial_prevents_meta_request(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(
        budget.httpx, "post", lambda *a, **kw: httpx.Response(403, json={"message": "denied"})
    )
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        replay_mode=False,
        model_api_key="never-log-this",
        cloud_jobs=True,
        supabase_url="https://test.supabase.co",
        supabase_publishable_key="public",
        supabase_access_token="private-user-token",
        server_budget_key="private-budget-key",
    )
    client = MetaClient(settings, "test-budget", httpx.MockTransport(lambda req: sent.append(req)))
    with pytest.raises(BudgetExceeded):
        client.call("responses", "spark", "muse-spark-1.3", {})
    assert not sent
    assert "private-budget-key" not in repr(settings)
    client.close()


def test_missing_host_budget_fails_closed(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, cloud_jobs=True)
    with pytest.raises(BudgetExceeded):
        Budget(settings).reserve("test", "spark", 0.25)


def test_cloud_archive_restores_only_allowed_files(tmp_path, monkeypatch):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        z.writestr("protocol.json", '{"name":"Test"}')
    store = CloudJobs(
        Settings(_env_file=None, supabase_url="https://test.supabase.co"), "private-token", OWNER
    )
    monkeypatch.setattr(store, "get", lambda job: {"artifact_path": OWNER + "/" + job + ".zip"})
    monkeypatch.setattr(
        store, "request", lambda *a, **kw: httpx.Response(200, content=output.getvalue())
    )
    folder = tmp_path / "restored"
    assert store.restore("a" * 32, folder)
    assert (folder / "owner.txt").read_text() == OWNER
    assert json.loads((folder / "protocol.json").read_text())["name"] == "Test"
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../escape", "bad")
    monkeypatch.setattr(
        store, "request", lambda *a, **kw: httpx.Response(200, content=bad.getvalue())
    )
    with pytest.raises(ValueError, match="Unexpected"):
        store.restore("a" * 32, folder)
    assert not (tmp_path / "escape").exists()
    store.close()


def test_api_only_shadow_uses_spark_and_never_completes_rules():
    from app.schemas import Event, Opinion
    from app.supervise.verifier import Verifier

    calls = []

    def no_glimmer(*args):
        raise AssertionError("API-only mode must not call Glimmer")

    def spark(prompt, frames):
        calls.append(prompt)
        return Opinion(completed=False, confidence=0.8, reason="Advisory disagreement")

    verifier = Verifier(no_glimmer, spark, api_only=True)
    event = Event(
        t=1, step_id="cap", kind="step_completed", tier="rules", confidence=1, detail="Rule result"
    )
    events = verifier.review(event, "Check the cap", [], shadow=True)
    assert len(calls) == 1
    assert events[0].kind == "shadow_disagreement"
    assert events[0].tier == "spark"
    assert verifier.shadow[0]["available"] is True
    assert verifier.shadow[0]["agree"] is False
    assert event.kind == "step_completed"
