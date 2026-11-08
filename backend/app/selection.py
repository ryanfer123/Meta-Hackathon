"""Explicit video selections. Original uploads remain untouched for playback/audit."""

import json
import math
import subprocess
from pathlib import Path
from typing import Any

from app.learn.frames import file_hash
from app.replay_cache import digest
from app.track.native_video import probe_video


def selection(
    video: Path, start: float | None, end: float | None, maximum_s: float
) -> dict[str, Any] | None:
    if start is None and end is None:
        return None
    duration = float(probe_video(video)["duration_s"])
    a, b = start if start is not None else 0.0, end if end is not None else duration
    if (
        not all(math.isfinite(v) for v in (a, b, duration))
        or not 0 <= a < b <= duration + 1e-6
        or b - a < 1.5
        or b - a > maximum_s
    ):
        raise ValueError(
            f"Choose a section between 1.5 and {maximum_s:g} seconds, within the recording"
        )
    return {
        "start": a,
        "end": min(b, duration),
        "source_duration": duration,
        "source_sha256": file_hash(video),
    }


def selected_video(video: Path) -> tuple[Path, float, dict[str, Any] | None]:
    path = video.parent / "selection.json"
    selected = json.loads(path.read_text()).get(video.name) if path.exists() else None
    if not selected:
        return video, 0.0, None
    if selected["source_sha256"] != file_hash(video):
        raise ValueError("Recording changed after its section was selected")
    start, end = float(selected["start"]), float(selected["end"])
    if start == 0 and end == selected["source_duration"]:
        return video, 0.0, selected
    key = digest(["exact-section-v1", selected])
    role = digest(video.name)[:8]
    target = video.parent / ("selected-" + role + "-" + key + ".mp4")
    if not target.exists():
        temporary = target.with_suffix(".tmp.mp4")
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-nostdin",
                    "-y",
                    "-ss",
                    str(start),
                    "-i",
                    str(video),
                    "-t",
                    str(end - start),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "18",
                    "-c:a",
                    "aac",
                    "-map_metadata",
                    "-1",
                    "-movflags",
                    "+faststart",
                    str(temporary),
                ],
                capture_output=True,
                timeout=300,
                check=False,
            )
            if result.returncode or not temporary.exists():
                raise ValueError(
                    "Could not prepare the selected section. Choose an H.264 recording."
                )
            if temporary.stat().st_size > 100 * 1024 * 1024:
                raise ValueError("Selected section is too large. Compress the source recording.")
            temporary.replace(target)
            # Prune only this input's derived selections, never original uploads or another take.
            for old in video.parent.glob("selected-" + role + "-*.mp4"):
                if old != target:
                    old.unlink(missing_ok=True)
        except FileNotFoundError as exc:
            raise RuntimeError("FFmpeg is required to trim recordings") from exc
        finally:
            temporary.unlink(missing_ok=True)
    return target, start, selected
