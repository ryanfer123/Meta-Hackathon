"""Private, atomic progress snapshots. Estimates describe the current stage only."""

import time
from pathlib import Path
from typing import Any

from app.replay_cache import atomic_json


class JobProgress:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.started = time.time()
        self.stage_started = self.started
        self.stage = ""

    def update(self, stage: str, completed: int = 0, total: int = 0, unit: str = "") -> None:
        now = time.time()
        if stage != self.stage:
            self.stage, self.stage_started = stage, now
        elapsed = max(0, now - self.stage_started)
        eta = elapsed / completed * (total - completed) if 0 < completed < total else None
        atomic_json(
            self.folder / "progress.json",
            {
                "stage": stage,
                "completed": completed,
                "total": total,
                "unit": unit,
                "started_at": self.started,
                "updated_at": now,
                "eta_seconds": round(eta) if eta is not None else None,
                "estimate_scope": "current-stage",
            },
        )


def with_progress(result: dict[str, Any], folder: Path) -> dict[str, Any]:
    import json

    path = folder / "progress.json"
    if result.get("status") in ("processing", "validating") and path.exists():
        return {**result, "progress": json.loads(path.read_text())}
    return result
