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


def freeze(manifest: Path, data: dict[str, Any], protocol: Path | None = None) -> dict[str, str]:
    result = {"manifest_sha256": sha(manifest)}
    if protocol is not None:
        result["protocol_sha256"] = sha(protocol)
    test = [r for r in data["runs"] if r["split"] == "test"]
    if not test:
        raise ValueError("Cannot freeze an empty test set")
    for r in test:
        result[r["id"]] = sha(manifest.parent / r["video"])
    return result


def pilot_ready(data: dict[str, Any]) -> None:
    runs = data["runs"]
    references = data.get("reference_video_sha256", [])
    if len(set(references)) < 2 or any(not isinstance(h, str) or len(h) != 64 for h in references):
        raise ValueError("Pilot requires distinct teaching/second-video reference hashes")
    if (
        not 6 <= len(runs) <= 8
        or sum(r["split"] == "dev" for r in runs) < 2
        or sum(r["split"] == "test" for r in runs) < 4
    ):
        raise ValueError("Pilot needs 6–8 independent recordings: at least 2 dev and 4 test")
    if any(r.get("source") != "real" or r.get("labels_confirmed") is not True for r in runs):
        raise ValueError("Confirm labels for every real recording before freezing the pilot")
    for run in runs:
        for event in run["events"]:
            if (
                event.get("kind") not in KINDS
                or not isinstance(event.get("step_id"), str)
                or not math.isfinite(float(event["t"]))
                or float(event["t"]) < 0
            ):
                raise ValueError("Invalid pilot event label")


def evaluate(
    manifest: Path, frozen: Path, out: Path, *, pilot: bool = False, protocol: Path | None = None
) -> None:
    data = json.loads(manifest.read_text())
    runs = data["runs"]
    if pilot:
        if protocol is None:
            raise ValueError("Pilot requires --protocol to freeze the exact rules")
        pilot_ready(data)
    elif sum(r["split"] == "test" for r in runs) < 6 or sum(r["split"] == "dev" for r in runs) < 6:
        raise ValueError("Need at least 6 independently labelled real dev and 6 test recordings")
    if any(r.get("source") != "real" for r in runs):
        raise ValueError("Real evaluation cannot include synthetic recordings")
    expected = json.loads(frozen.read_text())
    if freeze(manifest, data, protocol) != expected:
        raise ValueError("Frozen test manifest or recording changed; do not tune on the test set")
    hashes = [sha(manifest.parent / r["video"]) for r in runs]
    if pilot and set(hashes) & set(data["reference_video_sha256"]):
        raise ValueError("Teaching/validation footage cannot be an evaluation recording")
    if len(hashes) != len(set(hashes)):
        raise ValueError("Duplicate recording across evaluation runs")
    truth: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    shadow_available = shadow_agree = cloud = local = 0
    state_total = unconfirmed = state_runs = 0
    for run in runs:
        if run["split"] != "test":
            continue
        predicted = json.loads((manifest.parent / run["prediction"]).read_text())
        if (
            predicted.get("provenance") != "live-recording"
            or predicted.get("video_sha256") != expected[run["id"]]
        ):
            raise ValueError("Prediction provenance or source-video hash mismatch")
        states = predicted.get("states")
        if isinstance(states, dict):
            state_runs += 1
            state_total += len(states)
            unconfirmed += sum(value != "DONE" for value in states.values())
        # Include run id in matching identity so adjacent runs can never match one another.
        for e in run["events"]:
            truth.append({**e, "step_id": run["id"] + ":" + str(e.get("step_id"))})
        for e in predicted["events"]:
            if e.get("tier", "rules") != "rules":
                continue
            predictions.append({**e, "step_id": run["id"] + ":" + str(e.get("step_id"))})
        calls.extend(predicted["metrics"].get("calls", []))
        for s in predicted.get("shadow", []):
            if s.get("available"):
                shadow_available += 1
                shadow_agree += bool(s.get("agree"))
    lines = [
        "# Small real-video pilot" if pilot else "# Frozen real-video evaluation",
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
    for tier in sorted({str(c["tier"]) for c in calls}):
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
        f"Unconfirmed configured steps: {unconfirmed}/{state_total} across {state_runs} test runs with saved states."
        if state_runs
        else "Step-state coverage was not recorded; no completion-rate claim.",
        f"Cloud transmissions: {cloud}; on-device transmissions: {local}.",
        "",
        "Pilot results are descriptive and do not establish production accuracy."
        if pilot
        else "Full evaluation protocol used.",
        "Small samples have wide uncertainty. Wilson intervals apply to event counts, not independent operators; repeated errors in one run are correlated.",
        "Call latency includes the request round trip; it excludes local job waiting, capture/sampling, encoding and checkpoint storage. It is not physical-error detection latency.",
        f"Frozen manifest SHA-256: `{expected['manifest_sha256']}`",
    ]
    out.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("eval/labels.json"))
    parser.add_argument("--frozen", type=Path, default=Path("eval/frozen_test.json"))
    parser.add_argument("--out", type=Path, default=Path("eval/results.md"))
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument(
        "--protocol", type=Path, help="Exact protocol file; required for pilot mode"
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="6–8 real recordings, at least 2 dev/4 test; explicitly confirmed labels",
    )
    args = parser.parse_args()
    try:
        if args.freeze:
            if args.frozen.exists():
                raise ValueError(
                    "Freeze already exists; preserve it. Create a new evaluation version explicitly."
                )
            if args.pilot:
                if args.protocol is None:
                    raise ValueError("Pilot requires --protocol")
                pilot_data = json.loads(args.manifest.read_text())
                pilot_ready(pilot_data)
                hashes = [sha(args.manifest.parent / r["video"]) for r in pilot_data["runs"]]
                if len(hashes) != len(set(hashes)) or set(hashes) & set(
                    pilot_data["reference_video_sha256"]
                ):
                    raise ValueError(
                        "Pilot recordings must be independent and exclude teaching/validation footage"
                    )
            args.frozen.write_text(
                json.dumps(
                    freeze(args.manifest, json.loads(args.manifest.read_text()), args.protocol),
                    indent=2,
                )
            )
        else:
            evaluate(args.manifest, args.frozen, args.out, pilot=args.pilot, protocol=args.protocol)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
