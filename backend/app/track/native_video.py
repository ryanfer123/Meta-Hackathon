"""Local CFR video preparation and conservative native SAM parsing. No model calls."""

import json
import math
import subprocess
import uuid
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, video_segmentation_format

from app.learn.frames import file_hash
from app.replay_cache import digest
from app.track.geometry import Detection

PROCESSED_FPS = 4
MAX_SIDE = 640
# General inline-file limit, not a promise about encoded JSON-body limits.
# https://dev.meta.ai/docs/file-handling
PROVIDER_INLINE_FILE_BYTES = 50_000_000
TRANSCODE_SETTINGS = {
    "version": 1,
    "codec": "h264",
    "fps": PROCESSED_FPS,
    "max_side": MAX_SIDE,
    "pixel_format": "yuv420p",
    "crf": 26,
    "audio": False,
    "source_pts": "zero",
    "fps_filter": True,
}


class NativeVideoTooLarge(ValueError):
    """Prepared bytes exceed the local cap or documented general inline-file cap."""


class NativeVideoNoMatches(ValueError):
    """A completed native response has no masks; retry this concept as images once."""


@dataclass(frozen=True)
class PreparedVideo:
    path: Path
    source_sha256: str
    width: int
    height: int
    frame_count: int
    duration_s: float
    fps: float

    @property
    def billed_frame_reservation(self) -> int:
        # Meta's usage.video_frames_processed reports billed frames, minimum 50/request.
        return max(50, self.frame_count, math.ceil(self.duration_s * PROCESSED_FPS))


@dataclass(frozen=True)
class ParsedVideo:
    frames: dict[int, dict[str, Detection]]
    valid: bool
    reason: str = ""


def probe_video(path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,avg_frame_rate,r_frame_rate,nb_frames,duration:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg and ffprobe are required for native SAM tracking") from exc
    if result.returncode:
        raise ValueError("Cannot inspect the local recording")
    try:
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        duration = float(stream.get("duration") or payload.get("format", {}).get("duration", 0))
        fps = float(Fraction(stream["avg_frame_rate"]))
        width, height = int(stream["width"]), int(stream["height"])
        if not all(math.isfinite(value) and value > 0 for value in (duration, fps, width, height)):
            raise ValueError("Invalid video dimensions or timing")
        frames = stream.get("nb_frames")
        frame_count = int(frames) if frames and str(frames).isdigit() else math.ceil(duration * fps)
        return {
            "width": width,
            "height": height,
            "duration_s": duration,
            "fps": fps,
            "frame_count": frame_count,
            "codec": stream["codec_name"],
        }
    except (ValueError, KeyError, IndexError, TypeError, ZeroDivisionError) as exc:
        raise ValueError("Cannot establish recording dimensions and timing") from exc


def prepared_info(path: Path, source_sha256: str, max_bytes: int) -> PreparedVideo:
    if path.stat().st_size > min(max_bytes, PROVIDER_INLINE_FILE_BYTES):
        raise NativeVideoTooLarge("Prepared native SAM video exceeds configured inline-byte cap")
    info = probe_video(path)
    if info["codec"] != "h264" or max(info["width"], info["height"]) > MAX_SIDE:
        raise ValueError("Prepared SAM video has unexpected codec or dimensions")
    if not math.isclose(info["fps"], PROCESSED_FPS, abs_tol=1e-6):
        raise ValueError("Prepared SAM video must be constant-rate 4 fps")
    if info["frame_count"] <= 0 or info["frame_count"] > 15000:
        raise ValueError("Prepared SAM video exceeds documented 15,000-frame limit")
    return PreparedVideo(
        path,
        source_sha256,
        info["width"],
        info["height"],
        info["frame_count"],
        info["duration_s"],
        info["fps"],
    )


def prepare_video(video: Path, cache_dir: Path, max_bytes: int) -> PreparedVideo:
    if max_bytes <= 0:
        raise ValueError("Native video byte cap must be positive")
    source_sha256 = file_hash(video)
    key = digest([source_sha256, TRANSCODE_SETTINGS])
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / (key + ".mp4")
    if target.exists():
        return prepared_info(target, source_sha256, max_bytes)
    source = probe_video(video)
    if source["duration_s"] > 90:
        raise ValueError("Recording must be at most 90 seconds for native tracking")
    temporary = cache_dir / (key + "." + uuid.uuid4().hex + ".mp4")
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(video),
                "-map",
                "0:v:0",
                "-an",
                "-sn",
                "-dn",
                "-vf",
                "setpts=PTS-STARTPTS,fps=4,scale=w='min(640,iw)':h='min(640,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
                "-r",
                str(PROCESSED_FPS),
                "-fps_mode",
                "cfr",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "26",
                "-pix_fmt",
                "yuv420p",
                "-map_metadata",
                "-1",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            check=False,
            capture_output=True,
            timeout=180,
        )
        if result.returncode:
            raise ValueError("Cannot transcode the recording for native SAM tracking")
        info = prepared_info(temporary, source_sha256, max_bytes)
        temporary.replace(target)
        return PreparedVideo(
            target,
            info.source_sha256,
            info.width,
            info.height,
            info.frame_count,
            info.duration_s,
            info.fps,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg and ffprobe are required for native SAM tracking") from exc
    finally:
        temporary.unlink(missing_ok=True)


def parse_video_masks(text: str, video: PreparedVideo) -> ParsedVideo:
    parser = video_segmentation_format().create_parser()
    try:
        parser.push(text)
        result = parser.finish(CompletedOutcome()).result
        if result.diagnostics:
            return ParsedVideo({}, False, "SAM video parser diagnostics; masks remain unknown")
        frames: dict[int, dict[str, Detection]] = {}
        for record in result.records:
            if record.kind != "mask":
                continue
            if record.frame is None:
                return ParsedVideo({}, False, "SAM video mask has no source-frame reference")
            index = record.frame.frame_index
            if index < 0 or index >= video.frame_count:
                return ParsedVideo({}, False, "SAM video frame outside the prepared source")
            if (
                record.identity.media != "video"
                or record.identity.frame_index != index
                or record.identity.object_id != record.object_id
            ):
                return ParsedVideo({}, False, "SAM video identity fields conflict")
            left, top = int(record.bounds.left), int(record.bounds.top)
            right, bottom = int(record.bounds.right), int(record.bounds.bottom)
            if (
                left < 0
                or top < 0
                or right > video.width
                or bottom > video.height
                or right <= left
                or bottom <= top
            ):
                return ParsedVideo({}, False, "SAM video mask outside the prepared source")
            raster = np.frombuffer(bytes(decode_mask_to_raster(record.mask)), dtype=np.uint8)
            small = raster.reshape(record.mask.height, record.mask.width)
            full = np.zeros((video.height, video.width), dtype=np.bool_)
            full[top:bottom, left:right] = (
                cv2.resize(small, (right - left, bottom - top), interpolation=cv2.INTER_NEAREST) > 0
            )
            frame = frames.setdefault(index, {})
            if record.object_id in frame:
                return ParsedVideo({}, False, "Repeated SAM mask identity in one source frame")
            frame[record.object_id] = Detection(
                full, record.confidence if record.confidence is not None else 0.5
            )
        return ParsedVideo(frames, True)
    except (ValueError, TypeError, IndexError) as exc:
        return ParsedVideo({}, False, "SAM video mask could not be decoded: " + type(exc).__name__)
