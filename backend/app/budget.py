import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings

SAM_VIDEO_FRAME_USD = 0.0002


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    """Durable atomic reservations shared by all worker processes. Never refund attempts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.data_dir / "budget.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS calls "
                "(day TEXT, run TEXT, kind TEXT, reserved REAL, "
                "processed_frames INTEGER NOT NULL DEFAULT 0)"
            )
            if "processed_frames" not in {row[1] for row in db.execute("PRAGMA table_info(calls)")}:
                db.execute(
                    "ALTER TABLE calls ADD COLUMN processed_frames INTEGER NOT NULL DEFAULT 0"
                )
            db.execute(
                "CREATE TABLE IF NOT EXISTS budget_halts (day TEXT PRIMARY KEY, reason TEXT NOT NULL)"
            )

    @staticmethod
    def _frames(value: int, *, positive: bool = False) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
            raise ValueError("Processed frames must be a valid nonnegative integer")

    def _check_halt(self, db: sqlite3.Connection, day: str) -> None:
        if db.execute("SELECT 1 FROM budget_halts WHERE day=?", (day,)).fetchone():
            raise BudgetExceeded(
                "SAM accounting overrun halted all model reservations for this UTC day"
            )

    def _cloud_rpc(self, name: str, fields: dict[str, Any]) -> None:
        token = self.settings.supabase_access_token.get_secret_value()
        key = self.settings.server_budget_key.get_secret_value()
        if not token or not key:
            raise BudgetExceeded("Hosted budget authorization is not configured")
        try:
            response = httpx.post(
                self.settings.supabase_url.rstrip("/") + "/rest/v1/rpc/" + name,
                headers={
                    "apikey": self.settings.supabase_publishable_key,
                    "Authorization": "Bearer " + token,
                },
                json={"server_key": key, **fields},
                timeout=15,
            )
        except httpx.HTTPError as exc:
            raise BudgetExceeded(
                "Hosted budget could not be reached; no further model request permitted"
            ) from exc
        if not response.is_success:
            raise BudgetExceeded("Hosted request budget denied; no further model request permitted")

    def reserve(self, run: str, kind: str, max_cost: float, processed_frames: int = 0) -> None:
        self._frames(processed_frames)
        if isinstance(max_cost, bool) or not math.isfinite(max_cost) or max_cost < 0:
            raise ValueError("Cost reservation must be finite and nonnegative")
        if processed_frames and kind != "sam":
            raise ValueError("Only SAM video reservations may include processed frames")
        if processed_frames and max_cost + 1e-12 < processed_frames * SAM_VIDEO_FRAME_USD:
            raise ValueError("SAM video reservation must cover the estimated processed-frame cost")
        day = datetime.now(UTC).date().isoformat()
        if self.settings.cloud_jobs:
            with sqlite3.connect(self.path) as db:
                self._check_halt(db, day)
            self._cloud_rpc(
                "reserve_model_budget",
                {
                    "run_id": run,
                    "call_kind": kind,
                    "reserved_usd": max_cost,
                    "processed_frames": processed_frames,
                    "max_run_usd": self.settings.hosted_max_run_cost_usd,
                    "max_day_usd": self.settings.hosted_max_daily_cost_usd,
                    "max_sam_frames": self.settings.hosted_max_sam_video_frames,
                    "max_sam_calls": self.settings.max_sam_calls,
                    "max_spark_calls": self.settings.max_spark_calls,
                    "max_spark_day": self.settings.max_daily_spark_calls,
                },
            )
            return
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute("BEGIN IMMEDIATE")
            self._check_halt(db, day)
            n = db.execute(
                "SELECT COUNT(*) FROM calls WHERE run=? AND kind=? AND processed_frames=0",
                (run, kind),
            ).fetchone()[0]
            daily = db.execute(
                "SELECT COUNT(*) FROM calls WHERE day=? AND kind='spark'", (day,)
            ).fetchone()[0]
            cost = db.execute(
                "SELECT COALESCE(SUM(reserved),0) FROM calls WHERE run=?", (run,)
            ).fetchone()[0]
            day_cost = db.execute(
                "SELECT COALESCE(SUM(reserved),0) FROM calls WHERE day=?", (day,)
            ).fetchone()[0]
            video_frames = db.execute(
                "SELECT COALESCE(SUM(processed_frames),0) FROM calls WHERE run=? AND kind='sam'",
                (run,),
            ).fetchone()[0]
            cap = self.settings.max_sam_calls if kind == "sam" else self.settings.max_spark_calls
            if kind in ("sam", "spark") and not processed_frames and n >= cap:
                raise BudgetExceeded(f"{kind} per-run call cap reached ({cap})")
            if (
                processed_frames
                and video_frames + processed_frames > self.settings.max_sam_video_frames
            ):
                raise BudgetExceeded("SAM processed-frame reservation cap reached")
            if kind == "spark" and daily >= self.settings.max_daily_spark_calls:
                raise BudgetExceeded("daily Spark call cap reached")
            if cost + max_cost > self.settings.max_run_cost_usd + 1e-9:
                raise BudgetExceeded("run cost reservation cap reached")
            if day_cost + max_cost > self.settings.max_daily_cost_usd + 1e-9:
                raise BudgetExceeded("daily cost reservation cap reached")
            db.execute(
                "INSERT INTO calls(day,run,kind,reserved,processed_frames) VALUES (?,?,?,?,?)",
                (day, run, kind, max_cost, processed_frames),
            )

    def record_video_usage(self, run: str, reserved_frames: int, actual_frames: int) -> None:
        self._frames(reserved_frames, positive=True)
        self._frames(actual_frames)
        extra = actual_frames - reserved_frames
        if extra <= 0:
            return
        day = datetime.now(UTC).date().isoformat()
        reason = (
            "SAM provider processed more frames than reserved; review accounting before continuing"
        )
        extra_cost = extra * SAM_VIDEO_FRAME_USD
        # Persist the halt first, including when a cloud reconciliation request fails.
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO budget_halts(day,reason) VALUES (?,?)", (day, reason))
            if not self.settings.cloud_jobs:
                db.execute(
                    "INSERT INTO calls(day,run,kind,reserved,processed_frames) VALUES (?,?,?,?,?)",
                    (day, run, "sam", extra_cost, extra),
                )
        accounting = self.log_path(run).with_name("accounting.jsonl")
        with accounting.open("a") as log:
            log.write(
                json.dumps(
                    {
                        "status": "accounting_overrun",
                        "reserved_frames": reserved_frames,
                        "actual_frames": actual_frames,
                        "overrun_frames": extra,
                        "overrun_reserved_usd": extra_cost,
                        "utc_day_halted": day,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        if self.settings.cloud_jobs:
            self._cloud_rpc(
                "reconcile_sam_budget",
                {
                    "run_id": run,
                    "reserved_frames": reserved_frames,
                    "actual_frames": actual_frames,
                },
            )
        raise BudgetExceeded(
            "SAM accounting overrun recorded; all reservations halted for this UTC day"
        )

    def log_path(self, run: str) -> Path:
        path = self.settings.data_dir / "runs" / run / "calls.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
