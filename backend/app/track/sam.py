from pathlib import Path

import cv2
import numpy as np
from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format

from app.meta_client import MetaClient
from app.schemas import Protocol
from app.track.fallback_color import segment_color
from app.track.geometry import Detection, FrameState


def decode(text: str, width: int, height: int) -> list[Detection]:
    parser = image_segmentation_format().create_parser()
    parser.push(text)
    result = parser.finish(CompletedOutcome()).result
    if result.diagnostics:
        raise ValueError("SAM parser reported diagnostics; refusing uncertain geometry")
    detections: list[Detection] = []
    for record in result.records:
        if record.kind != "mask":
            continue
        raster = np.frombuffer(bytes(decode_mask_to_raster(record.mask)), dtype=np.uint8)
        small = raster.reshape(record.mask.height, record.mask.width)
        x, y = int(record.bounds.left), int(record.bounds.top)
        right, bottom = int(record.bounds.right), int(record.bounds.bottom)
        if x < 0 or y < 0 or right > width or bottom > height or right <= x or bottom <= y:
            raise ValueError("SAM geometry outside source image")
        full = np.zeros((height, width), dtype=np.bool_)
        full[y:bottom, x:right] = (
            cv2.resize(small, (right - x, bottom - y), interpolation=cv2.INTER_NEAREST) > 0
        )
        # Missing model confidence stays uncertain; it is never fabricated as 1.0.
        detections.append(
            Detection(full, record.confidence if record.confidence is not None else 0.5)
        )
    return detections


def track(
    client: MetaClient,
    protocol: Protocol,
    frames: list[tuple[float, Path]],
    video_hash: str,
    color_fallback: bool = False,
) -> list[FrameState]:
    states: list[FrameState] = []
    for idx, (t, path) in enumerate(frames):
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError("Cannot decode sampled frame")
        h, w = image.shape[:2]
        objects: dict[str, Detection | None] = {}
        for obj in protocol.objects:
            if color_fallback and obj.hsv_lower is not None:
                objects[obj.name] = segment_color(image.astype(np.uint8), obj)
                continue
            candidates = decode(client.segment(path, obj.sam_prompt, video_hash, idx), w, h)
            if len(candidates) == 1:
                d = candidates[0]
                objects[obj.name] = Detection(d.mask, d.score, obj.obj_class)
            else:
                # Image-keyframe identity is unsafe for identical candidates. Require distinct props.
                objects[obj.name] = None
        states.append(FrameState(t, objects, w, h, str(path), complete=False))
    return states
