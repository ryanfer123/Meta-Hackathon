import sqlite3
from datetime import UTC, datetime

import pytest
from app.budget import Budget, BudgetExceeded
from app.config import Settings


def test_monthly_cap_is_shared_across_models_and_runs_and_previous_month_is_excluded(tmp_path):
    config = Settings(
        _env_file=None, data_dir=tmp_path, max_monthly_cost_usd=1, max_daily_cost_usd=5
    )
    budget = Budget(config)
    month = datetime.now(UTC).strftime("%Y-%m")
    with sqlite3.connect(budget.path) as db:
        db.execute(
            "INSERT INTO calls(day,run,kind,reserved) VALUES (?,?,?,?)",
            ("2000-01-01", "old", "spark", 100),
        )
        # A different day in this month still contributes to the calendar-month total.
        db.execute(
            "INSERT INTO calls(day,run,kind,reserved) VALUES (?,?,?,?)",
            (month + "-01", "earlier", "sam", 0.75),
        )
    budget.reserve("new", "glimmer", 0.25)
    with pytest.raises(BudgetExceeded, match="monthly"):
        budget.reserve("another", "voice", 0.01)
    with sqlite3.connect(budget.path) as db:
        assert db.execute("SELECT count(*) FROM calls WHERE run='another'").fetchone()[0] == 0
