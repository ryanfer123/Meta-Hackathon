"""Small provider boundaries. Adapters return geometry/opinions, never step verdicts."""

from pathlib import Path
from typing import Protocol as Interface

from app.meta_client import MetaClient
from app.schemas import Opinion, Protocol
from app.track.geometry import FrameState
from app.track.sam import track, track_video


class TrackingProvider(Interface):
    provider_id: str

    def track(
        self,
        protocol: Protocol,
        video: Path,
        paths: list[tuple[float, Path]],
        video_hash: str,
        color: bool = False,
    ) -> list[FrameState]: ...


class OpinionProvider(Interface):
    def __call__(self, prompt: str, images: list[Path]) -> Opinion: ...


class MetaTrackingProvider:
    provider_id = "meta-sam-3.1-v1"

    def __init__(self, client: MetaClient):
        self.client = client

    def track(
        self,
        protocol: Protocol,
        video: Path,
        paths: list[tuple[float, Path]],
        video_hash: str,
        color: bool = False,
    ) -> list[FrameState]:
        if self.client.settings.sam_mode == "video":
            return track_video(self.client, protocol, video, paths, video_hash, color)
        return track(self.client, protocol, paths, video_hash, color)
