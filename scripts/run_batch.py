"""Opt-in local batch analysis. Never labels recordings or freezes evaluation data."""

import argparse
import fcntl
import hashlib
import json
import math
import re
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.budget import Budget, BudgetExceeded  # noqa: E402
from app.config import Settings  # noqa: E402
from app.learn.frames import file_hash  # noqa: E402
from app.replay_cache import atomic_json, canonical  # noqa: E402
from app.schemas import Protocol  # noqa: E402
from app.service import run_recording  # noqa: E402

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
ARTIFACTS = ("report.html", "chain.json", "root.txt")


@dataclass
class BatchRow:
    video: str
    status: str
    events: int = 0
    cloud_frames: int = 0
    estimated_cost_usd: float | None = None
    seconds: float = 0


def videos_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise ValueError("Choose an existing video folder")
    videos = sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )
    if not videos:
        raise ValueError("No supported videos found")
    stems = [p.stem.casefold() for p in videos]
    if len(set(stems)) != len(stems) or any(p.stem in {"", ".", ".."} for p in videos):
        raise ValueError("Video stems must be unique and safe output-folder names")
    return videos


def reserved_cost(path: Path, jobs: list[str]) -> float:
    if not jobs or not path.exists():
        return 0.0
    total = 0.0
    with sqlite3.connect(path) as db:
        for offset in range(0, len(jobs), 500):
            group = jobs[offset : offset + 500]
            placeholders = ",".join("?" for _ in group)
            total += float(
                db.execute(
                    f"SELECT COALESCE(SUM(reserved),0) FROM calls WHERE run IN ({placeholders})",
                    group,
                ).fetchone()[0]
            )
    return total


def summarize(
    video: Path, status: str, calls: list[dict[str, Any]], events: int, elapsed: float
) -> BatchRow:
    costs = [c.get("cost_estimate_usd") for c in calls]
    return BatchRow(
        video.name,
        status,
        events,
        sum(int(c.get("cloud_frames", 0)) for c in calls),
        None if any(c is None for c in costs) else sum(float(c) for c in costs),
        elapsed,
    )


def load_calls(settings: Settings, job: str) -> list[dict[str, Any]]:
    path = settings.data_dir / "runs" / job / "calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def copy_artifacts(folder: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ARTIFACTS:
        shutil.copyfile(folder / name, destination / name)


def cached_prediction(
    path: Path, video_hash: str, protocol: Protocol, split: str
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        run: dict[str, Any] = json.loads(path.read_text())
        if not isinstance(run, dict):
            return None
        if (
            run.get("status") == "ready"
            and run.get("provenance") == "live-recording"
            and run.get("video_sha256") == video_hash
            and run.get("batch_split") == split
            and run.get("protocol") == protocol.model_dump(by_alias=True)
            and isinstance(run.get("events"), list)
            and isinstance(run.get("metrics"), dict)
        ):
            return run
    except (ValueError, OSError):
        pass
    return None


def run_batch(
    settings: Settings,
    protocol_path: Path,
    videos: Path,
    out: Path,
    split: str,
    *,
    allow_paid_calls: bool = False,
    max_cost_usd: float | None = None,
) -> list[BatchRow]:
    if not allow_paid_calls:
        raise ValueError("Pass --allow-paid-calls explicitly before running analysis")
    if split not in {"dev", "test"}:
        raise ValueError("Split must be dev or test")
    if max_cost_usd is not None and (not math.isfinite(max_cost_usd) or max_cost_usd <= 0):
        raise ValueError("--max-cost-usd must be a finite positive number")
    if settings.cloud_jobs:
        raise ValueError("Batch analysis requires the trusted local ledger (CLOUD_JOBS=false)")
    host = urlparse(settings.glimmer_base_url).hostname
    if (
        max_cost_usd is not None
        and settings.glimmer_base_url
        and host not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("A capped batch cannot price a remote open-model tier; use API-only mode")
    settings.require_live()
    protocol = Protocol.model_validate_json(protocol_path.read_text())
    sources = videos_in(videos)
    out.mkdir(parents=True, exist_ok=True)
    identity = {
        "protocol_sha256": hashlib.sha256(
            canonical(protocol.model_dump(by_alias=True))
        ).hexdigest(),
        "split": split,
        "data_dir": str(settings.data_dir.resolve()),
    }
    # Lock the complete batch, so competing CLI processes cannot race the remaining allowance.
    with (out / ".batch.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another batch is already using this output folder") from exc
        state_path = out / ".batch-state.json"
        state = (
            json.loads(state_path.read_text()) if state_path.exists() else {**identity, "jobs": []}
        )
        if (
            not isinstance(state, dict)
            or not isinstance(state.get("jobs"), list)
            or any(
                not isinstance(job, str) or re.fullmatch(r"[a-f0-9]{32}", job) is None
                for job in state["jobs"]
            )
        ):
            raise ValueError("Malformed batch state; preserve it and inspect the local ledger")
        if any(state.get(key) != value for key, value in identity.items()):
            raise ValueError("Output folder belongs to a different protocol, split or local ledger")
        jobs: list[str] = state["jobs"]
        budget = Budget(settings)
        rows = []
        for video in sources:
            start = time.perf_counter()
            video_hash = file_hash(video)
            job = hashlib.sha256(
                canonical([str(out.resolve()), identity, video.stem, video_hash])
            ).hexdigest()[:32]
            if job not in jobs:
                jobs.append(job)
                atomic_json(state_path, {**identity, "jobs": jobs})
            prediction = out / f"{video.stem}.prediction.json"
            cached = cached_prediction(prediction, video_hash, protocol, split)
            if cached is not None:
                rows.append(
                    summarize(
                        video,
                        "skipped",
                        cached["metrics"].get("calls", []),
                        len(cached["events"]),
                        0,
                    )
                )
                continue
            spent = reserved_cost(budget.path, jobs)
            if max_cost_usd is not None and spent >= max_cost_usd - 1e-9:
                rows.append(BatchRow(video.name, "budget-stopped"))
                break
            cap = settings.max_run_cost_usd
            if max_cost_usd is not None:
                # Include this job's past attempts, already counted in spent. Every next Meta
                # request still passes Budget.reserve before HTTP, including retries/failures.
                cap = min(cap, reserved_cost(budget.path, [job]) + max_cost_usd - spent)
            run_settings = settings.model_copy(update={"max_run_cost_usd": cap})
            try:
                run = run_recording(
                    run_settings, job, video, protocol, fail_on_budget_exhaustion=True
                )
                copy_artifacts(settings.data_dir / "jobs" / job, out / video.stem)
                atomic_json(prediction, {**run, "batch_split": split})
                rows.append(
                    summarize(
                        video,
                        "ready",
                        run["metrics"].get("calls", []),
                        len(run["events"]),
                        time.perf_counter() - start,
                    )
                )
            except BudgetExceeded:
                rows.append(
                    summarize(
                        video,
                        "budget-stopped",
                        load_calls(settings, job),
                        0,
                        time.perf_counter() - start,
                    )
                )
                break
            except Exception:
                # Provider response bodies and credentials never become terminal output.
                rows.append(
                    summarize(
                        video, "error", load_calls(settings, job), 0, time.perf_counter() - start
                    )
                )
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--videos", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--allow-paid-calls", action="store_true", required=True)
    parser.add_argument("--max-cost-usd", type=float)
    args = parser.parse_args()
    try:
        rows = run_batch(
            Settings(),
            args.protocol,
            args.videos,
            args.out,
            args.split,
            allow_paid_calls=args.allow_paid_calls,
            max_cost_usd=args.max_cost_usd,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, str(exc) + "\n")
    print("video | status | events | cloud frames | estimated USD | seconds")
    for row in rows:
        cost = "unknown" if row.estimated_cost_usd is None else f"{row.estimated_cost_usd:.6f}"
        print(
            f"{row.video.replace(chr(10), ' ')} | {row.status} | {row.events} | {row.cloud_frames} | {cost} | {row.seconds:.2f}"
        )
    if any(row.status != "ready" and row.status != "skipped" for row in rows):
        parser.exit(2, "Batch stopped or contains failed recordings; inspect local call logs.\n")


if __name__ == "__main__":
    main()
