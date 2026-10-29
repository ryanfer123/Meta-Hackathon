"""Native-video spike contract checks use synthetic parser text and mocked transport only."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from app.config import Settings
from app.meta_client import MetaClient

from scripts import spike


def response(text, status="completed", processed=8):
    return {
        "status": status,
        "output": [{"content": [{"type": "output_text", "text": text}]}],
        "usage": {"video_frames_processed": processed},
    }


def source():
    return {"duration_s": 2, "source_average_fps": 4, "source_frames": 8}


def fixture_text():
    return (Path(__file__).parent / "fixtures" / "sam_synthetic.txt").read_text().strip()


def test_video_detail_reports_explicit_sparse_frame_refs_and_id_recurrence():
    line = fixture_text()
    text = "\n".join([line, line.replace("<0f>", "<2f>"), line.replace("<0f>3", "<7f>8")])
    result = spike.summarize_video_response(response(text), source())
    assert result["evidence_status"] == "parsed"
    assert result["frame_indices_in_output_order"] == [0, 2, 7]
    assert result["frame_reference_fields"] == ["frame_index"]
    assert result["billed_frames_per_source_second"] == 4
    assert result["emitted_frames_per_source_second"] == 1.5
    assert result["mask_object_count"] == 2
    assert result["object_id_recurrence"] == [
        {"object_id": "3", "frame_indices": [0, 2], "appears_in_multiple_frames": True},
        {"object_id": "8", "frame_indices": [7], "appears_in_multiple_frames": False},
    ]
    assert "identity" in result["per_record_fields"]["mask"]
    assert result["frames"][0]["masks"][0]["raster_pixels"] == 16
    assert result["frames"][0]["masks"][0]["confidence"] == pytest.approx(0.93)
    assert "Not established" in result["physical_identity_consistency"]


def test_video_detail_keeps_missing_confidence_and_unreported_processing_rate_unknown():
    raw = response(fixture_text().replace(";c=0.93", ""))
    raw["usage"] = {}
    result = spike.summarize_video_response(raw, source())
    assert result["frames"][0]["masks"][0]["confidence"] is None
    assert result["billed_frames_per_source_second"] is None


@pytest.mark.parametrize("status,text", [("incomplete", None), ("completed", "<0f>broken")])
def test_video_detail_marks_incomplete_or_diagnostic_response_unknown(status, text):
    result = spike.summarize_video_response(response(text or fixture_text(), status), source())
    assert result["evidence_status"] == "unknown"
    if status == "completed":
        assert result["diagnostics"]
        assert "raw" not in result["diagnostics"][0]


def test_video_detail_accepts_empty_success_as_zero_matches_without_guessing_coverage():
    result = spike.summarize_video_response(response(""), source())
    assert result["mask_object_count"] == 0
    assert result["frames"] == []
    assert result["billed_frames_per_source_second"] == 4
    assert "Not established" in result["physical_identity_consistency"]


def test_probe_uses_real_metadata_fields_and_does_not_claim_provider_size_limit(
    tmp_path, monkeypatch
):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"synthetic-test-container")
    payload = {
        "streams": [
            {
                "codec_name": "h264",
                "width": 64,
                "height": 64,
                "avg_frame_rate": "4/1",
                "nb_frames": "8",
                "duration": "2.0",
            }
        ],
        "format": {"duration": "2.0"},
    }
    commands = []

    def probe(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(spike.subprocess, "run", probe)
    result = spike.video_metadata(video)
    assert result["source_average_fps"] == 4
    assert result["source_frames"] == 8
    assert result["source_frame_count_is_estimate"] is False
    assert result["bytes"] == len(b"synthetic-test-container")
    assert commands[0][0] == "ffprobe"
    payload["streams"][0].pop("nb_frames")
    assert spike.video_metadata(video)["source_frame_count_is_estimate"] is True


def test_detail_rejects_oversized_clip_before_transport_or_probe(tmp_path, monkeypatch):
    video = tmp_path / "large.mp4"
    with video.open("wb") as handle:
        handle.truncate(spike.NATIVE_DETAIL_MAX_BYTES + 1)
    monkeypatch.setattr(
        spike.subprocess, "run", lambda *args, **kwargs: pytest.fail("probe not needed")
    )
    with pytest.raises(ValueError, match="10 MiB"):
        spike.video_metadata(video)


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--native-video-detail", "--video", "clip.mp4"],
        ["--native-video-detail", "--allow-paid-calls"],
        ["--allow-paid-calls"],
    ],
)
def test_spike_cli_rejects_missing_paid_consent_or_required_media_before_client(
    monkeypatch, arguments
):
    monkeypatch.setattr(sys, "argv", ["spike.py", *arguments])
    monkeypatch.setattr(spike, "Settings", lambda: pytest.fail("must reject before reading config"))
    with pytest.raises(SystemExit) as exc:
        spike.main()
    assert exc.value.code == 2


def test_detail_cli_makes_exactly_one_mocked_native_request_and_writes_observations(
    tmp_path, monkeypatch
):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"synthetic-test-video-placeholder")
    settings = Settings(
        _env_file=None, data_dir=tmp_path, replay_mode=False, model_api_key="test-key-never-output"
    )
    calls = []
    closed = []

    class Client:
        estimate = staticmethod(MetaClient.estimate)

        def __init__(self, config, job):
            assert config is settings
            self.settings, self.run_id = config, job

        def call(self, *args, **kwargs):
            calls.append((args, kwargs))
            return response(fixture_text())

        def close(self):
            closed.append(True)

    monkeypatch.setattr(spike, "Settings", lambda: settings)
    monkeypatch.setattr(spike, "MetaClient", Client)
    monkeypatch.setattr(
        spike, "video_metadata", lambda path: {**source(), "bytes": video.stat().st_size}
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["spike.py", "--video", str(video), "--native-video-detail", "--allow-paid-calls"],
    )
    spike.main()
    assert len(calls) == 1 and closed == [True]
    args, kwargs = calls[0]
    assert args[:3] == ("responses", "sam", "sam-3.1")
    body = args[3]
    assert body["metadata"] == {"include_confidence": "true", "mask_encoding": "one_bit"}
    assert body["input"][0]["content"][1]["video_url"].startswith("data:video/mp4;base64,")
    assert kwargs["frames"] == 8
    assert kwargs["reserve_usd"] == 0.01
    assert kwargs["sam_frames"] == 50
    assert body["store"] is False
    observations = list((tmp_path / "runs").glob("*/observations.json"))
    assert len(observations) == 1
    raw = observations[0].read_text()
    detail = json.loads(raw)["native_video_detail"]
    assert detail["estimated_cost_usd"] == pytest.approx(0.0016)
    assert detail["request_limits"]["provider_max_request_bytes"] is None
    assert detail["request_limits"]["documented_max_frames"] == 15000
    assert "test-key-never-output" not in raw
    assert "data:video" not in raw


def test_native_detail_does_not_reuse_image_cost_when_video_usage_is_absent(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"synthetic-test-video-placeholder")
    monkeypatch.setattr(spike, "video_metadata", lambda path: source())

    class Client:
        settings = Settings(_env_file=None, data_dir=tmp_path)
        run_id = "empty-test"

        def call(self, *args, **kwargs):
            raw = response("")
            raw["usage"] = {}
            return raw

        def estimate(self, *args):
            pytest.fail("Missing video usage must not be estimated as an image")

    detail = spike.native_video_detail(Client(), video, "tube")
    assert detail["estimated_cost_usd"] is None
    assert detail["billed_frames_per_source_second"] is None


def test_detail_preserves_full_empty_response_body_and_item_schema(tmp_path, monkeypatch):
    raw = {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "custom": {"key": "kept"},
                "content": [{"type": "output_text", "text": "", "annotations": []}],
            }
        ],
        "usage": {"video_frames_processed": 50},
        "error": None,
    }

    class Client:
        settings = Settings(_env_file=None, data_dir=tmp_path)
        run_id = "empty-diagnostic"
        estimate = staticmethod(MetaClient.estimate)

        def call(self, *args, **kwargs):
            return raw

    monkeypatch.setattr(spike, "video_metadata", lambda video: source())
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"test")
    result = spike.native_video_detail(Client(), video, "tube")
    saved = tmp_path / "runs/empty-diagnostic" / result["raw_response_file"]
    assert json.loads(saved.read_text()) == raw
    assert saved.stat().st_mode & 0o777 == 0o600
    assert result["output_items"][0]["type"] == "message"
    assert "custom" in result["output_items"][0]["keys"]
    assert result["mask_record_count"] == 0
