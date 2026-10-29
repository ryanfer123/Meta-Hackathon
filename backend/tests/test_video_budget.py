"""Native-video accounting and safety guards; no provider requests or real credentials."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx
import pytest
from app import budget as budget_module
from app.budget import Budget, BudgetExceeded
from app.config import Settings
from app.samples import sample_protocol
from app.schemas import Protocol
from pydantic import ValidationError


def config(tmp_path, **updates):
    return Settings(_env_file=None, data_dir=tmp_path, **updates)


def totals(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT SUM(reserved), SUM(processed_frames) FROM calls").fetchone()


def test_video_defaults_fit_two_ninety_second_experts_with_implicit_hand(tmp_path):
    settings = config(tmp_path)
    protocol = Protocol.model_validate(
        {
            "name": "Two expert budget test",
            "objects": [o.model_dump(by_alias=True) for o in sample_protocol().objects[:6]],
            "steps": [
                {
                    "id": "observe",
                    "title": "Observe tube",
                    "post": [{"op": "present", "obj": "tube_1"}],
                }
            ],
        }
    )
    # Six visible props plus the implicit hand, for both expert takes under one run ID.
    object_count = len(protocol.objects)
    assert settings.sam_mode == "image"
    assert settings.max_sam_video_frames == 6000
    assert settings.hosted_max_sam_video_frames == 6000
    assert settings.max_spark_calls == 40
    assert settings.max_run_cost_usd == 8
    assert settings.max_daily_cost_usd == 10
    assert settings.hosted_max_run_cost_usd == 8
    assert settings.hosted_max_daily_cost_usd == 10
    assert len(protocol.objects) == 7
    assert "hand" in {o.name for o in protocol.objects}
    budget = Budget(settings)
    for _ in range(2 * object_count):
        frames = 90 * 4
        budget.reserve("expert-pair", "sam", frames * 0.0002, processed_frames=frames)
    usd, frames = totals(budget.path)
    assert frames == 5040
    assert usd == pytest.approx(1.008)


def test_video_frame_cap_replaces_image_call_count_but_image_limit_remains(tmp_path):
    budget = Budget(config(tmp_path, max_sam_calls=1, max_sam_video_frames=20))
    budget.reserve("one", "sam", 0.0025)
    budget.reserve("one", "sam", 0.002, processed_frames=10)
    budget.reserve("one", "sam", 0.002, processed_frames=10)
    with pytest.raises(BudgetExceeded, match="per-run call"):
        budget.reserve("one", "sam", 0.0025)
    with pytest.raises(BudgetExceeded, match="processed-frame"):
        budget.reserve("one", "sam", 0.0002, processed_frames=1)
    assert totals(budget.path)[1] == 20


def test_video_frame_reservations_are_atomic_across_instances(tmp_path):
    settings = config(tmp_path, max_sam_video_frames=100)
    Budget(settings)

    def reserve(_):
        try:
            Budget(settings).reserve("same", "sam", 0.01, processed_frames=50)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(12))) == 2
    assert totals(tmp_path / "budget.sqlite")[1] == 100


def test_legacy_sqlite_migration_preserves_existing_calls(tmp_path):
    path = tmp_path / "budget.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE calls(day TEXT, run TEXT, kind TEXT, reserved REAL)")
        db.execute("INSERT INTO calls VALUES ('2026-10-28','old','sam',0.0025)")
    budget = Budget(config(tmp_path))
    budget.reserve("new", "sam", 0.002, processed_frames=10)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT processed_frames FROM calls WHERE run='old'").fetchone() == (0,)
    assert totals(path) == pytest.approx((0.0045, 10))


def test_local_daily_cost_cap_spans_jobs(tmp_path):
    budget = Budget(config(tmp_path, max_daily_cost_usd=0.5))
    budget.reserve("a", "spark", 0.25)
    budget.reserve("b", "voice", 0.25)
    with pytest.raises(BudgetExceeded, match="daily cost"):
        budget.reserve("c", "sam", 0.0025)


def test_video_overrun_adds_only_delta_halts_all_kinds_and_survives_restart(tmp_path):
    settings = config(tmp_path)
    budget = Budget(settings)
    budget.reserve("sam", "sam", 0.002, processed_frames=10)
    budget.record_video_usage("sam", 10, 7)
    assert totals(budget.path) == pytest.approx((0.002, 10))
    with pytest.raises(BudgetExceeded, match="overrun recorded"):
        budget.record_video_usage("sam", 10, 14)
    assert totals(budget.path) == pytest.approx((0.0028, 14))
    for kind in ("sam", "spark", "voice"):
        with pytest.raises(BudgetExceeded, match="halted"):
            Budget(settings).reserve("another-job", kind, 0.001)
    accounting = json.loads((tmp_path / "runs/sam/accounting.jsonl").read_text())
    assert accounting["overrun_frames"] == 4
    assert accounting["status"] == "accounting_overrun"
    assert not (tmp_path / "runs/sam/calls.jsonl").exists()


def test_overrun_halt_is_scoped_to_utc_day(tmp_path, monkeypatch):
    settings = config(tmp_path)
    budget = Budget(settings)
    with pytest.raises(BudgetExceeded):
        budget.record_video_usage("job", 10, 11)

    class Tomorrow:
        @staticmethod
        def now(_):
            return datetime(2099, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(budget_module, "datetime", Tomorrow)
    Budget(settings).reserve("next-day", "spark", 0.25)


def hosted(tmp_path, **updates):
    return config(
        tmp_path,
        cloud_jobs=True,
        supabase_url="https://mock.supabase.invalid",
        supabase_publishable_key="public-test",
        supabase_access_token="mock-user-token",
        server_budget_key="mock-server-budget",
        **updates,
    )


def test_hosted_reservations_send_configured_caps_without_local_defaults(tmp_path, monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=None)

    monkeypatch.setattr(budget_module.httpx, "post", post)
    settings = hosted(tmp_path, max_sam_calls=800)
    Budget(settings).reserve("a" * 32, "sam", 0.072, processed_frames=360)
    url, request = calls[0]
    assert url.endswith("/reserve_model_budget")
    assert request["json"] == {
        "server_key": "mock-server-budget",
        "run_id": "a" * 32,
        "call_kind": "sam",
        "reserved_usd": 0.072,
        "processed_frames": 360,
        "max_run_usd": 8,
        "max_day_usd": 10,
        "max_sam_frames": 6000,
        "max_sam_calls": 800,
        "max_spark_calls": 40,
        "max_spark_day": 60,
    }
    assert request["headers"]["Authorization"] == "Bearer mock-user-token"
    assert "mock-server-budget" not in repr(settings)


@pytest.mark.parametrize("deny", [False, True])
def test_hosted_overrun_reconciles_and_blocks_next_request_even_if_reconcile_denied(
    tmp_path, monkeypatch, deny
):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(403 if deny else 200, json=None)

    monkeypatch.setattr(budget_module.httpx, "post", post)
    settings = hosted(tmp_path)
    with pytest.raises(BudgetExceeded):
        Budget(settings).record_video_usage("a" * 32, 10, 12)
    assert calls[0][0].endswith("/reconcile_sam_budget")
    assert calls[0][1]["json"] == {
        "server_key": "mock-server-budget",
        "run_id": "a" * 32,
        "reserved_frames": 10,
        "actual_frames": 12,
    }
    with pytest.raises(BudgetExceeded, match="halted"):
        Budget(settings).reserve("another", "spark", 0.25)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "cost,frames,kind",
    [
        (float("nan"), 0, "sam"),
        (float("inf"), 0, "sam"),
        (-1, 0, "sam"),
        (0.1, -1, "sam"),
        (0.1, 1.5, "sam"),
        (0.1, True, "sam"),
        (0.1, 1, "spark"),
        (0.001, 100, "sam"),
    ],
)
def test_invalid_video_accounting_fails_before_requests(tmp_path, cost, frames, kind):
    budget = Budget(config(tmp_path))
    with pytest.raises(ValueError):
        budget.reserve("test", kind, cost, processed_frames=frames)
    assert totals(budget.path) == (None, None)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_run_cost_usd", float("inf")),
        ("max_daily_cost_usd", float("nan")),
        ("hosted_max_run_cost_usd", 0),
        ("hosted_max_daily_cost_usd", -1),
        ("max_sam_video_frames", 0),
        ("hosted_max_sam_video_frames", -1),
        ("sam_mode", "unknown"),
        ("sam_video_max_bytes", 50_000_001),
    ],
)
def test_invalid_budget_config_is_rejected(tmp_path, field, value):
    with pytest.raises(ValidationError):
        config(tmp_path, **{field: value})


def test_image_defaults_fit_two_experts_and_three_spark_reservations(tmp_path):
    settings = config(tmp_path)
    budget = Budget(settings)
    image_calls = 2 * 90 * 2 * 7  # two 90s experts, 2 fps, six props plus hand
    assert settings.sam_mode == "image"
    assert image_calls == 2520
    assert image_calls <= settings.max_sam_calls == 3000
    for _ in range(image_calls):
        budget.reserve("expert-pair-image", "sam", 0.0025)
    for _ in range(3):
        budget.reserve("expert-pair-image", "spark", 0.25)
    usd, frames = totals(budget.path)
    assert usd == pytest.approx(7.05)
    assert frames == 0
    assert usd < settings.hosted_max_run_cost_usd == settings.max_run_cost_usd == 8
    assert usd < settings.hosted_max_daily_cost_usd == settings.max_daily_cost_usd == 10
    with pytest.raises(BudgetExceeded, match="run cost"):
        budget.reserve("expert-pair-image", "spark", 1.0)
