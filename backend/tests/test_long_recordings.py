"""Bounded long recordings use all sampled frames; no network calls."""

from pathlib import Path

import cv2
import numpy as np
import pytest
from app.budget import BudgetExceeded
from app.config import Settings
from app.processing_plan import plan_long_recording
from app.samples import sample_protocol
from app.schemas import Protocol
from app.track.native_video import PreparedVideo, parse_video_masks


def setup(tmp_path, monkeypatch, duration=300, width=320, height=180, **kwargs):
    from app import processing_plan

    settings = Settings(_env_file=None, data_dir=tmp_path, sam_mode="video", **kwargs)
    path = tmp_path / "frame.jpg"
    cv2.imwrite(str(path), np.zeros((height, width, 3), dtype=np.uint8))
    frames = [(i / 2, path) for i in range(int(duration * 2))]
    monkeypatch.setattr(processing_plan, "probe_video", lambda *_: {"duration_s": duration})
    return settings, frames


def test_five_minute_plan_uses_every_frame_and_fits_default_frame_budget(tmp_path, monkeypatch):
    settings, frames = setup(tmp_path, monkeypatch)
    protocol = Protocol.model_validate(
        {
            "name": "Five-concept capacity test",
            "objects": [
                {"name": f"part_{i}", "sam_prompt": f"part {i}", "class": "part"} for i in range(4)
            ],
            "steps": [
                {"id": "s", "title": "Observe part", "post": [{"op": "present", "obj": "part_0"}]}
            ],
        }
    )
    plan = plan_long_recording(settings, protocol, tmp_path / "video.mp4", frames)
    assert plan["sampled_frames"] == 600
    assert plan["processed_frames_estimate"] == 4 * 300 * len(
        {o.sam_prompt for o in protocol.objects}
    )
    assert plan["base_tracking_reservation_usd"] <= settings.max_run_cost_usd
    assert plan["packed_mask_mb_upper_bound"] <= 128


@pytest.mark.parametrize("hosted", [False, True])
def test_long_plan_checks_local_and_hosted_budgets_without_reserving(tmp_path, monkeypatch, hosted):
    settings, frames = setup(
        tmp_path,
        monkeypatch,
        cloud_jobs=hosted,
        max_sam_video_frames=100,
        hosted_max_sam_video_frames=100,
    )
    with pytest.raises(BudgetExceeded, match="No model request"):
        plan_long_recording(settings, sample_protocol(), tmp_path / "video.mp4", frames)
    assert not (tmp_path / "budget.sqlite").exists()


def test_long_plan_refuses_excessive_mask_memory(tmp_path, monkeypatch):
    settings, frames = setup(tmp_path, monkeypatch, width=1024, height=768, max_run_mask_mb=16)
    with pytest.raises(ValueError, match="tracking memory"):
        plan_long_recording(settings, sample_protocol(), tmp_path / "video.mp4", frames)


def test_long_plan_does_not_expand_image_or_configured_duration_limits(tmp_path, monkeypatch):
    settings, frames = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="faster video tracking"):
        plan_long_recording(
            settings.model_copy(update={"sam_mode": "image"}), sample_protocol(), Path("v"), frames
        )
    with pytest.raises(ValueError, match="up to 120 seconds"):
        plan_long_recording(
            settings.model_copy(update={"max_run_duration_s": 120}),
            sample_protocol(),
            Path("v"),
            frames,
        )


def test_native_parser_refuses_geometry_above_memory_ceiling(tmp_path):
    text = (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text()
    video = PreparedVideo(tmp_path / "video.mp4", "hash", 64, 64, 1, 0.25, 4)
    result = parse_video_masks(text, video, max_packed_bytes=1)
    assert not result.valid and not result.frames and "memory limit" in result.reason


def test_report_uses_only_event_evidence_and_generates_only_needed_overlays(tmp_path):
    from app.service import evidence_overlays
    from app.track.geometry import FrameState

    frames, paths = [], []
    for i in range(3):
        path = tmp_path / f"frame-{i}.jpg"
        cv2.imwrite(str(path), np.zeros((16, 16, 3), dtype=np.uint8))
        paths.append((float(i), path))
        frames.append(FrameState(float(i), {}, 16, 16, str(path)))
    refs = {str(paths[0][1])}
    evidence = evidence_overlays(
        frames, paths, tmp_path, overlay_refs=refs | {str(paths[1][1])}, evidence_refs=refs
    )
    assert set(evidence) == refs
    assert (tmp_path / "evidence_frame-0.jpg").exists()
    assert (tmp_path / "evidence_frame-1.jpg").exists()
    assert not (tmp_path / "evidence_frame-2.jpg").exists()


def test_full_five_minute_pipeline_with_mocked_models_keeps_timeline_and_chain(
    tmp_path, monkeypatch
):
    import json
    import shutil

    import httpx
    from app import service
    from app.audit.chain import verify_entries
    from app.learn.frames import sample
    from app.meta_client import MetaClient

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg required for local video conversion")
    folder = tmp_path / "jobs" / "long-test"
    folder.mkdir(parents=True)
    video = folder / "original.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 2, (96, 64))
    if not writer.isOpened():
        pytest.skip("local MP4 writer unavailable")
    for _ in range(600):
        writer.write(np.zeros((64, 96, 3), dtype=np.uint8))
    writer.release()
    with pytest.raises(ValueError, match="at most 90s"):
        sample(video, tmp_path / "teaching-frames")
    wire = (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text().strip()
    records = "\n".join(wire.replace("<0f>", f"<{i}f>", 1) for i in range(1200))
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body["model"])
        text = (
            records
            if body["model"] == "sam-3.1"
            else json.dumps(
                {"completed": False, "confidence": 0.5, "reason": "Synthetic mocked opinion"}
            )
        )
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"content": [{"type": "output_text", "text": text}]}],
                "usage": {"video_frames_processed": 1200} if body["model"] == "sam-3.1" else {},
            },
        )

    monkeypatch.setattr(
        service,
        "MetaClient",
        lambda config, job: MetaClient(config, job, httpx.MockTransport(respond)),
    )
    protocol = Protocol.model_validate(
        {
            "name": "Synthetic long pipeline test",
            "objects": [{"name": "part", "sam_prompt": "part", "class": "part"}],
            "steps": [
                {"id": "s", "title": "Observe change", "post": [{"op": "present", "obj": "part"}]}
            ],
        }
    )
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        replay_mode=False,
        model_api_key="mock-only",
        sam_mode="video",
    )
    run = service.run_recording(settings, "long-test", video, protocol)
    assert len(run["frames"]) == 600
    assert run["frames"][-1]["t"] == 299.5
    assert run["processing_plan"]["duration_s"] == 300
    assert calls.count("sam-3.1") == 2
    assert run["states"]["s"] != "DONE"  # A vacuous condition must never become success.
    refs = {event["evidence_frame"] for event in run["events"] if event["evidence_frame"]}
    evidence = {ref: (folder / ("evidence_" + Path(ref).name)).read_bytes() for ref in refs}
    assert verify_entries(run["chain"], run["chain_root"], evidence)
    assert (folder / "run.json").stat().st_size < 20 * 1024 * 1024


def test_long_display_contours_are_bounded_without_changing_predicate_masks():
    import json

    from app.samples import wire_frame
    from app.track.geometry import Detection, FrameState

    mask = np.zeros((180, 320), dtype=np.bool_)
    mask[10:170, 10:310] = True
    mask[10:30, 10:310:2] = False
    detection = Detection(mask, 0.93)
    before = detection.packed_mask
    frame = FrameState(299.5, {f"obj_{i}": detection for i in range(21)}, 320, 180)
    rendered = wire_frame(frame, max_contour_points=64)
    assert all(sum(len(c) for c in obj["contours"]) <= 64 for obj in rendered["objects"].values())
    assert detection.packed_mask == before
    assert np.array_equal(detection.mask, mask)
    assert len(json.dumps({"frames": [rendered] * 600}).encode()) < 20 * 1024 * 1024


def test_sampler_keeps_last_half_second_of_fractional_duration(tmp_path):
    from app.learn.frames import sample

    video = tmp_path / "fractional.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 3, (32, 32))
    if not writer.isOpened():
        pytest.skip("local MP4 writer unavailable")
    for _ in range(10):
        writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
    writer.release()
    frames = sample(video, tmp_path / "frames")
    assert [t for t, _ in frames] == [0, 0.5, 1, 1.5, 2, 2.5, 3]


@pytest.mark.parametrize("processed", [0, 1200])
def test_video_timeout_is_scoped_to_native_requests_and_does_not_retry(tmp_path, processed):
    import httpx
    from app.meta_client import MetaClient

    seen = []

    def respond(request):
        seen.append(request.extensions["timeout"]["read"])
        assert all(
            request.extensions["timeout"][field] == 120 for field in ("connect", "write", "pool")
        )
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [],
                "usage": {"video_frames_processed": processed} if processed else {},
            },
        )

    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        replay_mode=False,
        model_api_key="mock-only",
        sam_video_timeout_s=240,
    )
    client = MetaClient(settings, "timeout-scope", httpx.MockTransport(respond))
    try:
        client.call("responses", "sam", "sam-3.1", {}, sam_frames=processed)
    finally:
        client.close()
    assert seen == [240 if processed else 120]
