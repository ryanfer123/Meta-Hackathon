"""Generated recordings and mocked model responses only; not real evaluation evidence."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
from app import service
from app.config import Settings
from app.learn.frames import file_hash
from app.meta_client import MetaClient
from app.schemas import Protocol

from eval.run_eval import evaluate, freeze
from scripts.make_manifest import make_manifest
from scripts.run_batch import run_batch, videos_in


def setup_batch(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        replay_mode=False,
        model_api_key="mock-only",
        sam_mode="image",
    )
    protocol = Protocol.model_validate(
        {
            "name": "Synthetic test only",
            "objects": [{"name": "cap", "sam_prompt": "blue cap", "class": "cap"}],
            "steps": [
                {"id": "present", "title": "Observe cap", "post": [{"op": "present", "obj": "cap"}]}
            ],
        }
    )
    path = tmp_path / "protocol.json"
    path.write_text(protocol.model_dump_json(by_alias=True))
    sent = []
    wire = (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text()

    def handler(request):
        body = json.loads(request.content)
        sent.append(body["model"])
        text = (
            wire
            if body["model"] == "sam-3.1"
            else '{"completed":true,"confidence":0.9,"reason":"mock test"}'
        )
        return httpx.Response(
            200,
            json={
                "output": [{"content": [{"type": "output_text", "text": text}]}],
                "usage": {"input_tokens": 10, "output_tokens": 20},
            },
        )

    monkeypatch.setattr(
        service,
        "MetaClient",
        lambda settings, job: MetaClient(settings, job, httpx.MockTransport(handler)),
    )
    return settings, path, sent


def write_video(folder, stem, value):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stem}.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 2.0, (64, 64))
    assert writer.isOpened()
    try:
        for index in range(4):
            image = np.full((64, 64, 3), value + index, dtype=np.uint8)
            writer.write(image)
    finally:
        writer.release()
    return path


def test_batch_requires_opt_in_before_clients_or_outputs(tmp_path):
    with pytest.raises(ValueError, match="allow-paid-calls"):
        run_batch(Settings(_env_file=None), tmp_path / "absent", tmp_path, tmp_path / "out", "test")
    assert not (tmp_path / "out").exists()
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_batch.py",
            "--protocol",
            "missing",
            "--videos",
            "missing",
            "--out",
            str(tmp_path / "out"),
            "--split",
            "test",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--allow-paid-calls" in result.stderr


def test_batch_reuses_api_pipeline_and_skips_matching_predictions(tmp_path, monkeypatch):
    settings, protocol, sent = setup_batch(tmp_path, monkeypatch)
    source = write_video(tmp_path / "videos", "take", 30)
    out = tmp_path / "predictions"
    rows = run_batch(
        settings, protocol, source.parent, out, "dev", allow_paid_calls=True, max_cost_usd=1
    )
    assert [row.status for row in rows] == ["ready"]
    prediction = json.loads((out / "take.prediction.json").read_text())
    assert prediction["provenance"] == "live-recording"
    assert prediction["video_sha256"] == file_hash(source)
    assert prediction["batch_split"] == "dev"
    assert isinstance(prediction["shadow"], list)
    assert rows[0].cloud_frames == sum(c["cloud_frames"] for c in prediction["metrics"]["calls"])
    for name in ("report.html", "chain.json", "root.txt"):
        assert (out / "take" / name).is_file()
    count = len(sent)
    rows = run_batch(
        settings, protocol, source.parent, out, "dev", allow_paid_calls=True, max_cost_usd=1
    )
    assert rows[0].status == "skipped"
    assert len(sent) == count
    # A changed source is a new attempt, not an accepted old prediction.
    write_video(source.parent, "take", 50)
    rows = run_batch(
        settings, protocol, source.parent, out, "dev", allow_paid_calls=True, max_cost_usd=1
    )
    assert rows[0].status == "ready"
    assert len(sent) > count


def test_batch_cost_limit_rejects_next_http_and_retains_failed_reservations(tmp_path, monkeypatch):
    settings, protocol, sent = setup_batch(tmp_path, monkeypatch)
    source = write_video(tmp_path / "videos", "take", 20)
    out = tmp_path / "out"
    rows = run_batch(
        settings, protocol, source.parent, out, "test", allow_paid_calls=True, max_cost_usd=0.006
    )
    assert rows[0].status == "budget-stopped"
    assert len(sent) == 2
    with sqlite3.connect(settings.data_dir / "budget.sqlite") as db:
        assert db.execute("SELECT SUM(reserved) FROM calls").fetchone()[0] == pytest.approx(0.005)
    assert not (out / "take.prediction.json").exists()
    # The denied request is not sent, including on a later retry of this batch.
    rows = run_batch(
        settings, protocol, source.parent, out, "test", allow_paid_calls=True, max_cost_usd=0.006
    )
    assert rows[0].status == "budget-stopped"
    assert len(sent) == 2


def test_batch_total_cap_stops_before_next_video(tmp_path, monkeypatch):
    settings, protocol, sent = setup_batch(tmp_path, monkeypatch)
    folder = tmp_path / "videos"
    write_video(folder, "a", 10)
    write_video(folder, "b", 20)
    out = tmp_path / "out"
    first = run_batch(
        settings, protocol, folder, out, "test", allow_paid_calls=True, max_cost_usd=0.27
    )
    assert first[0].status == "ready"
    assert first[1].status == "budget-stopped"
    assert not (out / "b.prediction.json").exists()
    with sqlite3.connect(settings.data_dir / "budget.sqlite") as db:
        assert db.execute("SELECT SUM(reserved) FROM calls").fetchone()[0] <= 0.27 + 1e-9


@pytest.mark.parametrize(
    "update", [{"cloud_jobs": True}, {"glimmer_base_url": "https://inference.baseten.co/v1"}]
)
def test_batch_refuses_uncapped_hosted_or_unknown_remote_costs(tmp_path, update):
    settings = Settings(_env_file=None, **update)
    with pytest.raises(ValueError, match="local ledger|remote open-model"):
        run_batch(
            settings,
            tmp_path / "missing",
            tmp_path,
            tmp_path / "out",
            "dev",
            allow_paid_calls=True,
            max_cost_usd=1,
        )
    assert not (tmp_path / "out").exists()


def test_manifest_preserves_labels_and_batch_predictions_pass_eval_contract(tmp_path, monkeypatch):
    settings, protocol, _ = setup_batch(tmp_path, monkeypatch)
    manifest = tmp_path / "labels.json"
    for split, base in [("dev", 10), ("test", 60)]:
        videos = tmp_path / split
        for index in range(6):
            write_video(videos, f"{split}_{index}", base + index * 3)
        # source=real is deliberately confined to this temporary generated test fixture.
        # This tests the evaluator's input contract, never physical accuracy.
        make_manifest(videos, tmp_path / f"{split}-predictions", manifest, split)
    data = json.loads(manifest.read_text())
    assert len(data["runs"]) == 12
    assert all(run["events"] == [] for run in data["runs"])
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps(freeze(manifest, data)))
    for split in ("dev", "test"):
        rows = run_batch(
            settings,
            protocol,
            tmp_path / split,
            tmp_path / f"{split}-predictions",
            split,
            allow_paid_calls=True,
        )
        assert all(row.status == "ready" for row in rows)
    result = tmp_path / "results.md"
    evaluate(manifest, frozen, result)
    assert "Test runs: 6" in result.read_text()
    original = manifest.read_bytes()
    with pytest.raises(ValueError, match="already listed"):
        make_manifest(tmp_path / "dev", tmp_path / "dev-predictions", manifest, "test")
    assert manifest.read_bytes() == original


def test_manifest_cli_help_and_ambiguous_output_stems(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/make_manifest.py", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    (tmp_path / "take.mp4").touch()
    (tmp_path / "take.mov").touch()
    with pytest.raises(ValueError, match="unique"):
        videos_in(tmp_path)


def test_batch_stops_when_verifier_turns_budget_denial_into_uncertainty(tmp_path, monkeypatch):
    settings, protocol, sent = setup_batch(tmp_path, monkeypatch)
    source = write_video(tmp_path / "videos", "take", 20)
    out = tmp_path / "out"
    rows = run_batch(
        settings, protocol, source.parent, out, "test", allow_paid_calls=True, max_cost_usd=0.03
    )
    assert rows[0].status == "budget-stopped"
    assert sent == ["sam-3.1"] * 8
    assert not (out / "take.prediction.json").exists()


def test_batch_does_not_refund_failed_http_attempts(tmp_path, monkeypatch):
    settings, protocol, _ = setup_batch(tmp_path, monkeypatch)
    source = write_video(tmp_path / "videos", "take", 20)
    out = tmp_path / "out"
    sent = []

    def unavailable(request):
        sent.append(request.url.path)
        return httpx.Response(500, json={"private_provider_body": "must not reach stdout"})

    monkeypatch.setattr(
        service,
        "MetaClient",
        lambda settings, job: MetaClient(settings, job, httpx.MockTransport(unavailable)),
    )
    rows = run_batch(
        settings, protocol, source.parent, out, "test", allow_paid_calls=True, max_cost_usd=0.004
    )
    assert rows[0].status == "error"
    rows = run_batch(
        settings, protocol, source.parent, out, "test", allow_paid_calls=True, max_cost_usd=0.004
    )
    assert rows[0].status == "budget-stopped"
    assert len(sent) == 1
    assert not (out / "take.prediction.json").exists()
