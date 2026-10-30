"""Single-request diagnostics. Exact response bodies stay in ignored private run folders."""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import Settings  # noqa: E402
from app.glimmer_client import GlimmerClient  # noqa: E402
from app.meta_client import MetaClient, image_url, response_text  # noqa: E402
from app.track.sam import decode  # noqa: E402

from scripts.spike import native_video_detail  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["sam-image", "sam-video", "open-image"], required=True)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--prompt", default="tube")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-cost-usd", type=float, default=0.10)
    parser.add_argument("--allow-paid-calls", action="store_true", required=True)
    args = parser.parse_args()
    if args.kind == "sam-video" and not args.video:
        parser.error("--video required")
    if args.kind != "sam-video" and not args.image:
        parser.error("--image required")
    if not args.run_id.replace("-", "").isalnum() or not 0 < args.max_cost_usd <= 0.10:
        parser.error("Use an alphanumeric run ID and a cost ceiling in (0, 0.10]")
    settings = Settings().model_copy(
        update={"cloud_jobs": False, "max_run_cost_usd": args.max_cost_usd}
    )
    settings.require_live()
    folder = settings.data_dir / "runs" / args.run_id
    if (folder / f"{args.kind}.observations.json").exists():
        parser.error("This probe already ran; use a fresh explicitly authorized run ID")
    client = MetaClient(settings, args.run_id)
    result: dict[str, object] = {"kind": args.kind, "status": "error"}
    start = time.perf_counter()
    try:
        if args.kind == "sam-video":
            result.update(native_video_detail(client, args.video, args.prompt))
        elif args.kind == "sam-image":
            image = cv2.imread(str(args.image))
            if image is None:
                raise ValueError("Cannot read image")
            raw = client.call(
                "responses",
                "sam",
                "sam-3.1",
                {
                    "model": "sam-3.1",
                    "store": False,
                    "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": args.prompt},
                                {"type": "input_image", "image_url": image_url(args.image)},
                            ],
                        }
                    ],
                },
                frames=1,
                reserve_usd=0.0025,
            )
            client.save_raw_response(raw, "sam-image")
            result.update(
                {
                    "response_status": raw.get("status"),
                    "usage": raw.get("usage"),
                    "mask_count": len(decode(response_text(raw), image.shape[1], image.shape[0])),
                    "response_keys": sorted(raw),
                }
            )
        else:
            # One request, no malformed-answer retry, and a conservative local reservation.
            opinion = GlimmerClient(settings, args.run_id).opinion(
                "Describe the visible objects and their colors. completed only means the image is readable.",
                [args.image],
                max_attempts=1,
                raw_response=folder / "open-image.response.json",
            )
            result.update(
                {
                    "model": settings.glimmer_model,
                    "opinion": opinion.model_dump(),
                    "reserved_usd": 0.05,
                    "billing_cost": "Read provider billing; reservation is not a bill",
                }
            )
        result["status"] = "ok"
    except Exception as exc:
        # Never print provider bodies, credentials, or exception strings.
        result["error_type"] = type(exc).__name__
        result["http_status"] = getattr(getattr(exc, "response", None), "status_code", None)
    finally:
        client.close()
        result["latency_ms"] = (time.perf_counter() - start) * 1000
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{args.kind}.observations.json"
        path.write_text(json.dumps(result, indent=2))
        path.chmod(0o600)
        print(json.dumps(result, indent=2))
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
