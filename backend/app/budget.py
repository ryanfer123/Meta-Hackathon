import sqlite3
from datetime import UTC, datetime
from pathlib import Path

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
