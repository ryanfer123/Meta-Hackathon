"""Generate a private, offline blind-labelling page. Never loads model predictions."""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.learn.frames import file_hash  # noqa: E402
from app.schemas import Protocol  # noqa: E402
from app.track.native_video import probe_video  # noqa: E402


def export_page(manifest: Path, protocol: Path, out: Path) -> None:
    data = json.loads(manifest.read_text())
    steps = Protocol.model_validate_json(protocol.read_text()).steps
    if not data.get("runs") or any(run.get("source") != "real" for run in data["runs"]):
        raise ValueError("Use a manifest of real recordings")
    data["protocol_sha256"] = file_hash(protocol)
    for run in data["runs"]:
        source = manifest.parent / run["video"]
        run["video_sha256"] = file_hash(source)
        run["filename"] = source.name
        run["video_duration_s"] = float(probe_video(source)["duration_s"])
        run["labels_confirmed"] = False
    payload = json.dumps(
        {"manifest": data, "steps": [{"id": s.id, "title": s.title} for s in steps]}
    ).replace("<", "\\u003c")
    page = (Path(__file__).parent / "label_template.html").read_text().replace("PAYLOAD", payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)


def import_labels(manifest: Path, labelled: Path, protocol: Path) -> None:
    original = json.loads(manifest.read_text())
    steps = {s.id for s in Protocol.model_validate_json(protocol.read_text()).steps}
    edited = json.loads(labelled.read_text())
    if edited.get("protocol_sha256") != file_hash(protocol):
        raise ValueError("Protocol changed since labelling; use a new page")
    if len(original["runs"]) != len(edited["runs"]):
        raise ValueError("Recording list changed")
    for source, labels in zip(original["runs"], edited["runs"], strict=True):
        for key in ("id", "split", "source", "video", "prediction"):
            if labels.get(key) != source[key]:
                raise ValueError("Recording identity or split changed")
        if labels.get("labels_confirmed") is not True or labels.get("video_sha256") != file_hash(
            manifest.parent / source["video"]
        ):
            raise ValueError("Labels are unconfirmed or recording changed")
        if not isinstance(labels.get("events"), list):
            raise ValueError("Invalid events")
        duration = float(probe_video(manifest.parent / source["video"])["duration_s"])
        for event in labels["events"]:
            if (
                event.get("kind")
                not in {
                    "skipped",
                    "out_of_order",
                    "wrong_object",
                    "dwell_exceeded",
                    "dwell_too_short",
                }
                or event.get("step_id") not in steps
                or not math.isfinite(float(event["t"]))
                or not 0 <= float(event["t"]) <= duration
            ):
                raise ValueError("Invalid event label")
        source.update(events=labels["events"], labels_confirmed=True, video_duration_s=duration)
    temporary = manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps(original, indent=2) + "\n")
    temporary.replace(manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/labelling.html"))
    parser.add_argument("--import-labels", type=Path)
    args = parser.parse_args()
    try:
        if args.import_labels:
            if not args.protocol:
                raise ValueError("--protocol is required to validate imported step labels")
            import_labels(args.manifest, args.import_labels, args.protocol)
        elif args.protocol:
            export_page(args.manifest, args.protocol, args.out)
        else:
            raise ValueError("--protocol is required to create the labelling page")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
