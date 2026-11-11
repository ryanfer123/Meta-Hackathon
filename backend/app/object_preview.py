"""Three-frame object grounding preview, explicitly separate from a procedure verdict."""

import base64
from pathlib import Path
from typing import Any

import cv2

from app.config import Settings
from app.learn.frames import file_hash
from app.meta_client import MetaClient
from app.progress import JobProgress
from app.replay_cache import atomic_json
from app.samples import wire_frame
from app.schemas import Protocol
from app.selection import selected_video
from app.track.native_video import probe_video
from app.track.sam import track


def preview_paths(video: Path, folder: Path, side: int) -> list[tuple[float, Path]]:
    duration = float(probe_video(video)["duration_s"])
    times = [0.0, duration / 2, max(0.0, duration - 0.5)]
    cap = cv2.VideoCapture(str(video))
    paths = []
    try:
        for index, t in enumerate(times):
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, image = cap.read()
            if not ok:
                raise ValueError("Cannot decode preview frames. Choose H.264 MP4 or MOV.")
            h, w = image.shape[:2]
            image = cv2.resize(
                image, (max(1, int(w * side / max(h, w))), max(1, int(h * side / max(h, w))))
            )
            path = folder / f"preview_{index}.jpg"
            cv2.imwrite(str(path), image)
            paths.append((t, path))
    finally:
        cap.release()
    return paths


def descriptions(protocol: Protocol, prompts: dict[str, str]) -> Protocol:
    if set(prompts) != {obj.name for obj in protocol.objects} or any(
        not value.strip() or len(value) > 200 for value in prompts.values()
    ):
        raise ValueError("Provide a short visual description for every existing object")
    result = protocol.model_copy(deep=True)
    changed = False
    for obj in result.objects:
        value = prompts[obj.name].strip()
        changed |= value != obj.sam_prompt
        obj.sam_prompt = value
    if changed:
        result.verified = False
    return result


def process_preview(settings: Settings, job: str, protocol: Protocol) -> None:
    folder = settings.data_dir / "jobs" / job
    client = MetaClient(settings, job)
    try:
        progress = JobProgress(folder)
        progress.update("Choosing three preview frames")
        video, offset, chosen = selected_video(folder / "original.mp4")
        paths = preview_paths(video, folder, protocol.frame_max_side)
        client.tracking_progress = lambda done, total, unit: progress.update(
            "Previewing the objects", done, total, unit
        )
        frames = track(client, protocol, paths, file_hash(video))
        wired: list[dict[str, Any]] = []
        for frame, (_, path) in zip(frames, paths, strict=True):
            wired.append(
                {
                    **wire_frame(frame),
                    "image": "data:image/jpeg;base64,"
                    + base64.b64encode(path.read_bytes()).decode(),
                }
            )
        for item in wired:
            item["t"] += offset
        atomic_json(
            folder / "run.json",
            {
                "id": job,
                "status": "ready",
                "phase": "object-preview",
                "next_tracking_mode": settings.sam_mode,
                "duration_s": float(probe_video(video)["duration_s"]),
                "analysis_range": chosen,
                "name": "Object preview",
                "protocol": protocol.model_dump(by_alias=True),
                "frames": wired,
                "scope": "Three sampled images only. This is not full tracking, validation or a step-completion result.",
                "objects": [
                    {
                        "name": obj.name,
                        "visible_frames": sum(
                            (d := f.objects.get(obj.name)) is not None and d.area > 0
                            for f in frames
                        ),
                        "total_frames": len(frames),
                    }
                    for obj in protocol.objects
                ],
            },
        )
    except Exception:
        # Provider bodies and credentials never become a user-facing error.
        atomic_json(
            folder / "run.json",
            {
                "id": job,
                "status": "error",
                "resumable": True,
                "error": "Object preview could not finish. Review the file, service connection and budget before retrying.",
            },
        )
    finally:
        client.close()
