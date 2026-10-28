"""Scaffold a real-recording manifest before inspecting model predictions."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_batch import videos_in  # noqa: E402


def make_manifest(videos: Path, predictions: Path, out: Path, split: str) -> None:
    if split not in {"dev", "test"}:
        raise ValueError("Split must be dev or test")
    sources = videos_in(videos)
    out.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(out.read_text()) if out.exists() else {"runs": []}
    runs = existing["runs"]
    ids = {run["id"] for run in runs}
    paths = {(out.parent / run["video"]).resolve() for run in runs}
    for source in sources:
        run_id = f"{split}-{source.stem}"
        if source.resolve() in paths:
            raise ValueError("A recording is already listed; preserve its labels and split")
        if run_id in ids:
            raise ValueError("Manifest IDs must be unique")
        runs.append(
            {
                "id": run_id,
                "split": split,
                "source": "real",
                "video": os.path.relpath(source.resolve(), out.parent.resolve()),
                "prediction": os.path.relpath(
                    (predictions / f"{source.stem}.prediction.json").resolve(), out.parent.resolve()
                ),
                "events": [],
            }
        )
        ids.add(run_id)
        paths.add(source.resolve())
    # Exclusive creation is unnecessary for a trusted local annotation file, but never
    # mutate existing labels: build a complete value and replace only after validation.
    temporary = out.with_name(out.name + ".tmp")
    temporary.write_text(json.dumps({**existing, "runs": runs}, indent=2) + "\n")
    temporary.replace(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("eval/labels.json"))
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    args = parser.parse_args()
    try:
        make_manifest(args.videos, args.predictions, args.out, args.split)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(f"Manifest: {args.out}. Verify source=real and fill labels before viewing predictions.")


if __name__ == "__main__":
    main()
