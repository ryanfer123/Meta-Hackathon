"""Long teaching/validation coverage with generated video and mocked providers only."""

import json
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
from app import processing_plan, service
from app.budget import Budget, BudgetExceeded
from app.config import Settings
from app.learn.frames import teaching_keyframes
from app.learn.validate import StepRange
from app.meta_client import MetaClient
from app.schemas import Protocol
from app.track.geometry import FrameState


def settings(tmp_path, **kwargs):
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        replay_mode=False,
        model_api_key="mock-only",
        sam_mode="video",
        **kwargs,
    )


def protocol():
    return Protocol.model_validate(
        {
            "name": "Synthetic seven-object procedure",
            "objects": [
                {"name": f"part_{i}", "sam_prompt": f"colored part {i}", "class": "part"}
                for i in range(6)
            ],
            "steps": [
                {
                    "id": "s",
                    "title": "Observe a change",
                    "post": [{"op": "present", "obj": "part_0"}],
                }
            ],
        }
    )


def plan_inputs(tmp_path, monkeypatch):
    path = tmp_path / "frame.jpg"
    cv2.imwrite(str(path), np.zeros((288, 512, 3), dtype=np.uint8))
    frames = [(i / 2, path) for i in range(600)]
    monkeypatch.setattr(processing_plan, "probe_video", lambda *_: {"duration_s": 300})
    return frames


def test_two_five_minute_expert_takes_fit_combined_default_budget(tmp_path, monkeypatch):
    frames = plan_inputs(tmp_path, monkeypatch)
    cfg = settings(tmp_path)
    plan = processing_plan.plan_validation(cfg, protocol(), Path("a"), frames, Path("b"), frames)
    assert plan["sampled_frames"] == 1200
    assert plan["processed_frames_estimate"] == 16800
    assert plan["base_tracking_reservation_usd"] == pytest.approx(3.36)
    assert plan["packed_mask_mb_upper_bound"] < cfg.max_validation_mask_mb
    budget = Budget(cfg)
    for _ in range(14):
        budget.reserve("pair", "sam", 0.24, processed_frames=1200)


@pytest.mark.parametrize("limit", ["memory", "frames", "cost", "image"])
def test_combined_plan_rejects_before_either_tracking_call(tmp_path, monkeypatch, limit):
    frames = plan_inputs(tmp_path, monkeypatch)
    changes = {
        "memory": {"max_validation_mask_mb": 128},
        "frames": {"max_sam_video_frames": 16000},
        "cost": {"max_run_cost_usd": 3},
        "image": {"sam_mode": "image"},
    }[limit]
    cfg = settings(tmp_path).model_copy(update=changes)
    with pytest.raises((ValueError, BudgetExceeded)):
        processing_plan.plan_validation(cfg, protocol(), Path("a"), frames, Path("b"), frames)
    assert not (tmp_path / "budget.sqlite").exists()


def test_long_teaching_compiles_50_time_stratified_images_and_saves_resolution(
    tmp_path, monkeypatch
):
    folder = tmp_path / "jobs" / "teach"
    folder.mkdir(parents=True)
    writer = cv2.VideoWriter(
        str(folder / "original.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 2, (96, 64)
    )
    if not writer.isOpened():
        pytest.skip("local MP4 writer unavailable")
    for i in range(600):
        writer.write(np.full((64, 96, 3), i % 255, dtype=np.uint8))
    writer.release()
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": protocol().model_dump_json(by_alias=True),
                            }
                        ]
                    }
                ],
            },
        )

    monkeypatch.setattr(
        service, "MetaClient", lambda cfg, job: MetaClient(cfg, job, httpx.MockTransport(respond))
    )
    service.process_learn(settings(tmp_path), "teach", [], "Describe the entire procedure.")
    result = json.loads((folder / "status.json").read_text())
    assert result["status"] == "ready", result
    assert result["protocol"]["frame_max_side"] == 96
    assert result["protocol"]["verified"] is False
    content = seen[0]["input"][0]["content"]
    assert sum(item["type"] == "input_image" for item in content) == 50
    assert "299.500" in content[0]["text"]
    assert json.loads((folder / "narration.json").read_text())[0]["end"] == 300
    call = json.loads((tmp_path / "runs/teach/calls.jsonl").read_text())
    assert call["reserved_usd"] == 1.25


def test_long_validation_routes_both_complete_timelines_without_false_verification(
    tmp_path, monkeypatch
):
    folder = tmp_path / "jobs" / "validate"
    folder.mkdir(parents=True)
    (folder / "original.mp4").write_bytes(b"expert-a")
    (folder / "heldout.mp4").write_bytes(b"expert-b")
    (folder / "protocol.json").write_text(protocol().model_dump_json(by_alias=True))
    paths = plan_inputs(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "probe_video", lambda *_: {"duration_s": 300})
    sampled = []

    def sample(*args):
        sampled.append(args[3:])
        return paths

    monkeypatch.setattr(service, "sample", sample)
    routed = []

    def track(client, proto, video, frames, video_hash):
        routed.append(len(frames))
        return [FrameState(t, {}, 640, 360, str(path)) for t, path in frames]

    monkeypatch.setattr(service, "track_video", track)
    monkeypatch.setattr(
        service.MetaClient, "structured", lambda *_: pytest.fail("No repair calls requested")
    )
    service.process_validation(
        settings(tmp_path), "validate", {"s": StepRange(start=0, end=300)}, False
    )
    result = json.loads((folder / "status.json").read_text())
    assert result["status"] == "ready", result
    assert routed == [600, 600]
    assert sampled == [(600, 1024, False), (600, 1024, False)]
    assert result["validation"]["processing_plan"]["processed_frames_estimate"] == 16800
    assert not result["protocol"]["verified"]


def test_image_cache_does_not_reuse_pixels_after_resize(tmp_path):
    calls = []

    def respond(request):
        calls.append(True)
        return httpx.Response(200, json={"status": "completed", "output": []})

    path = tmp_path / "f.jpg"
    cv2.imwrite(str(path), np.zeros((64, 64, 3), dtype=np.uint8))
    client = MetaClient(settings(tmp_path), "image-resize", httpx.MockTransport(respond))
    try:
        client.segment(path, "part", "same-video", 0)
        client.segment(path, "part", "same-video", 0)
        cv2.imwrite(str(path), np.zeros((128, 128, 3), dtype=np.uint8))
        client.segment(path, "part", "same-video", 0)
    finally:
        client.close()
    assert len(calls) == 2


def test_static_long_teaching_still_covers_middle_and_end(tmp_path):
    frames = []
    for i in range(600):
        path = tmp_path / f"{i}.jpg"
        cv2.imwrite(str(path), np.zeros((8, 8, 3), dtype=np.uint8))
        frames.append((i / 2, path))
    selected = teaching_keyframes(frames)
    positions = [int(p.stem) for p in selected]
    assert len(positions) == 50
    assert positions[0] == 0 and positions[-1] == 599
    assert max(b - a for a, b in zip(positions, positions[1:])) <= 24


def test_protocol_coordinate_resolution_can_normalize_a_lower_resolution_recording(tmp_path):
    from app.learn.frames import sample

    video = tmp_path / "low-res.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 2, (96, 64))
    if not writer.isOpened():
        pytest.skip("local MP4 writer unavailable")
    for _ in range(4):
        writer.write(np.zeros((64, 96, 3), dtype=np.uint8))
    writer.release()
    frames = sample(video, tmp_path / "frames", 2, 180, 192, True)
    assert cv2.imread(str(frames[0][1])).shape[:2] == (128, 192)
