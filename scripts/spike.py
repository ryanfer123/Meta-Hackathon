"""Explicit paid checks, opt-in after local account configuration. No automatic deployment."""

import argparse
import base64
import json
import math
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import fields
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import Settings  # noqa: E402
from app.glimmer_client import GlimmerClient  # noqa: E402
from app.learn.frames import file_hash, sample  # noqa: E402
from app.meta_client import MetaClient, response_text  # noqa: E402
from app.schemas import Opinion  # noqa: E402
from app.track.sam import decode  # noqa: E402
from meta_sam_parser import (  # noqa: E402
    CompletedOutcome,
    IncompleteOutcome,
    decode_mask_to_raster,
    video_segmentation_format,
)

SAM_SEGMENTING_DOC = "https://dev.meta.ai/docs/sam/segmenting"
SAM_READING_DOC = "https://dev.meta.ai/docs/sam/reading-segmentation"
SAM_LIBRARIES_DOC = "https://dev.meta.ai/docs/sam/client-libraries"
NATIVE_DETAIL_MAX_BYTES = 10 * 1024 * 1024


def video_metadata(video: Path) -> dict[str, Any]:
    """Probe the supplied clip locally; do not infer a service's processing rate."""
    if video.suffix.lower() != ".mp4":
        raise ValueError("Native-video detail spike currently accepts an MP4 clip")
    if video.stat().st_size > NATIVE_DETAIL_MAX_BYTES:
        raise ValueError("Native-video detail spike is locally limited to 10 MiB")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,avg_frame_rate,nb_frames,duration:format=duration",
            "-of",
            "json",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(probe.stdout)
    stream = payload["streams"][0]
    duration = float(stream.get("duration") or payload.get("format", {}).get("duration", 0))
    fps = float(Fraction(stream["avg_frame_rate"]))
    if not math.isfinite(duration) or not math.isfinite(fps) or duration <= 0 or fps <= 0:
        raise ValueError("Cannot establish finite positive clip duration and frame rate")
    if duration > 30:
        raise ValueError("Native-video detail spike is locally limited to 30 seconds")
    if stream["codec_name"] not in {"h264", "hevc", "mpeg4"}:
        raise ValueError("SAM documentation permits H.264, H.265 or MPEG-4 video")
    count = stream.get("nb_frames")
    frame_count = int(count) if count and str(count).isdigit() else math.ceil(duration * fps)
    if frame_count <= 0 or frame_count > 15000:
        raise ValueError("Clip exceeds documented 15,000-frame limit or has no frames")
    return {
        "sha256": file_hash(video),
        "bytes": video.stat().st_size,
        "duration_s": duration,
        "source_average_fps": fps,
        "source_frames": frame_count,
        "source_frame_count_is_estimate": not (count and str(count).isdigit()),
        "codec": stream["codec_name"],
        "width": stream["width"],
        "height": stream["height"],
    }


def summarize_video_response(raw: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Report real parser fields and ID recurrence, without asserting physical identity."""
    parser = video_segmentation_format().create_parser()
    parser.push(response_text(raw))
    outcome = (
        CompletedOutcome() if raw.get("status") == "completed" else IncompleteOutcome("response")
    )
    result = parser.finish(outcome).result
    masks = [record for record in result.records if record.kind == "mask"]
    by_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_object: dict[str, set[int]] = defaultdict(set)
    frame_reference_fields: set[str] = set()
    for record in masks:
        if record.frame is None:
            continue
        index = record.frame.frame_index
        by_object[record.object_id].add(index)
        frame_reference_fields.update(field.name for field in fields(record.frame))
        raster = decode_mask_to_raster(record.mask)
        by_frame[index].append(
            {
                "object_id": record.object_id,
                "identity": {
                    "media": record.identity.media,
                    "frame_index": record.identity.frame_index,
                    "object_id": record.identity.object_id,
                },
                "confidence": record.confidence,
                "mask_shape": [record.mask.height, record.mask.width],
                "raster_pixels": len(raster),
                "bounds": {
                    field.name: getattr(record.bounds, field.name)
                    for field in fields(record.bounds)
                },
            }
        )
    usage = raw.get("usage") or {}
    processed = usage.get("video_frames_processed")
    duration = source["duration_s"]
    processed_fps = (
        float(processed) / duration
        if isinstance(processed, (int, float))
        and not isinstance(processed, bool)
        and math.isfinite(processed)
        and processed >= 0
        else None
    )
    return {
        "response_status": raw.get("status", "unknown"),
        "parser_outcome": result.outcome.status,
        "evidence_status": "unknown"
        if result.diagnostics or result.outcome.status != "completed"
        else "parsed",
        "frame_reference_kind": "zero-based source-video frame index (not a timestamp)",
        "frame_reference_fields": sorted(frame_reference_fields),
        "frame_indices_in_output_order": list(
            dict.fromkeys(
                record.frame.frame_index
                for record in result.records
                if getattr(record, "frame", None) is not None
            )
        ),
        "emitted_frame_count": len(by_frame),
        "emitted_frames_per_source_second": len(by_frame) / duration,
        "processed_frames_per_source_second": processed_fps,
        "processed_fps_scope": "usage.video_frames_processed / source duration; an average, not a proof of regular sampling",
        "mask_object_count": len(by_object),
        "mask_record_count": len(masks),
        "record_kinds": dict(Counter(record.kind for record in result.records)),
        "per_record_fields": {
            kind: sorted(
                {
                    field.name
                    for record in result.records
                    if record.kind == kind
                    for field in fields(record)
                }
            )
            for kind in {record.kind for record in result.records}
        },
        "frames": [
            {"frame_index": index, "masks": records} for index, records in sorted(by_frame.items())
        ],
        "object_id_recurrence": [
            {
                "object_id": object_id,
                "frame_indices": sorted(indices),
                "appears_in_multiple_frames": len(indices) > 1,
            }
            for object_id, indices in sorted(by_object.items())
        ],
        "physical_identity_consistency": "Not established by recurring IDs alone. Inspect the source clip; docs do not guarantee identity through full occlusion or exit/re-entry.",
        "diagnostics": [
            {"severity": diagnostic.severity, "code": diagnostic.code, "line": diagnostic.line}
            for diagnostic in result.diagnostics
        ],
        "usage": usage,
    }


def native_video_detail(client: MetaClient, video: Path, prompt: str) -> dict[str, Any]:
    source = video_metadata(video)
    start = time.perf_counter()
    raw = client.call(
        "responses",
        "sam",
        "sam-3.1",
        {
            "model": "sam-3.1",
            "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_video",
                            "video_url": "data:video/mp4;base64,"
                            + base64.b64encode(video.read_bytes()).decode(),
                        },
                    ],
                }
            ],
        },
        frames=source["source_frames"],
        reserve_usd=max(0.05, source["source_frames"] * 0.0002),
    )
    latency_ms = (time.perf_counter() - start) * 1000
    summary = summarize_video_response(raw, source)
    return {
        "source": source,
        "prompt": prompt,
        "latency_ms": latency_ms,
        "estimated_cost_usd": client.estimate("sam", summary["usage"])
        if summary["processed_frames_per_source_second"] is not None
        else None,
        "request_limits": {
            "documented_max_frames": 15000,
            "documented_max_objects_per_frame": 16,
            "documented_containers": ["MP4", "MOV"],
            "documented_codecs": ["H.264", "H.265", "MPEG-4"],
            "provider_max_request_bytes": None,
            "provider_max_request_bytes_status": "No numeric byte limit found in the checked SAM pages; not measured by one successful clip",
            "local_spike_max_bytes": NATIVE_DETAIL_MAX_BYTES,
            "local_spike_max_duration_s": 30,
            "local_spike_container": "MP4",
            "sources": [SAM_SEGMENTING_DOC, SAM_READING_DOC, SAM_LIBRARIES_DOC],
        },
        **summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path)
    parser.add_argument("--audio", type=Path, help="Mono PCM16 WAV, 16/24 kHz")
    parser.add_argument("--video", type=Path)
    parser.add_argument(
        "--native-video-detail",
        action="store_true",
        help="Only one SAM native-video request; no other modality checks",
    )
    parser.add_argument("--images", type=int, default=2, choices=range(1, 13))
    parser.add_argument("--prompt", default="blue cap")
    parser.add_argument("--allow-paid-calls", action="store_true", required=True)
    args = parser.parse_args()
    if args.native_video_detail and not args.video:
        parser.error("--native-video-detail requires --video")
    if not args.native_video_detail and not args.image:
        parser.error("--image is required for the standard multimodal spike")
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
        if args.native_video_detail:
            try:
                observations["native_video_detail"] = native_video_detail(
                    client, args.video, args.prompt
                )
            except Exception as exc:
                observations["native_video_detail"] = {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "note": "No completed detail observation; inspect local errors without sharing credentials.",
                }
                raise
            observations["account_access"] = (
                "SAM native-video detail only; other modalities not exercised"
            )
            return
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
