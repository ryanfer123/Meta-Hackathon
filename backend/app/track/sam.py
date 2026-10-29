import re
from pathlib import Path

import cv2
import httpx
import numpy as np
from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format

from app.meta_client import MetaClient
from app.schemas import ObjectSpec, Protocol
from app.track.fallback_color import segment_color
from app.track.geometry import Detection, FrameState, centroid
from app.track.native_video import (
    NativeVideoNoMatches,
    NativeVideoTooLarge,
    ParsedVideo,
    PreparedVideo,
    parse_video_masks,
    prepare_video,
)


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


def _native_size_rejection(exc: Exception) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code != 413:
        return False
    try:
        error = exc.response.json().get("error", {})
        return isinstance(error, dict) and error.get("code") == "payload_too_large"
    except (ValueError, AttributeError):
        return False


def _natural_name(name: str) -> list[tuple[int, str | int]]:
    return [(1, int(part)) if part.isdigit() else (0, part) for part in re.split(r"(\d+)", name)]


def _unambiguous_masks(objects: dict[str, Detection], count: int) -> bool:
    if len(objects) != count:
        return False
    masks = [d.mask for d in objects.values()]
    if any(mask is None or not mask.any() for mask in masks):
        return False
    for i, a in enumerate(masks):
        if a is None:
            return False
        for b in masks[i + 1 :]:
            if b is None or np.any(a & b):
                return False
    xs = sorted(centroid(mask)[0] for mask in masks if mask is not None)
    return all(right - left > 1 for left, right in zip(xs, xs[1:]))


def _map_native_group(
    parsed: ParsedVideo,
    objects: list[ObjectSpec],
    prepared: PreparedVideo,
    states: list[FrameState],
) -> None:
    if not parsed.valid:
        return
    names = sorted(objects, key=lambda obj: _natural_name(obj.name))
    binding: dict[str, ObjectSpec] | None = None
    retired = False
    sampled: dict[int, list[FrameState]] = {}
    for state in states:
        index = min(prepared.frame_count - 1, max(0, int(state.t * prepared.fps + 0.5)))
        sampled.setdefault(index, []).append(state)
    for index in range(prepared.frame_count):
        matches = parsed.frames.get(index, {})
        unambiguous = _unambiguous_masks(matches, len(names))
        if binding is None and unambiguous:

            def center_x(object_id: str) -> float:
                mask = matches[object_id].mask
                return centroid(mask)[0] if mask is not None else float("inf")

            ordered_ids = sorted(matches, key=center_x)
            binding = dict(zip(ordered_ids, names, strict=True))
        elif binding is not None and (set(matches) != set(binding) or not unambiguous):
            # After full visibility loss or identity churn, the API explicitly does not
            # guarantee re-entry identity. Never reassign a familiar numeric ID by guess.
            retired = True
        if binding is None or retired:
            continue
        for state in sampled.get(index, []):
            for object_id, obj in binding.items():
                detection = matches[object_id]
                mask = detection.mask
                if mask is None:
                    continue
                restored = (
                    cv2.resize(
                        mask.astype(np.uint8),
                        (state.width, state.height),
                        interpolation=cv2.INTER_NEAREST,
                    )
                    > 0
                )
                state.objects[obj.name] = Detection(restored, detection.score, obj.obj_class)


def track_video(
    client: MetaClient,
    protocol: Protocol,
    video: Path,
    frames: list[tuple[float, Path]],
    video_hash: str,
    color_fallback: bool = False,
) -> list[FrameState]:
    """Use one native request per concept; missing, split or re-entering IDs stay unknown.

    Output records reference the CFR prepared clip's source indices, not a billed
    usage count or a line ordinal. No nearest-visible-mask interpolation is allowed.
    """
    states: list[FrameState] = []
    groups: dict[str, list[ObjectSpec]] = {}
    for obj in protocol.objects:
        if not (color_fallback and obj.hsv_lower is not None):
            groups.setdefault(obj.sam_prompt.strip(), []).append(obj)
    for t, path in frames:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError("Cannot decode sampled evidence frame")
        h, w = image.shape[:2]
        detections: dict[str, Detection | None] = {obj.name: None for obj in protocol.objects}
        if color_fallback:
            for obj in protocol.objects:
                if obj.hsv_lower is not None:
                    detections[obj.name] = segment_color(image.astype(np.uint8), obj)
        states.append(FrameState(t, detections, w, h, str(path), complete=False))
    if not groups:
        return states
    try:
        prepared = prepare_video(
            video,
            client.settings.data_dir / "cache" / "native-video",
            client.settings.sam_video_max_bytes,
        )
    except NativeVideoTooLarge:
        client.tracking_notice(
            "image_fallback",
            "Prepared clip exceeds inline byte cap; using the separately budgeted image path once",
        )
        return track(client, protocol, frames, video_hash, color_fallback)
    if prepared.source_sha256 != video_hash:
        raise ValueError("Prepared SAM video does not match recording hash")
    for prompt, objects in groups.items():
        if len(objects) > 16:
            client.tracking_notice(
                "native_video_unknown",
                "Concept requires more than documented 16 objects; no request sent",
            )
            continue
        try:
            text = client.segment_video(video, prompt, video_hash)
        except (httpx.HTTPStatusError, NativeVideoTooLarge, NativeVideoNoMatches) as exc:
            if not isinstance(
                exc, NativeVideoTooLarge | NativeVideoNoMatches
            ) and not _native_size_rejection(exc):
                raise
            if isinstance(exc, NativeVideoNoMatches):
                client.tracking_notice(
                    "native_video_failed",
                    "Completed native response returned zero masks for this concept across the clip",
                )
                detail = "Completed native response had zero masks; using this concept's separately budgeted image path once"
            else:
                detail = "Native video exceeded local byte cap or returned 413 payload_too_large; using this concept's image path once"
            client.tracking_notice(
                "image_fallback",
                detail,
            )
            # track only uses .objects; preserving .steps here avoids inventing a new
            # protocol or weakening the validated reference graph saved to the run.
            partial = protocol.model_copy(update={"objects": objects})
            fallback = track(client, partial, frames, video_hash, color_fallback)
            for state, source in zip(states, fallback, strict=True):
                state.objects.update(source.objects)
            continue
        parsed = parse_video_masks(text, prepared)
        if not parsed.valid:
            client.tracking_notice("native_video_unknown", parsed.reason)
        _map_native_group(parsed, objects, prepared, states)
    return states
