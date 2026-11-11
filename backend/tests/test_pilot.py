import hashlib
import json

import pytest
from app.samples import sample_protocol

from eval.run_eval import evaluate, freeze
from scripts.label_recordings import export_page, import_labels


def fixture(tmp_path):
    data = {"reference_video_sha256": ["a" * 64, "b" * 64], "runs": []}
    for i in range(6):
        video = tmp_path / f"{i}.mp4"
        video.write_bytes(f"test-only synthetic stand-in {i}".encode())
        events = [{"kind": "skipped", "step_id": "cap", "t": 4.0}] if i == 4 else []
        prediction = {
            "provenance": "live-recording",
            "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
            "events": events,
            "metrics": {"calls": []},
            "shadow": [],
        }
        (tmp_path / f"{i}.json").write_text(json.dumps(prediction))
        data["runs"].append(
            {
                "id": str(i),
                "split": "dev" if i < 2 else "test",
                "source": "real",
                "video": video.name,
                "prediction": f"{i}.json",
                "events": events,
                "labels_confirmed": True,
            }
        )
    manifest = tmp_path / "labels.json"
    manifest.write_text(json.dumps(data))
    frozen = tmp_path / "frozen.json"
    protocol = tmp_path / "protocol.json"
    protocol.write_text(sample_protocol().model_dump_json(by_alias=True))
    frozen.write_text(json.dumps(freeze(manifest, data, protocol)))
    return data, manifest, frozen


def test_small_pilot_is_explicit_does_not_weaken_full_evaluation(tmp_path):
    _, manifest, frozen = fixture(tmp_path)
    out = tmp_path / "results.md"
    with pytest.raises(ValueError, match="at least 6"):
        evaluate(manifest, frozen, out)
    assert not out.exists()
    evaluate(manifest, frozen, out, pilot=True, protocol=tmp_path / "protocol.json")
    assert "Small real-video pilot" in out.read_text()
    assert "Test runs: 4" in out.read_text()
    assert "| skipped | 1 | 0 | 0 |" in out.read_text()
    assert "do not establish production accuracy" in out.read_text()


@pytest.mark.parametrize("bad", ["labels", "split", "references", "leakage"])
def test_pilot_refuses_unconfirmed_or_leaking_data(tmp_path, bad):
    data, manifest, frozen = fixture(tmp_path)
    if bad == "labels":
        data["runs"][0]["labels_confirmed"] = False
    if bad == "split":
        data["runs"][0]["split"] = "test"
    if bad == "references":
        data["reference_video_sha256"] = []
    if bad == "leakage":
        data["reference_video_sha256"][0] = hashlib.sha256(
            (tmp_path / "0.mp4").read_bytes()
        ).hexdigest()
    manifest.write_text(json.dumps(data))
    frozen.write_text(json.dumps(freeze(manifest, data, tmp_path / "protocol.json")))
    with pytest.raises(ValueError):
        evaluate(
            manifest, frozen, tmp_path / "out.md", pilot=True, protocol=tmp_path / "protocol.json"
        )


def test_offline_label_page_never_loads_predictions_and_import_preserves_splits(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("scripts.label_recordings.probe_video", lambda *a: {"duration_s": 10})
    data, manifest, _ = fixture(tmp_path)
    protocol = tmp_path / "protocol.json"
    protocol.write_text(sample_protocol().model_dump_json(by_alias=True))
    page = tmp_path / "labels.html"
    # The prediction files can be removed entirely. Blind labelling never reads them.
    for i in range(6):
        (tmp_path / f"{i}.json").unlink()
    export_page(manifest, protocol, page)
    assert "connect-src 'none'" in page.read_text()
    assert "crypto.subtle.digest" in page.read_text()
    labels = json.loads(manifest.read_text())
    for run in labels["runs"]:
        run["video_sha256"] = hashlib.sha256((tmp_path / run["video"]).read_bytes()).hexdigest()
    labels["protocol_sha256"] = hashlib.sha256(protocol.read_bytes()).hexdigest()
    confirmed = tmp_path / "confirmed.json"
    confirmed.write_text(json.dumps(labels))
    import_labels(manifest, confirmed, protocol)
    assert [r["split"] for r in json.loads(manifest.read_text())["runs"]] == [
        r["split"] for r in data["runs"]
    ]
    labels["runs"][0]["split"] = "test"
    confirmed.write_text(json.dumps(labels))
    with pytest.raises(ValueError, match="split changed"):
        import_labels(manifest, confirmed, protocol)
