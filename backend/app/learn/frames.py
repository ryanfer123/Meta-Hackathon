import hashlib
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np


def sample(
    video: Path,
    output: Path,
    fps: float = 2,
    max_frames: int = 180,
    max_side: int = 1024,
    upscale: bool = False,
) -> list[tuple[float, Path]]:
    if not 0 < fps <= 4:
        raise ValueError("sampling fps must be 0-4")
    if not 64 <= max_side <= 1024:
        raise ValueError("Sampled frame side must be between 64 and 1024 pixels")
    output.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError("Cannot decode recording. Use H.264 MP4 or MOV.")
    native_fps = cap.get(cv2.CAP_PROP_FPS)
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if native_fps <= 0 or total <= 0 or total / native_fps > max_frames / fps:
        cap.release()
        raise ValueError(
            f"Recording must be at most {max_frames / fps:.0f}s with valid timestamps."
        )
    frames: list[tuple[float, Path]] = []
    try:
        # Include the last sampling point before a fractional-second end. Flooring
        # the count silently dropped up to one evidence interval from every clip.
        for i in range(min(max_frames, math.ceil(total / native_fps * fps))):
            t = i / fps
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, image = cap.read()
            if not ok:
                break
            height, width = image.shape[:2]
            if max(width, height) > max_side or (upscale and max(width, height) != max_side):
                image = cv2.resize(
                    image,
                    (
                        int(width * max_side / max(width, height)),
                        int(height * max_side / max(width, height)),
                    ),
                )
            path = output / f"frame_{i:04d}_{t:07.3f}.jpg"
            cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frames.append((t, path))
    finally:
        cap.release()
    if len(frames) < 3:
        raise ValueError("Recording too short: at least three sampled frames are required.")
    return frames


def keyframes(frames: list[tuple[float, Path]], limit: int = 12) -> list[Path]:
    selected: list[Path] = []
    last = None
    for _, path in frames:
        raw = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if raw is None:
            raise ValueError("Cannot read sampled frame")
        image = cv2.resize(raw, (64, 64))
        if last is None or float(cv2.absdiff(image, last).mean()) >= 8:
            selected.append(path)
            last = image
    if frames[-1][1] not in selected:
        selected.append(frames[-1][1])
    if len(selected) > limit:
        selected = [selected[int(i)] for i in np.linspace(0, len(selected) - 1, limit)]
    return selected


def teaching_keyframes(frames: list[tuple[float, Path]]) -> list[Path]:
    """Cover longer teaching clips with at most 50 time-stratified images.

    Keep both endpoints and the largest observed visual change in each interior
    time bin. This is frame selection, not proof that every brief action is visible.
    """
    if len(frames) <= 180:
        return keyframes(frames)
    changes: list[float] = []
    previous = None
    for _, path in frames:
        raw = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if raw is None:
            raise ValueError("Cannot read teaching frame")
        image = cv2.resize(raw, (64, 64))
        changes.append(0.0 if previous is None else float(cv2.absdiff(image, previous).mean()))
        previous = image
    bins = np.array_split(np.arange(len(frames)), min(50, len(frames)))
    selected = [int(bucket[int(np.argmax([changes[int(i)] for i in bucket]))]) for bucket in bins]
    selected[0], selected[-1] = 0, len(frames) - 1
    return [frames[index][1] for index in selected]


def extract_audio(video: Path, target: Path) -> None:
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
                "-ac",
                "1",
                "-ar",
                "24000",
                "-c:a",
                "pcm_s16le",
                "-map_metadata",
                "-1",
                str(target),
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is required for narrated recordings.") from exc
    if result.returncode:
        raise ValueError("No supported audio track; provide timestamped narration JSON instead.")


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
