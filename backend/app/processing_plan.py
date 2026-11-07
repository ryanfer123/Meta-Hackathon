"""Local safety checks for longer recordings; never reserves or calls a model."""

import math
from pathlib import Path
from typing import Any

import cv2

from app.budget import SAM_VIDEO_FRAME_USD, BudgetExceeded
from app.config import Settings
from app.schemas import Protocol
from app.track.native_video import PROCESSED_FPS, probe_video


def packed_memory_bytes(protocol: Protocol, frames: list[tuple[float, Path]]) -> int:
    memory = 0
    for _, path in frames:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError("Cannot read the recording's sampled frame.")
        height, width = image.shape[:2]
        memory += ((width * height + 7) // 8) * len(protocol.objects)
    return memory


def plan_long_recording(
    settings: Settings,
    protocol: Protocol,
    video: Path,
    frames: list[tuple[float, Path]],
    color_fallback: bool = False,
) -> dict[str, Any]:
    if len(frames) <= 180:
        return {}
    if settings.sam_mode != "video":
        raise ValueError("Recordings over 90 seconds need faster video tracking.")
    duration = float(probe_video(video)["duration_s"])
    if duration > settings.max_run_duration_s:
        raise ValueError(f"Choose a recording up to {settings.max_run_duration_s} seconds.")
    memory = packed_memory_bytes(protocol, frames)
    if memory > settings.max_run_mask_mb * 1024 * 1024:
        raise ValueError(
            "This recording needs more tracking memory than this server allows. "
            "Choose a shorter recording or a lower-resolution video."
        )
    prompts = {
        obj.sam_prompt.strip()
        for obj in protocol.objects
        if not (color_fallback and obj.hsv_lower is not None)
    }
    processed = max(50, math.ceil(duration * PROCESSED_FPS)) * len(prompts)
    cap = (
        settings.hosted_max_sam_video_frames
        if settings.cloud_jobs
        else settings.max_sam_video_frames
    )
    cost_cap = (
        settings.hosted_max_run_cost_usd if settings.cloud_jobs else settings.max_run_cost_usd
    )
    estimate = processed * SAM_VIDEO_FRAME_USD
    if processed > cap or estimate > cost_cap:
        raise BudgetExceeded(
            f"This recording's base tracking exceeds the job budget "
            f"({processed} processed frames, ${estimate:.2f} estimated reservation). "
            "Choose a shorter recording. No model request has been sent."
        )
    return {
        "duration_s": duration,
        "sampled_frames": len(frames),
        "processed_frames_estimate": processed,
        "base_tracking_reservation_usd": estimate,
        "packed_mask_mb_upper_bound": memory / (1024 * 1024),
        "scope": "Base tracking only; fallbacks and advisory calls are separately budgeted.",
    }


def plan_validation(
    settings: Settings,
    protocol: Protocol,
    first_video: Path,
    first: list[tuple[float, Path]],
    second_video: Path,
    second: list[tuple[float, Path]],
) -> dict[str, Any]:
    """Check both expert videos as one workload before either tracking call."""
    if max(len(first), len(second)) <= 180:
        return {}
    if settings.sam_mode != "video":
        raise ValueError("Enable faster video tracking to validate videos longer than 90 seconds.")
    memory = packed_memory_bytes(protocol, first) + packed_memory_bytes(protocol, second)
    if memory > settings.max_validation_mask_mb * 1024 * 1024:
        raise ValueError(
            "Both expert videos exceed this server's tracking memory limit. Use shorter or lower-resolution videos."
        )
    durations = [float(probe_video(path)["duration_s"]) for path in (first_video, second_video)]
    if max(durations) > settings.max_teaching_duration_s:
        raise ValueError(
            f"Each expert video must be at most {settings.max_teaching_duration_s} seconds."
        )
    prompts = len({obj.sam_prompt.strip() for obj in protocol.objects})
    processed = sum(max(50, math.ceil(seconds * PROCESSED_FPS)) for seconds in durations) * prompts
    frames_cap = (
        settings.hosted_max_sam_video_frames
        if settings.cloud_jobs
        else settings.max_sam_video_frames
    )
    cost_cap = (
        settings.hosted_max_run_cost_usd if settings.cloud_jobs else settings.max_run_cost_usd
    )
    estimate = processed * SAM_VIDEO_FRAME_USD
    if processed > frames_cap or estimate > cost_cap:
        raise BudgetExceeded(
            "The combined expert-video tracking exceeds the validation budget. Use shorter videos. No model request has been sent."
        )
    return {
        "expert_videos": 2,
        "sampled_frames": len(first) + len(second),
        "processed_frames_estimate": processed,
        "base_tracking_reservation_usd": estimate,
        "packed_mask_mb_upper_bound": memory / (1024 * 1024),
        "scope": "Both expert takes; fallbacks, repairs and existing reservations remain separately capped.",
    }
