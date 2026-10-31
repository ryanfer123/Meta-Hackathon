import base64
import json
import mimetypes
import time
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.budget import Budget
from app.config import Settings
from app.model_output import ModelOutputIncomplete, ensure_complete, json_object_text
from app.replay_cache import ReplayCache, canonical, digest
from app.schemas import TranscriptTurn
from app.track.native_video import (
    TRANSCODE_SETTINGS,
    NativeVideoNoMatches,
    NativeVideoTooLarge,
    parse_video_masks,
    prepare_video,
)

# A conservative local cap on serialized inline requests; provider docs instead
# specify a50MB inline FILE maximum and do not establish a JSON-body maximum.
LOCAL_ENCODED_REQUEST_MAX_BYTES = 50_000_000

T = TypeVar("T", bound=BaseModel)


def image_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("Use a JPEG, PNG or WebP image")
    return "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode()


def response_text(raw: dict[str, Any]) -> str:
    return "".join(
        part.get("text", "")
        for item in raw.get("output", [])
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )


class MetaClient:
    def __init__(
        self, settings: Settings, run_id: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.settings, self.run_id = settings, run_id
        self.budget = Budget(settings)
        self.cache = ReplayCache(settings.data_dir / "cache")
        self.http = httpx.Client(
            base_url="https://api.meta.ai/v1/",
            timeout=120,
            transport=transport,
            headers={"Authorization": "Bearer " + settings.model_api_key.get_secret_value()},
        )

    def close(self) -> None:
        self.http.close()

    def call(
        self,
        endpoint: str,
        kind: str,
        model: str,
        body: dict[str, Any],
        frames: int = 0,
        files: Any = None,
        reserve_usd: float = 0.25,
        sam_frames: int = 0,
    ) -> dict[str, Any]:
        self.settings.require_live()
        if sam_frames < 0 or (sam_frames and kind != "sam"):
            raise ValueError("Video frame reservations require non-negative SAM frames")
        if sam_frames:
            self.budget.reserve(self.run_id, kind, reserve_usd, processed_frames=sam_frames)
        else:
            self.budget.reserve(self.run_id, kind, reserve_usd)
        start = time.perf_counter()
        usage: dict[str, Any] = {}
        status = "error"
        try:
            response = self.http.post(endpoint, json=body if files is None else None, files=files)
            response.raise_for_status()
            raw: dict[str, Any] = response.json()
            usage = raw.get("usage", {})
            if sam_frames:
                billed = usage.get("video_frames_processed")
                if isinstance(billed, int) and not isinstance(billed, bool) and billed >= 0:
                    self.budget.record_video_usage(self.run_id, sam_frames, billed)
            try:
                ensure_complete(raw)
            except ModelOutputIncomplete:
                if kind != "sam":
                    raise
                # Raw SAM callers (notably the observation spike) need partial
                # frame references and diagnostics. Keep the call logged as an
                # error; consumers must not treat partial geometry as evidence.
                return raw
            status = "ok"
            return raw
        finally:
            # Never record headers, raw error bodies, request images, or secrets.
            with self.budget.log_path(self.run_id).open("ab") as log:
                log.write(
                    canonical(
                        {
                            "model": model,
                            "tier": "spark" if kind == "spark" else kind,
                            "latency_ms": (time.perf_counter() - start) * 1000,
                            "usage": usage,
                            "reserved_usd": reserve_usd,
                            "cost_estimate_usd": self.estimate(kind, usage)
                            if not sam_frames or "video_frames_processed" in usage
                            else None,
                            "sam_video_frames_reserved": sam_frames,
                            "sam_video_frames_billed": usage.get("video_frames_processed")
                            if sam_frames
                            else None,
                            "cloud_frames": frames,
                            "status": status,
                        }
                    )
                    + b"\n"
                )

    @staticmethod
    def estimate(kind: str, usage: dict[str, Any]) -> float | None:
        if kind == "sam":
            return (
                float(usage["video_frames_processed"]) * 0.0002
                if "video_frames_processed" in usage
                else 0.0025
            )
        if kind == "spark" and "input_tokens" in usage and "output_tokens" in usage:
            return float(usage["input_tokens"]) * 1.25e-6 + float(usage["output_tokens"]) * 4.25e-6
        return None

    def structured(self, prompt: str, schema: type[T], images: list[Path] | None = None) -> T:
        feedback = ""
        for attempt in range(3):
            content: list[dict[str, Any]] = [
                {
                    "type": "input_text",
                    "text": prompt
                    + "\nReturn JSON only. Schema: "
                    + json.dumps(schema.model_json_schema())
                    + feedback,
                }
            ]
            content.extend({"type": "input_image", "image_url": image_url(p)} for p in images or [])
            raw = self.call(
                "responses",
                "spark",
                "muse-spark-1.3",
                {
                    "model": "muse-spark-1.3",
                    "max_output_tokens": self.settings.spark_max_output_tokens,
                    "input": [{"role": "user", "content": content}],
                },
                len(images or []),
            )
            try:
                return schema.model_validate_json(json_object_text(response_text(raw)))
            except (ValidationError, ValueError) as exc:
                feedback = f"\nPrevious response invalid: {exc}. Correct the JSON."
                if attempt == 2:
                    raise
        raise RuntimeError("unreachable")

    def segment(self, frame: Path, prompt: str, video_hash: str, frame_index: int) -> str:
        key = digest([video_hash, prompt, frame_index, "sam-3.1", "one_bit"])
        cached = self.cache.get("sam", key)
        if cached is not None:
            return str(cached["payload"])
        raw = self.call(
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
                            {"type": "input_image", "image_url": image_url(frame)},
                        ],
                    }
                ],
            },
            frames=1,
            reserve_usd=0.0025,
        )
        try:
            ensure_complete(raw)
        except ModelOutputIncomplete:
            # Image tracking has no response-status channel: no candidates is
            # unknown evidence. Never cache a partial response as a full mask.
            return ""
        text = response_text(raw)
        self.cache.put("sam", key, text, "live-meta-sam-3.1")
        return text

    def tracking_notice(self, event: str, detail: str) -> None:
        # Routing notes contain no response bodies, media, authorization headers or keys.
        path = self.budget.log_path(self.run_id).parent / "tracking.jsonl"
        with path.open("ab") as log:
            log.write(canonical({"event": event, "detail": detail}) + b"\n")

    def save_raw_response(self, raw: dict[str, Any], name: str) -> Path:
        """Private diagnostics: exact response JSON only, never HTTP headers or request bodies."""
        if not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Invalid diagnostic name")
        target = self.budget.log_path(self.run_id).parent / (name + ".response.json")
        target.write_text(json.dumps(raw, indent=2))
        target.chmod(0o600)
        return target

    def segment_video(self, video_path: Path, prompt: str, video_hash: str) -> str:
        prepared = prepare_video(
            video_path,
            self.settings.data_dir / "cache" / "native-video",
            self.settings.sam_video_max_bytes,
        )
        if prepared.source_sha256 != video_hash:
            raise ValueError("Native video hash does not match its recording")
        key = digest([video_hash, prompt, "sam-3.1-video", TRANSCODE_SETTINGS])
        cached = self.cache.get("sam-video", key)
        if cached is not None:
            text = str(cached["payload"])
            parsed = parse_video_masks(text, prepared)
            if parsed.valid and not any(parsed.frames.values()):
                raise NativeVideoNoMatches("Cached completed video has zero masks")
            return text
        reserved_frames = prepared.billed_frame_reservation
        body = {
            "model": "sam-3.1",
            "store": False,
            "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_video",
                            "video_url": "data:video/mp4;base64,"
                            + base64.b64encode(prepared.path.read_bytes()).decode(),
                        },
                    ],
                }
            ],
        }
        if len(canonical(body)) > LOCAL_ENCODED_REQUEST_MAX_BYTES:
            raise NativeVideoTooLarge("Encoded native request exceeds conservative local byte cap")
        raw = self.call(
            "responses",
            "sam",
            "sam-3.1",
            body,
            frames=prepared.frame_count,
            reserve_usd=reserved_frames * 0.0002,
            sam_frames=reserved_frames,
        )
        if raw.get("status") != "completed":
            self.tracking_notice(
                "native_video_unknown",
                "SAM video response was not completed; no mask evidence accepted or cached",
            )
            return ""
        text = response_text(raw)
        parsed = parse_video_masks(text, prepared)
        if parsed.valid and not any(parsed.frames.values()):
            self.save_raw_response(raw, "sam-video-zero-" + key[:16])
            raise NativeVideoNoMatches(
                "Completed video has zero masks; raw response retained privately"
            )
        if parsed.valid:
            self.cache.put("sam-video", key, text, "live-meta-sam-3.1-video")
        return text

    def transcribe(self, audio: Path) -> list[TranscriptTurn]:
        with audio.open("rb") as file:
            settings = {
                "model": "muse-voice-transcribe-1.0",
                "mode": "ENDPOINTING",
                "audioEncoding": "WAV",
            }
            raw = self.call(
                "asr/transcribe",
                "voice",
                settings["model"],
                {},
                files={
                    "request": (None, json.dumps(settings), "application/json"),
                    "audio": ("audio.wav", file, "audio/wav"),
                },
            )
        return [
            TranscriptTurn(start=t["startMs"] / 1000, end=t["endMs"] / 1000, text=t["transcript"])
            for t in raw.get("turns", [])
        ]
