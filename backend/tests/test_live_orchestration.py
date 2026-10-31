"""Real local geometry/encoding with mocked model edges; never production accuracy evidence."""

import json
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest
from app.audit.chain import verify_entries
from app.config import Settings
from app.samples import sample_frames, sample_protocol
from app.schemas import Opinion
from app.service import process_run
from app.track.sam import decode


def test_official_parser_places_box_local_mask_in_source_frame():
    wire = (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text()
    ds = decode(wire, 64, 64)
    assert len(ds) == 1
    assert ds[0].score == pytest.approx(0.93)
    assert ds[0].mask.shape == (64, 64)
    assert int(ds[0].mask.sum()) == 12
    assert ds[0].mask[6, 6] and not ds[0].mask[0, 0]


@pytest.mark.parametrize("sam_mode", ["image", "video"])
def test_recorded_run_orchestration_shadows_every_completion(tmp_path, monkeypatch, sam_mode):
    from app import service

    job = "test-run"
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "original.mp4").write_bytes(b"synthetic-video-placeholder-not-a-real-recording")
    source = sample_frames("clean")
    paths = []
    frames = []
    for i, f in enumerate(source):
        path = folder / f"frame_{i:04d}.jpg"
        image = np.zeros((360, 640, 3), dtype=np.uint8)
        for d in f.objects.values():
            if d is not None and d.mask is not None:
                image[d.mask] = (170, 110, 80)
        cv2.imwrite(str(path), image)
        paths.append((f.t, path))
        frames.append(replace(f, evidence_frame=str(path)))
    seen = []

    def glimmer(self, prompt, images):
        seen.append(images)
        assert "target_step" in prompt and "measurements" in prompt
        assert "frame_timestamps_s" in prompt and "Do not infer" in prompt
        assert all(p.name.startswith("review_") for p in images)
        assert all(cv2.imread(str(p)).shape[1] < 640 for p in images)
        return Opinion(completed=True, confidence=0.9, reason="mocked observation")

    monkeypatch.setattr(service, "sample", lambda *_: paths)
    routed = []

    def tracked(mode):
        routed.append(mode)
        return frames

    monkeypatch.setattr(service, "track", lambda *_: tracked("image"))
    monkeypatch.setattr(service, "track_video", lambda *_: tracked("video"))
    monkeypatch.setattr(service.GlimmerClient, "opinion", glimmer)

    def no_spark(*_):
        raise AssertionError("confident agreeing Glimmer should not escalate")

    monkeypatch.setattr(service.MetaClient, "structured", no_spark)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        replay_mode=False,
        model_api_key="mock-only",
        sam_mode=sam_mode,
        glimmer_base_url="http://mock-glimmer.invalid",
    )
    process_run(settings, job, sample_protocol(), False)
    run = json.loads((folder / "run.json").read_text())
    assert run["status"] == "ready", run
    assert routed == [sam_mode]
    assert len(seen) == 4
    assert len(run["shadow"]) == 4
    assert run["metrics"]["shadow_agreement"] == 1
    evidence = {str(p): (folder / ("evidence_" + p.name)).read_bytes() for _, p in paths}
    assert verify_entries(run["chain"], run["chain_root"], evidence)
    assert "mocked" in (folder / "run.json").read_text()
