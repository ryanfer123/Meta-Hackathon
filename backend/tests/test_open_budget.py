"""Every advisory attempt reserves before network I/O; tests never call a provider."""

import json
import sqlite3

import httpx
import pytest
from app.budget import BudgetExceeded
from app.config import Settings
from app.glimmer_client import GlimmerClient
from pydantic import SecretStr


def settings(tmp_path, **kwargs):
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        replay_mode=False,
        glimmer_base_url="https://inference.baseten.co/v1",
        **kwargs,
    )


def test_open_budget_refuses_before_transport(tmp_path):
    client = GlimmerClient(
        settings(tmp_path, max_run_cost_usd=0.04),
        "limited",
        httpx.MockTransport(lambda request: pytest.fail("budget denial must precede I/O")),
    )
    with pytest.raises(BudgetExceeded):
        client.opinion("review", [])


def test_each_schema_attempt_is_reserved_and_failure_is_not_refunded(tmp_path):
    calls = []

    def bad_reply(request):
        calls.append(1)
        return httpx.Response(200, json={"choices": [{"message": {"content": "invalid"}}]})

    client = GlimmerClient(
        settings(tmp_path, max_run_cost_usd=0.1), "retry", httpx.MockTransport(bad_reply)
    )
    with pytest.raises(BudgetExceeded):
        client.opinion("review", [])
    assert len(calls) == 2
    with sqlite3.connect(tmp_path / "budget.sqlite") as db:
        assert db.execute("select kind,sum(reserved),count(*) from calls").fetchone() == (
            "glimmer",
            0.1,
            2,
        )
    rows = [
        json.loads(line) for line in (tmp_path / "runs/retry/calls.jsonl").read_text().splitlines()
    ]
    assert all(row["reserved_usd"] == 0.05 and row["status"] == "error" for row in rows)


def test_hosted_open_budget_uses_authenticated_ledger_before_model(tmp_path, monkeypatch):
    seen = []

    def reserve(url, *, headers, json, timeout):
        seen.append("reservation")
        assert url.endswith("/rpc/reserve_model_budget")
        assert headers["Authorization"] == "Bearer mock-user"
        assert json["call_kind"] == "glimmer" and json["reserved_usd"] == 0.05
        return httpx.Response(400)

    monkeypatch.setattr(httpx, "post", reserve)
    client = GlimmerClient(
        settings(
            tmp_path,
            cloud_jobs=True,
            supabase_url="https://example.invalid",
            supabase_access_token=SecretStr("mock-user"),
            server_budget_key=SecretStr("mock-budget"),
        ),
        "hosted",
        httpx.MockTransport(lambda request: pytest.fail("hosted denial must precede model I/O")),
    )
    with pytest.raises(BudgetExceeded):
        client.opinion("review", [])
    assert seen == ["reservation"]
