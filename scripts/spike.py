"""Explicit paid checks, opt-in after local account configuration. No automatic deployment."""

import argparse
import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import Settings  # noqa: E402
from app.glimmer_client import GlimmerClient  # noqa: E402
from app.learn.frames import sample  # noqa: E402
from app.meta_client import MetaClient, response_text  # noqa: E402
from app.schemas import Opinion  # noqa: E402
from app.track.sam import decode  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--audio", type=Path, help="Mono PCM16 WAV, 16/24 kHz")
    parser.add_argument("--video", type=Path)
    parser.add_argument("--images", type=int, default=2, choices=range(1, 13))
    parser.add_argument("--prompt", default="blue cap")
    parser.add_argument("--allow-paid-calls", action="store_true", required=True)
    args = parser.parse_args()
    settings = Settings()
    settings.require_live()
    job = "spike-" + str(int(time.time()))
    client = MetaClient(settings, job)
    observations: dict[str, object] = {
        "run_id": job,
        "account_access": "pending",
        "billing": "not checked by script",
    }
    try:
        observations["spark_text"] = client.structured(
            "Return completed=true if you can read this text. Describe the test.", Opinion
        ).model_dump()
        observations["account_access"] = "Spark text succeeded; other modalities checked separately"
        observations["spark_image_count_requested"] = args.images
        observations["spark_vision"] = client.structured(
            "Describe only the visible objects; completed means an image was readable.",
            Opinion,
            [args.image] * args.images,
        ).model_dump()
        import cv2

        image = cv2.imread(str(args.image))
        if image is None:
            raise ValueError("Cannot read spike image")
        text = client.segment(args.image, args.prompt, "spike-" + job, 0)
        observations["sam_image_matches"] = len(decode(text, image.shape[1], image.shape[0]))
        if args.audio:
            observations["transcription_turns"] = [
                t.model_dump() for t in client.transcribe(args.audio)
            ]
        if args.video:
            sampled = sample(args.video, settings.data_dir / "runs" / job / "frames")
            sequence_matches = []
            for i, (_, path) in enumerate(sampled[:3]):
                frame = cv2.imread(str(path))
                if frame is None:
                    raise ValueError("Cannot read sampled spike frame")
                wire = client.segment(path, args.prompt, job, i + 1)
                sequence_matches.append(len(decode(wire, frame.shape[1], frame.shape[0])))
            observations["sam_frame_sequence_matches"] = sequence_matches
            # Native video shape verified in Meta's segmenting docs. Keep clips short for this spike.
            if args.video.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Native video spike limited to 10 MB; use a short clip")
            raw = client.call(
                "responses",
                "sam",
                "sam-3.1",
                {
                    "model": "sam-3.1",
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": args.prompt},
                                {
                                    "type": "input_video",
                                    "video_url": "data:video/mp4;base64,"
                                    + base64.b64encode(args.video.read_bytes()).decode(),
                                },
                            ],
                        }
                    ],
                },
                frames=len(sampled),
                reserve_usd=0.05,
            )
            observations["sam_video_output_chars"] = len(response_text(raw))
            observations["sam_video_usage"] = raw.get("usage")
        if settings.glimmer_base_url:
            observations["glimmer_vision"] = (
                GlimmerClient(settings, job)
                .opinion("Describe this image. completed=true if readable.", [args.image])
                .model_dump()
            )
        else:
            observations["glimmer_vision"] = "pending endpoint configuration"
    finally:
        client.close()
        target = settings.data_dir / "runs" / job / "observations.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(observations, indent=2))
        print(f"Observations: {target}; latency/usage/reservations in calls.jsonl. No keys logged.")


if __name__ == "__main__":
    main()
