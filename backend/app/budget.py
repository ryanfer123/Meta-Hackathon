import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import Settings


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    """Durable atomic reservations shared by all worker processes. Never refund attempts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.data_dir / "budget.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS calls (day TEXT, run TEXT, kind TEXT, reserved REAL)"
            )

    def reserve(self, run: str, kind: str, max_cost: float) -> None:
        if self.settings.cloud_jobs:
            token = self.settings.supabase_access_token.get_secret_value()
            key = self.settings.server_budget_key.get_secret_value()
            if not token or not key:
                raise BudgetExceeded("Hosted budget authorization is not configured")
            try:
                response = httpx.post(
                    self.settings.supabase_url.rstrip("/") + "/rest/v1/rpc/reserve_model_budget",
                    headers={
                        "apikey": self.settings.supabase_publishable_key,
                        "Authorization": "Bearer " + token,
                    },
                    json={
                        "server_key": key,
                        "run_id": run,
                        "call_kind": kind,
                        "reserved_usd": max_cost,
                    },
                    timeout=15,
                )
            except httpx.HTTPError as exc:
                raise BudgetExceeded(
                    "Hosted budget could not be reached; no model request sent"
                ) from exc
            if not response.is_success:
                raise BudgetExceeded("Hosted request budget denied; no model request sent")
            return
        day = datetime.now(UTC).date().isoformat()
        if max_cost < 0:
            raise ValueError("negative cost reservation")
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute("BEGIN IMMEDIATE")
            n = db.execute(
                "SELECT COUNT(*) FROM calls WHERE run=? AND kind=?", (run, kind)
            ).fetchone()[0]
            daily = db.execute(
                "SELECT COUNT(*) FROM calls WHERE day=? AND kind='spark'", (day,)
            ).fetchone()[0]
            cost = db.execute(
                "SELECT COALESCE(SUM(reserved),0) FROM calls WHERE run=?", (run,)
            ).fetchone()[0]
            cap = self.settings.max_sam_calls if kind == "sam" else self.settings.max_spark_calls
            if kind in ("sam", "spark") and n >= cap:
                raise BudgetExceeded(f"{kind} per-run call cap reached ({cap})")
            if kind == "spark" and daily >= self.settings.max_daily_spark_calls:
                raise BudgetExceeded("daily Spark call cap reached")
            if cost + max_cost > self.settings.max_run_cost_usd + 1e-9:
                raise BudgetExceeded("run cost reservation cap reached")
            db.execute("INSERT INTO calls VALUES (?,?,?,?)", (day, run, kind, max_cost))

    def log_path(self, run: str) -> Path:
        path = self.settings.data_dir / "runs" / run / "calls.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
