"""Generated media and mocked providers; these are not accuracy measurements."""

import json

import cv2
import numpy as np
import pytest
from app import main, object_preview, service
from app.audit.chain import verify_entries
from app.config import Settings
from app.learn.frames import file_hash
from app.object_preview import descriptions
from app.replay_cache import atomic_json
from app.run_summary import summarize
from app.samples import sample_protocol
from app.schemas import Opinion, Protocol
from app.selection import selected_video, selection
from app.track.geometry import Detection, FrameState
from app.track.native_video import probe_video
from fastapi.testclient import TestClient


def video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 4.0, (64, 64))
    assert writer.isOpened()
    for i in range(16):
        writer.write(np.full((64, 64, 3), i * 10, dtype=np.uint8))
    writer.release()
    return path


def test_exact_selection_keeps_source_and_reuses_derived_clip(tmp_path):
    source = video(tmp_path / "original.mp4.avi")
    before = file_hash(source)
    chosen = selection(source, 1.0, 3.0, 300)
    atomic_json(tmp_path / "selection.json", {source.name: chosen})
    selected, offset, meta = selected_video(source)
    assert offset == 1 and meta["end"] == 3
    assert probe_video(selected)["duration_s"] == pytest.approx(2, abs=0.1)
    stamp = selected.stat().st_mtime_ns
    assert selected_video(source)[0].stat().st_mtime_ns == stamp
    assert file_hash(source) == before
    with pytest.raises(ValueError):
        selection(source, 3.0, 8.0, 300)
    with pytest.raises(ValueError):
        selection(source, float("nan"), 3.0, 300)
    with pytest.raises(ValueError):
        selection(source, 0, 3.0, 2)


def test_preview_has_three_real_image_payloads_and_no_step_verdict(tmp_path, monkeypatch):
    job = "preview"
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    source = video(folder / "original.mp4")
    protocol = sample_protocol()
    called = []

    def track(client, proto, paths, sha):
        called.append((len(paths), sha))
        return [
            FrameState(t, {o.name: None for o in proto.objects}, 512, 512, str(p)) for t, p in paths
        ]

    monkeypatch.setattr(object_preview, "track", track)
    settings = Settings(_env_file=None, data_dir=tmp_path)
    object_preview.process_preview(settings, job, protocol)
    result = json.loads((folder / "run.json").read_text())
    assert result["phase"] == "object-preview" and result["status"] == "ready"
    assert len(result["frames"]) == 3 and result["frames"][0]["image"].startswith(
        "data:image/jpeg;base64,"
    )
    assert "events" not in result and "states" not in result
    assert called == [(3, file_hash(source))]
    assert all(o["visible_frames"] == 0 for o in result["objects"])


def test_description_edits_preserve_rules_and_invalidate_validation():
    protocol = sample_protocol()
    protocol.verified = True
    prompts = {o.name: o.sam_prompt for o in protocol.objects}
    assert descriptions(protocol, prompts).verified
    prompts[protocol.objects[0].name] = "distinct red marked tube"
    edited = descriptions(protocol, prompts)
    assert not edited.verified and protocol.verified
    assert (
        edited.steps == protocol.steps
        and edited.objects[0].sam_prompt != protocol.objects[0].sam_prompt
    )
    with pytest.raises(ValueError):
        descriptions(protocol, {"invented": "object"})


def test_preview_then_analysis_reuses_same_job_and_applies_mode_without_new_upload(
    tmp_path, monkeypatch
):
    original = "a" * 32
    folder = tmp_path / "jobs" / original
    folder.mkdir(parents=True)
    protocol = sample_protocol()
    (folder / "protocol.json").write_text(protocol.model_dump_json(by_alias=True))
    calls = []

    def preview(settings, job, proto):
        calls.append(("preview", job))
        atomic_json(
            tmp_path / "jobs" / job / "run.json",
            {
                "id": job,
                "status": "ready",
                "phase": "object-preview",
                "protocol": proto.model_dump(by_alias=True),
            },
        )

    def full(settings, job, proto, color):
        calls.append(("full", job, settings.sam_mode))
        atomic_json(tmp_path / "jobs" / job / "run.json", {"id": job, "status": "ready"})

    monkeypatch.setattr(main, "process_preview", preview)
    monkeypatch.setattr(main, "process_run", full)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auth_required=False,
        replay_mode=False,
        model_api_key="mock",
    )
    with TestClient(main.create_app(settings)) as api:
        response = api.post(
            "/api/runs",
            data={"protocol_id": original, "preview_only": "true"},
            files={"video": ("test.mp4", b"mock", "video/mp4")},
        )
        job = response.json()["run_id"]
        assert response.status_code == 202
        result = api.post(
            f"/api/runs/{job}/analyse",
            data={
                "tracking_mode": "video",
                "prompts": json.dumps({o.name: o.sam_prompt for o in protocol.objects}),
            },
        )
        assert result.status_code == 202
        assert api.post(f"/api/runs/{job}/analyse").status_code == 409
    assert calls == [("preview", job), ("full", job, "video")]
    assert (tmp_path / "jobs" / job / "original.mp4").read_bytes() == b"mock"


def test_invalid_trim_refuses_before_admission_or_paid_work(tmp_path, monkeypatch):
    monkeypatch.setattr("app.selection.probe_video", lambda *a: {"duration_s": 10})
    monkeypatch.setattr(main, "process_learn", lambda *a: pytest.fail("no processing"))
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auth_required=False,
        replay_mode=False,
        model_api_key="mock",
    )
    with TestClient(main.create_app(settings)) as api:
        result = api.post(
            "/api/protocols",
            data={"trim_start_s": 4, "trim_end_s": 11},
            files={"video": ("video.mp4", b"mock")},
        )
        assert result.status_code == 422
        assert not list((tmp_path / "jobs").iterdir())


def test_alternate_tracker_and_trimmed_run_keep_source_timestamps_and_chain(tmp_path, monkeypatch):
    job = "alternative"
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    source = video(folder / "original.mp4")
    atomic_json(folder / "selection.json", {source.name: selection(source, 1, 3, 300)})
    protocol = Protocol.model_validate(
        {
            "name": "Test only",
            "objects": [{"name": "cap", "sam_prompt": "cap", "class": "cap"}],
            "steps": [
                {"id": "s", "title": "Observe cap", "post": [{"op": "present", "obj": "cap"}]}
            ],
        }
    )

    class Tracker:
        provider_id = "test-only-local-geometry"

        def track(self, proto, recording, paths, video_hash, color=False):
            mask = np.ones((64, 64), dtype=np.bool_)
            return [
                FrameState(t, {"cap": Detection(mask, 0.9, "cap"), "hand": None}, 64, 64, str(p))
                for t, p in paths
            ]

    monkeypatch.setattr(
        service.MetaClient,
        "call",
        lambda *a, **kw: pytest.fail("alternate tracker must not call Meta"),
    )
    run = service.run_recording(
        Settings(_env_file=None, data_dir=tmp_path, replay_mode=False, model_api_key="mock"),
        job,
        source,
        protocol,
        tracking_provider=Tracker(),
        spark_opinion=lambda *a: Opinion(completed=True, confidence=0.9, reason="mock"),
    )
    assert run["video_sha256"] == file_hash(source)
    assert min(f["t"] for f in run["frames"]) == 1
    assert run["analysis_range"]["end"] == 3
    assert all(e["t"] >= 1 for e in run["events"])
    assert verify_entries(run["chain"], run["chain_root"])
    assert run["tracking_stats"]["tracking"]["provider"] == "test-only-local-geometry"


def test_summary_counts_only_rule_flags_and_never_models_as_completion():
    run = {
        "protocol": {"steps": [{"id": x, "title": x} for x in "abc"]},
        "states": {"a": "DONE", "b": "DONE", "c": "PENDING"},
        "events": [
            {"kind": "wrong_object", "tier": "rules", "step_id": "b"},
            {"kind": "skipped", "tier": "spark", "step_id": "a"},
            {"kind": "step_completed", "tier": "spark", "step_id": "c"},
        ],
    }
    result = summarize(run)
    assert (result["confirmed"], result["flagged"], result["unconfirmed"]) == (1, 1, 1)
