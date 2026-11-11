"""Exact, bounded stage checkpoints. Never infer geometry from display contours."""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from app.learn.frames import file_hash
from app.replay_cache import digest
from app.schemas import Protocol
from app.track.geometry import Detection, FrameState

if TYPE_CHECKING:
    from app.config import Settings

VERSION = "tracking-checkpoint-v1"


def checkpoint_key(settings: "Settings", protocol: Protocol, video: Path, color: bool) -> str:
    return digest(
        [VERSION, file_hash(video), protocol.model_dump(by_alias=True), settings.sam_mode, color]
    )


def save_frames(path: Path, key: str, frames: list[FrameState]) -> None:
    arrays: dict[str, Any] = {}
    metadata = []
    for i, frame in enumerate(frames):
        objects: dict[str, Any] = {}
        for j, (name, detection) in enumerate(frame.objects.items()):
            if detection is None:
                objects[name] = None
                continue
            array_key = f"m{i}_{j}"
            if detection.packed_mask is not None:
                arrays[array_key] = np.frombuffer(detection.packed_mask, dtype=np.uint8)
            objects[name] = {
                "array": array_key if detection.packed_mask is not None else None,
                "shape": detection.mask_shape,
                "score": detection.score,
                "class": detection.obj_class,
                "absent": detection.known_absent,
            }
        metadata.append(
            {
                "t": frame.t,
                "width": frame.width,
                "height": frame.height,
                "complete": frame.complete,
                "interactions": frame.interactions,
                "objects": objects,
            }
        )
    arrays["metadata"] = np.frombuffer(
        json.dumps({"key": key, "frames": metadata}).encode(), dtype=np.uint8
    )
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as out:
        np.savez_compressed(out, **arrays)
    temporary.replace(path)


def load_frames(
    path: Path, key: str, paths: list[tuple[float, Path]], maximum: int
) -> list[FrameState] | None:
    if not path.exists():
        return None
    import zipfile

    with zipfile.ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > maximum + 4 * 1024 * 1024:
            raise ValueError("Checkpoint exceeds the mask memory limit")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate checkpoint array")
        for item in archive.infolist():
            if not re.fullmatch(r"metadata\.npy|m[0-9]+_[0-9]+\.npy", item.filename):
                raise ValueError("Unexpected checkpoint array")
            with archive.open(item) as stream:
                version = np.lib.format.read_magic(stream)
                if version == (1, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
                elif version == (2, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream)
                else:
                    raise ValueError("Unsupported checkpoint array version")
                if (
                    len(shape) != 1
                    or dtype != np.uint8
                    or fortran
                    or shape[0] < 0
                    or shape[0] + stream.tell() != item.file_size
                ):
                    raise ValueError("Checkpoint array header exceeds stored bytes")
    with np.load(path, allow_pickle=False) as data:
        meta = json.loads(data["metadata"].tobytes())
        if meta["key"] != key:
            return None
        if len(meta["frames"]) != len(paths):
            raise ValueError("Checkpoint timeline does not match recording")
        frames = []
        for frame, (t, evidence) in zip(meta["frames"], paths, strict=True):
            if frame["t"] != t or not 0 < frame["width"] <= 1024 or not 0 < frame["height"] <= 1024:
                raise ValueError("Invalid checkpoint timeline or dimensions")
            objects: dict[str, Detection | None] = {}
            for name, item in frame["objects"].items():
                if item is None:
                    objects[name] = None
                    continue
                mask = None
                if item["array"] is not None:
                    shape = tuple(item["shape"])
                    if shape != (frame["height"], frame["width"]):
                        raise ValueError("Invalid checkpoint mask dimensions")
                    packed = data[item["array"]]
                    if packed.dtype != np.uint8 or packed.size != (shape[0] * shape[1] + 7) // 8:
                        raise ValueError("Invalid packed checkpoint")
                    mask = (
                        np.unpackbits(packed, count=shape[0] * shape[1])
                        .reshape(shape)
                        .astype(np.bool_)
                    )
                objects[name] = Detection(mask, item["score"], item["class"], item["absent"])
            frames.append(
                FrameState(
                    t,
                    objects,
                    frame["width"],
                    frame["height"],
                    str(evidence),
                    frame["complete"],
                    frame.get("interactions", {}),
                )
            )
    return frames


def persist(settings: "Settings") -> None:
    if settings._checkpoint_callback is not None:
        settings._checkpoint_callback()
