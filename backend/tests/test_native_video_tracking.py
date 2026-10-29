"""Native tracking tests: explicit synthetic SAM grammar and mocked HTTP, never paid calls."""

import json
import shutil
import subprocess
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
from app import meta_client
from app.budget import BudgetExceeded
from app.config import Settings
from app.learn.frames import file_hash
from app.meta_client import MetaClient
from app.samples import rect
from app.schemas import Protocol
from app.track import sam
from app.track.geometry import Detection, FrameState, centroid
from app.track.native_video import (
    NativeVideoNoMatches,
    NativeVideoTooLarge,
    PreparedVideo,
    parse_video_masks,
    prepare_video,
)


def protocol():
    return Protocol.model_validate(
        {
            "name": "Synthetic identity test",
            "objects": [
                {"name": "tube_2", "sam_prompt": "tube", "class": "tube"},
                {"name": "tube_1", "sam_prompt": "tube", "class": "tube"},
            ],
            "steps": [
                {"id": "s", "title": "Check tube", "post": [{"op": "present", "obj": "tube_1"}]}
            ],
        }
    )


def settings(tmp_path, **kwargs):
    return Settings(
        _env_file=None, data_dir=tmp_path, replay_mode=False, model_api_key="mock-key", **kwargs
    )


def prepared(tmp_path, source_hash="source", count=8):
    path = tmp_path / "prepared.mp4"
    path.write_bytes(b"synthetic-encoded-placeholder")
    return PreparedVideo(path, source_hash, 64, 64, count, count / 4, 4)


def mask_record(object_id, left, top=6, confidence=True):
    line = (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text().strip()
    record = line.removeprefix("<0f>").replace("3<|box;", f"{object_id}<|box;", 1)
    record = record.replace("x1=5;y1=6;x2=8;y2=9", f"x1={left};y1={top};x2={left + 3};y2={top + 3}")
    return record if confidence else record.replace(";c=0.93", "")


def wire(objects_by_frame):
    return "\n".join(
        f"<{index}f>" + ",".join(mask_record(*spec) for spec in objects)
        for index, objects in objects_by_frame.items()
        if objects
    )


def continuous_tubes():
    return {i: [(11, 5 if i < 4 else 40), (4, 35 if i < 4 else 10)] for i in range(8)}


def evidence(tmp_path):
    frames = []
    for i in range(4):
        path = tmp_path / f"frame_{i}.jpg"
        cv2.imwrite(str(path), np.zeros((128, 128, 3), dtype=np.uint8))
        frames.append((i / 2, path))
    return frames


class MockClient:
    def __init__(self, tmp_path, replies):
        self.settings = settings(tmp_path)
        self.replies = replies
        self.calls = []
        self.notices = []

    def segment_video(self, video, prompt, video_hash):
        self.calls.append(prompt)
        result = self.replies.get(prompt, "")
        if isinstance(result, Exception):
            raise result
        return result

    def tracking_notice(self, event, detail):
        self.notices.append((event, detail))


def test_native_ids_bind_left_to_right_once_and_survive_position_exchange(tmp_path, monkeypatch):
    video = prepared(tmp_path)
    monkeypatch.setattr(sam, "prepare_video", lambda *args: video)
    client = MockClient(
        tmp_path,
        {"tube": wire(continuous_tubes()), "hand": wire({i: [(9, 55, 40)] for i in range(8)})},
    )
    states = sam.track_video(
        client, protocol(), tmp_path / "original.mp4", evidence(tmp_path), "source"
    )
    assert client.calls == ["tube", "hand"]
    assert (
        centroid(states[0].objects["tube_1"].mask)[0]
        < centroid(states[0].objects["tube_2"].mask)[0]
    )
    assert (
        centroid(states[-1].objects["tube_1"].mask)[0]
        > centroid(states[-1].objects["tube_2"].mask)[0]
    )
    assert states[0].objects["tube_1"].mask.shape == (128, 128)
    assert int(states[0].objects["tube_1"].mask.sum()) == 48
    assert states[0].objects["tube_1"].obj_class == "tube"
    assert states[0].objects["tube_1"].score == pytest.approx(0.93)
    assert all(not state.complete for state in states)


@pytest.mark.parametrize(
    "ambiguous", [[], [(11, 5)], [(11, 5), (4, 35), (7, 50)], [(11, 5), (8, 35)], [(11, 5), (4, 5)]]
)
def test_missing_merge_split_changed_or_overlapping_ids_retire_bindings(
    tmp_path, monkeypatch, ambiguous
):
    video = prepared(tmp_path)
    monkeypatch.setattr(sam, "prepare_video", lambda *args: video)
    frames = continuous_tubes()
    frames[3] = ambiguous
    client = MockClient(tmp_path, {"tube": wire(frames)})
    states = sam.track_video(
        client, protocol(), tmp_path / "original.mp4", evidence(tmp_path), "source"
    )
    assert states[0].objects["tube_1"] is not None
    assert all(
        state.objects["tube_1"] is None and state.objects["tube_2"] is None for state in states[2:]
    )


def test_sparse_initial_frames_stay_unknown_without_nearest_visible_interpolation(
    tmp_path, monkeypatch
):
    video = prepared(tmp_path)
    monkeypatch.setattr(sam, "prepare_video", lambda *args: video)
    frames = {i: objects for i, objects in continuous_tubes().items() if i >= 2}
    client = MockClient(tmp_path, {"tube": wire(frames)})
    states = sam.track_video(
        client, protocol(), tmp_path / "original.mp4", evidence(tmp_path), "source"
    )
    assert states[0].objects["tube_1"] is None
    assert states[1].objects["tube_1"] is not None


def test_native_parser_diagnostics_and_out_of_bounds_frames_reject_geometry(tmp_path):
    video = prepared(tmp_path)
    assert not parse_video_masks("<0f>bad", video).valid
    assert not parse_video_masks("<9f>" + mask_record(1, 5), video).valid
    assert not parse_video_masks("<0f>" + mask_record(1, 63), video).valid
    parsed = parse_video_masks("<0f>" + mask_record(1, 5, confidence=False), video)
    assert parsed.valid
    assert parsed.frames[0]["1"].score == 0.5


def test_actual_live_empty_observation_stays_unknown_not_absent(tmp_path, monkeypatch):
    observed = json.loads(
        (Path(__file__).parent / "fixtures/sam_native_empty_observation.json").read_text()
    )
    assert observed["provenance"] == "sanitized-live-empty-summary"
    assert (
        (Path(__file__).parent / "fixtures" / observed["raw_output_file"]).read_text()
        == observed["raw_output"]
        == ""
    )
    video = prepared(tmp_path, count=observed["source_frames"])
    monkeypatch.setattr(sam, "prepare_video", lambda *args: video)
    parsed = parse_video_masks(observed["raw_output"], video)
    assert parsed.valid and parsed.frames == {}
    client = MockClient(tmp_path, {"tube": observed["raw_output"], "hand": ""})
    states = sam.track_video(
        client, protocol(), tmp_path / "original.mp4", evidence(tmp_path), "source"
    )
    assert all(all(d is None for d in state.objects.values()) for state in states)
    assert all(not state.complete for state in states)


def test_video_client_caches_by_source_prompt_and_transcode_settings(tmp_path, monkeypatch):
    source = tmp_path / "original.mp4"
    source.write_bytes(b"synthetic-source-placeholder")
    video = prepared(tmp_path, file_hash(source))
    monkeypatch.setattr(meta_client, "prepare_video", lambda *args: video)
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {"content": [{"type": "output_text", "text": wire(continuous_tubes())}]}
                ],
                "usage": {"video_frames_processed": 50},
            },
        )

    client = MetaClient(settings(tmp_path), "native-cache", httpx.MockTransport(handler))
    try:
        a = client.segment_video(source, "tube", file_hash(source))
        assert client.segment_video(source, "tube", file_hash(source)) == a
        assert len(calls) == 1
        assert calls[0]["store"] is False
        assert calls[0]["input"][0]["content"][1]["type"] == "input_video"
        client.segment_video(source, "cap", file_hash(source))
        assert len(calls) == 2
        monkeypatch.setattr(
            meta_client, "TRANSCODE_SETTINGS", {**meta_client.TRANSCODE_SETTINGS, "version": 999}
        )
        client.segment_video(source, "tube", file_hash(source))
        assert len(calls) == 3
        with pytest.raises(ValueError, match="hash"):
            client.segment_video(source, "tube", "wrong-hash")
    finally:
        client.close()
    logs = [
        json.loads(line)
        for line in (tmp_path / "runs/native-cache/calls.jsonl").read_text().splitlines()
    ]
    assert logs[0]["sam_video_frames_reserved"] == 50
    assert logs[0]["cloud_frames"] == 8
    assert logs[0]["cost_estimate_usd"] == 0.01


def test_video_client_overrun_halts_and_never_caches(tmp_path, monkeypatch):
    source = tmp_path / "original.mp4"
    source.write_bytes(b"synthetic-source-placeholder")
    video = prepared(tmp_path, file_hash(source))
    monkeypatch.setattr(meta_client, "prepare_video", lambda *args: video)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(
            200, json={"status": "completed", "output": [], "usage": {"video_frames_processed": 80}}
        )

    client = MetaClient(settings(tmp_path), "native-overrun", httpx.MockTransport(handler))
    try:
        with pytest.raises(BudgetExceeded):
            client.segment_video(source, "tube", file_hash(source))
        with pytest.raises(BudgetExceeded):
            client.segment_video(source, "tube", file_hash(source))
        assert len(calls) == 1
        assert not (tmp_path / "cache/sam-video").exists()
    finally:
        client.close()


def test_incomplete_native_response_is_unknown_and_uncached(tmp_path, monkeypatch):
    source = tmp_path / "original.mp4"
    source.write_bytes(b"synthetic-source-placeholder")
    monkeypatch.setattr(
        meta_client, "prepare_video", lambda *args: prepared(tmp_path, file_hash(source))
    )
    client = MetaClient(
        settings(tmp_path),
        "native-incomplete",
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "status": "incomplete",
                    "output": [],
                    "usage": {"video_frames_processed": 50},
                },
            )
        ),
    )
    try:
        assert client.segment_video(source, "tube", file_hash(source)) == ""
        assert not (tmp_path / "cache/sam-video").exists()
    finally:
        client.close()


def test_encoded_local_size_rejection_happens_before_any_paid_transport(tmp_path, monkeypatch):
    source = tmp_path / "original.mp4"
    source.write_bytes(b"synthetic-source-placeholder")
    monkeypatch.setattr(
        meta_client, "prepare_video", lambda *args: prepared(tmp_path, file_hash(source))
    )
    monkeypatch.setattr(meta_client, "LOCAL_ENCODED_REQUEST_MAX_BYTES", 50)
    client = MetaClient(
        settings(tmp_path),
        "native-too-large",
        httpx.MockTransport(lambda request: pytest.fail("No model request allowed")),
    )
    try:
        with pytest.raises(NativeVideoTooLarge):
            client.segment_video(source, "tube", file_hash(source))
    finally:
        client.close()


@pytest.mark.parametrize(
    "status,code,fallback",
    [
        (413, "payload_too_large", True),
        (400, None, False),
        (403, "content_policy_violation", False),
        (404, "model_not_found", False),
        (413, "unknown", False),
    ],
)
def test_fallback_is_only_one_explicit_size_rejection_and_only_failed_concept(
    tmp_path, monkeypatch, status, code, fallback
):
    video = prepared(tmp_path)
    monkeypatch.setattr(sam, "prepare_video", lambda *args: video)
    request = httpx.Request("POST", "https://api.meta.ai/v1/responses")
    response = httpx.Response(status, request=request, json={"error": {"code": code}})
    error = httpx.HTTPStatusError("mock rejection", request=request, response=response)
    client = MockClient(tmp_path, {"tube": error, "hand": ""})
    paths = evidence(tmp_path)
    seen = []

    def image_track(client, partial, frames, video_hash, color_fallback):
        seen.append([obj.name for obj in partial.objects])
        return [
            FrameState(
                t,
                {
                    obj.name: Detection(rect(5, 6, 4, 4, 128, 128), 0.9, obj.obj_class)
                    for obj in partial.objects
                },
                128,
                128,
            )
            for t, path in frames
        ]

    monkeypatch.setattr(sam, "track", image_track)
    if fallback:
        states = sam.track_video(client, protocol(), tmp_path / "original.mp4", paths, "source")
        assert states[0].objects["tube_1"] is not None
        assert seen == [["tube_2", "tube_1"]]
        assert client.calls == ["tube", "hand"]
    else:
        with pytest.raises(httpx.HTTPStatusError):
            sam.track_video(client, protocol(), tmp_path / "original.mp4", paths, "source")
        assert seen == []


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="local ffmpeg tools unavailable",
)
def test_local_real_transcode_produces_cached_cfr_h264_small_silent_clip(tmp_path):
    source = tmp_path / "synthetic-original.mp4"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 8, (1280, 720))
    assert writer.isOpened()
    for i in range(16):
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.circle(image, (100 + i * 20, 300), 30, (255, 100, 0), -1)
        writer.write(image)
    writer.release()
    video = prepare_video(source, tmp_path / "cache", 10 * 1024 * 1024)
    assert video.fps == 4 and video.frame_count == 8
    assert (video.width, video.height) == (640, 360)
    assert video.billed_frame_reservation == 50
    previous = video.path.stat().st_mtime_ns
    assert (
        prepare_video(source, tmp_path / "cache", 10 * 1024 * 1024).path.stat().st_mtime_ns
        == previous
    )
    audio = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "json",
            str(video.path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(audio.stdout)["streams"] == []
    with pytest.raises(NativeVideoTooLarge):
        prepare_video(source, tmp_path / "cache", 1)


@pytest.mark.parametrize("image_has_match", [False, True])
def test_completed_zero_mask_failure_falls_back_once_for_only_that_concept(
    tmp_path, monkeypatch, image_has_match
):
    video = prepared(tmp_path)
    monkeypatch.setattr(sam, "prepare_video", lambda *args: video)
    client = MockClient(
        tmp_path,
        {
            "tube": NativeVideoNoMatches("completed response returned zero masks"),
            "hand": wire({i: [(9, 55, 40)] for i in range(8)}),
        },
    )
    seen = []

    def image_track(client, partial, frames, video_hash, color_fallback):
        seen.append([obj.name for obj in partial.objects])
        return [
            FrameState(
                t,
                {
                    obj.name: Detection(rect(5, 6, 4, 4, 128, 128), 0.9, obj.obj_class)
                    if image_has_match
                    else None
                    for obj in partial.objects
                },
                128,
                128,
                complete=False,
            )
            for t, path in frames
        ]

    monkeypatch.setattr(sam, "track", image_track)
    states = sam.track_video(
        client, protocol(), tmp_path / "original.mp4", evidence(tmp_path), "source"
    )
    assert seen == [["tube_2", "tube_1"]]
    assert client.calls == ["tube", "hand"]
    assert [event for event, _ in client.notices] == ["native_video_failed", "image_fallback"]
    assert all((state.objects["tube_1"] is not None) == image_has_match for state in states)
    assert all(state.objects["hand"] is not None for state in states)
    assert all(not state.complete for state in states)
    if not image_has_match:
        assert all(state.objects["tube_1"] is None for state in states)


@pytest.mark.parametrize("text", ["", "<0f>bad"])
def test_unconfirmed_empty_or_diagnostic_response_does_not_trigger_image_fallback(
    tmp_path, monkeypatch, text
):
    video = prepared(tmp_path)
    monkeypatch.setattr(sam, "prepare_video", lambda *args: video)
    client = MockClient(tmp_path, {"tube": text, "hand": text})

    def forbidden(*args):
        raise AssertionError("Incomplete or diagnostic output must not trigger paid fallback")

    monkeypatch.setattr(sam, "track", forbidden)
    states = sam.track_video(
        client, protocol(), tmp_path / "original.mp4", evidence(tmp_path), "source"
    )
    assert all(all(d is None for d in state.objects.values()) for state in states)
    assert not any(event == "image_fallback" for event, _ in client.notices)


def test_zero_match_image_fallback_preserves_budget_refusal(tmp_path, monkeypatch):
    video = prepared(tmp_path)
    monkeypatch.setattr(sam, "prepare_video", lambda *args: video)
    client = MockClient(tmp_path, {"tube": NativeVideoNoMatches("empty")})
    attempts = []

    def denied(*args):
        attempts.append(True)
        raise BudgetExceeded("image fallback cap")

    monkeypatch.setattr(sam, "track", denied)
    with pytest.raises(BudgetExceeded, match="image fallback cap"):
        sam.track_video(client, protocol(), tmp_path / "original.mp4", evidence(tmp_path), "source")
    assert len(attempts) == 1
    assert client.calls == ["tube"]


@pytest.mark.parametrize(
    "status,text,expect_fallback",
    [("completed", "", True), ("incomplete", "", False), ("completed", "<0f>bad", False)],
)
def test_completed_empty_client_preserves_raw_body_and_requests_fallback_only_when_valid(
    tmp_path, monkeypatch, status, text, expect_fallback
):
    source = tmp_path / "original.mp4"
    source.write_bytes(b"test-source")
    video = prepared(tmp_path, file_hash(source))
    monkeypatch.setattr(meta_client, "prepare_video", lambda *args: video)
    raw = {
        "status": status,
        "output": [
            {
                "type": "message",
                "extra_field": {"diagnosis": "retained"},
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {"video_frames_processed": 50},
    }
    client = MetaClient(
        settings(tmp_path),
        "empty-body",
        httpx.MockTransport(lambda request: httpx.Response(200, json=raw)),
    )
    try:
        if expect_fallback:
            with pytest.raises(NativeVideoNoMatches):
                client.segment_video(source, "tube", file_hash(source))
            saved = list((tmp_path / "runs/empty-body").glob("*.response.json"))
            assert len(saved) == 1 and json.loads(saved[0].read_text()) == raw
            assert saved[0].stat().st_mode & 0o777 == 0o600
            assert not list((tmp_path / "cache/sam-video").glob("*.json"))
        else:
            client.segment_video(source, "tube", file_hash(source))
    finally:
        client.close()


def test_legacy_cached_completed_empty_also_triggers_fallback_without_call(tmp_path, monkeypatch):
    from app.replay_cache import digest

    source = tmp_path / "original.mp4"
    source.write_bytes(b"test-source")
    video = prepared(tmp_path, file_hash(source))
    monkeypatch.setattr(meta_client, "prepare_video", lambda *args: video)
    client = MetaClient(
        settings(tmp_path),
        "old-empty",
        httpx.MockTransport(lambda request: pytest.fail("cached result must not call network")),
    )
    key = digest([file_hash(source), "tube", "sam-3.1-video", meta_client.TRANSCODE_SETTINGS])
    client.cache.put("sam-video", key, "", "live-meta-sam-3.1-video")
    try:
        with pytest.raises(NativeVideoNoMatches):
            client.segment_video(source, "tube", file_hash(source))
    finally:
        client.close()


def test_observed_photographic_response_has_real_masks_and_explicit_frame_ids(tmp_path):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/sam_video_photographed_observed.json").read_text()
    )
    metadata = PreparedVideo(tmp_path / "clip.mp4", "hash", 640, 480, 12, 3, 4)
    parsed = parse_video_masks(meta_client.response_text(fixture["response"]), metadata)
    assert parsed.valid and len(parsed.frames) == 12
    assert sum(len(objects) for objects in parsed.frames.values()) == 50
    assert set(parsed.frames[0]) & set(parsed.frames[11])
    assert fixture["response"]["usage"]["video_frames_processed"] == 50
