"""Frozen, one-to-one event evaluation. Refuses to score missing or synthetic real-test data."""

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

KINDS = ("skipped", "out_of_order", "wrong_object", "dwell_exceeded", "dwell_too_short")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def match_events(
    truth: list[dict[str, Any]], predicted: list[dict[str, Any]], tolerance: float = 2
) -> tuple[int, int, int]:
    """Maximum-cardinality bipartite matching; each prediction can count at most once."""
    neighbors = [
        [
            j
            for j, p in enumerate(predicted)
            if p["kind"] == t["kind"]
            and p.get("step_id") == t.get("step_id")
            and abs(float(p["t"]) - float(t["t"])) <= tolerance
        ]
        for t in truth
    ]
    matched: dict[int, int] = {}

    def augment(i: int, visited: set[int]) -> bool:
        for j in neighbors[i]:
            if j in visited:
                continue
            visited.add(j)
            if j not in matched or augment(matched[j], visited):
                matched[j] = i
                return True
        return False

    count = sum(augment(i, set()) for i in range(len(truth)))
    return count, len(predicted) - count, len(truth) - count


def wilson(successes: int, n: int) -> str:
    if not n:
        return "N/A"
    z = 1.96
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return f"[{center - half:.3f}, {center + half:.3f}]"


def freeze(manifest: Path, data: dict[str, Any]) -> dict[str, str]:
    result = {"manifest_sha256": sha(manifest)}
    test = [r for r in data["runs"] if r["split"] == "test"]
    if not test:
        raise ValueError("Cannot freeze an empty test set")
    for r in test:
        result[r["id"]] = sha(manifest.parent / r["video"])
    return result


def evaluate(manifest: Path, frozen: Path, out: Path) -> None:
    data = json.loads(manifest.read_text())
    runs = data["runs"]
    if sum(r["split"] == "test" for r in runs) < 6 or sum(r["split"] == "dev" for r in runs) < 6:
        raise ValueError("Need at least 6 independently labelled real dev and 6 test recordings")
    if any(r.get("source") != "real" for r in runs):
        raise ValueError("Real evaluation cannot include synthetic recordings")
    expected = json.loads(frozen.read_text())
    if freeze(manifest, data) != expected:
        raise ValueError("Frozen test manifest or recording changed; do not tune on the test set")
    hashes = [sha(manifest.parent / r["video"]) for r in runs]
    if len(hashes) != len(set(hashes)):
        raise ValueError("Duplicate recording across evaluation runs")
    truth: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    shadow_available = shadow_agree = cloud = local = 0
    for run in runs:
        if run["split"] != "test":
            continue
        predicted = json.loads((manifest.parent / run["prediction"]).read_text())
        if (
            predicted.get("provenance") != "live-recording"
            or predicted.get("video_sha256") != expected[run["id"]]
        ):
            raise ValueError("Prediction provenance or source-video hash mismatch")
        # Include run id in matching identity so adjacent runs can never match one another.
        for e in run["events"]:
            truth.append({**e, "step_id": run["id"] + ":" + str(e.get("step_id"))})
        for e in predicted["events"]:
            predictions.append({**e, "step_id": run["id"] + ":" + str(e.get("step_id"))})
        calls.extend(predicted["metrics"].get("calls", []))
        for s in predicted.get("shadow", []):
            if s.get("available"):
                shadow_available += 1
                shadow_agree += bool(s.get("agree"))
    lines = [
        "# Frozen real-video evaluation",
        "",
        f"Test runs: {sum(r['split'] == 'test' for r in runs)}. "
        "Event tolerance ±2 s; exact type and step; one-to-one maximum matching.",
        "",
        "| Type | TP | FP | FN | Precision | Recall | F1 | Precision 95% Wilson | Recall 95% Wilson |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for kind in KINDS:
        tp, fp, fn = match_events(
            [e for e in truth if e["kind"] == kind], [e for e in predictions if e["kind"] == kind]
        )
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None

        def fmt(x: float | None) -> str:
            return f"{x:.3f}" if x is not None else "N/A"

        lines.append(
            f"| {kind} | {tp} | {fp} | {fn} | {fmt(precision)} | {fmt(recall)} | {fmt(f1)} | {wilson(tp, tp + fp)} | {wilson(tp, tp + fn)} |"
        )
    lines += [
        "",
        "## Model call latency",
        "",
        "| Tier | n | Median ms | p95 ms |",
        "|---|---:|---:|---:|",
    ]
    for tier in ("sam", "spark", "glimmer", "voice"):
        values = sorted(float(c["latency_ms"]) for c in calls if c["tier"] == tier)
        if values:
            lines.append(
                f"| {tier} | {len(values)} | {statistics.median(values):.1f} | {values[math.ceil(0.95 * len(values)) - 1]:.1f} |"
            )
    cloud = sum(c.get("cloud_frames", 0) for c in calls)
    local = sum(c.get("local_frames", 0) for c in calls)
    lines += [
        "",
        f"Shadow agreement: {shadow_agree}/{shadow_available} available opinions.",
        f"Cloud transmissions: {cloud}; on-device transmissions: {local}.",
        "",
        "Small samples have wide uncertainty. Wilson intervals apply to event counts, not independent operators; repeated errors in one run are correlated.",
        "Call latency excludes video capture/sampling, queueing and encoding. It is not physical-error detection latency.",
        f"Frozen manifest SHA-256: `{expected['manifest_sha256']}`",
    ]
    out.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("eval/labels.json"))
    parser.add_argument("--frozen", type=Path, default=Path("eval/frozen_test.json"))
    parser.add_argument("--out", type=Path, default=Path("eval/results.md"))
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    try:
        if args.freeze:
            if args.frozen.exists():
                raise ValueError(
                    "Freeze already exists; preserve it. Create a new evaluation version explicitly."
                )
            args.frozen.write_text(
                json.dumps(freeze(args.manifest, json.loads(args.manifest.read_text())), indent=2)
            )
        else:
            evaluate(args.manifest, args.frozen, args.out)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
