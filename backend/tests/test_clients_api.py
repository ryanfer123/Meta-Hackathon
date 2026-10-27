import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from app.audit.chain import build_chain, verify_entries
from app.audit.report import render_report
from app.budget import Budget, BudgetExceeded
from app.config import Settings
from app.main import create_app
from app.meta_client import MetaClient
from app.replay_cache import ReplayCache
from app.samples import sample_run
from app.schemas import Event, Opinion
from app.supervise.verifier import Verifier
from app.track.sam import decode
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError


def cfg(tmp_path, **kw):
    return Settings(_env_file=None, data_dir=tmp_path, **kw)


def test_config_safe_defaults(tmp_path):
    s = cfg(tmp_path)
    assert s.replay_mode
    with pytest.raises(RuntimeError):
        s.require_live()
    assert "secret" not in str(Settings(model_api_key="secret"))


def test_budget_atomic_under_concurrency(tmp_path):
    b = Budget(cfg(tmp_path, max_sam_calls=3))

    def reserve(_):
        try:
            b.reserve("same", "sam", 0.0025)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(12))) == 3


def test_budget_daily_and_cost_caps(tmp_path):
    b = Budget(cfg(tmp_path, max_daily_spark_calls=1, max_run_cost_usd=0.5))
    b.reserve("a", "spark", 0.25)
    with pytest.raises(BudgetExceeded):
        b.reserve("b", "spark", 0.25)
    with pytest.raises(BudgetExceeded):
        b.reserve("a", "voice", 0.3)


def test_strict_json_retry_and_no_key_in_logs(tmp_path):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        text = (
            "{}" if len(bodies) == 1 else '{"completed":true,"confidence":0.8,"reason":"observed"}'
        )
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": text}]}]}
        )

    s = cfg(tmp_path, replay_mode=False, model_api_key=SecretStr("never-log-me"))
    client = MetaClient(s, "retry", httpx.MockTransport(handler))
    try:
        assert client.structured("review", Opinion).completed
    finally:
        client.close()
    assert len(bodies) == 2 and "Previous response invalid" in str(bodies[-1])
    assert "never-log-me" not in (tmp_path / "runs/retry/calls.jsonl").read_text()


def test_retry_limit(tmp_path):
    calls = []

    def bad(request):
        calls.append(1)
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": "{}"}]}]}
        )

    client = MetaClient(
        cfg(tmp_path, replay_mode=False, model_api_key="test"), "bad", httpx.MockTransport(bad)
    )
    with pytest.raises(ValidationError):
        client.structured("review", Opinion)
    client.close()
    assert len(calls) == 3


def test_sam_cache_avoids_call(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"output": []})

    client = MetaClient(
        cfg(tmp_path, replay_mode=False, model_api_key="test"), "sam", httpx.MockTransport(handler)
    )
    f = tmp_path / "f.jpg"
    f.write_bytes(b"image")
    assert client.segment(f, "tube", "hash", 0) == ""
    assert client.segment(f, "tube", "hash", 0) == ""
    assert len(calls) == 1
    client.close()


def test_cache_provenance(tmp_path):
    cache = ReplayCache(tmp_path)
    cache.put("test", "key", {"a": 1}, "synthetic")
    assert cache.get("test", "key")["provenance"] == "synthetic"


def test_sam_empty_and_malformed_output():
    assert decode("", 64, 64) == []
    with pytest.raises(ValueError):
        decode("<0f>bad<|mask;broken|>", 64, 64)


def event():
    return Event(t=1, step_id="s", kind="step_completed", confidence=0.95, detail="rule evidence")


def opinion(completed=True, confidence=0.9):
    return Opinion(completed=completed, confidence=confidence, reason="test opinion")


def test_shadow_disagreement_does_not_override():
    v = Verifier(lambda *_: opinion(False), lambda *_: opinion(True))
    e = event()
    out = v.review(e, "review", [], shadow=True)
    assert e.kind == "step_completed"
    assert any(x.kind == "shadow_disagreement" for x in out)
    assert all(x.kind != "step_completed" for x in out)


def test_uncertainty_escalates_and_stays_advisory():
    v = Verifier(lambda *_: opinion(confidence=0.4), lambda *_: opinion())
    assert [e.tier for e in v.review(event(), "review", [])] == ["spark", "spark"]


def test_glimmer_unavailable_falls_back():
    def offline(*_):
        raise RuntimeError("offline")

    v = Verifier(offline, lambda *_: opinion())
    assert v.review(event(), "review", [], shadow=True)[0].kind == "escalated"
    assert v.shadow[0]["available"] is False


@pytest.mark.parametrize("tamper", ["event", "evidence", "previous", "delete", "reorder"])
def test_chain_tampering_detected(tamper):
    events = [event().model_dump(), event().model_copy(update={"t": 2}).model_dump()]
    events[0]["evidence_frame"] = "f"
    chain, root = build_chain(events, {"f": b"pixels"})
    assert verify_entries(chain, root, {"f": b"pixels"})
    if tamper == "event":
        chain[0]["event"]["detail"] = "changed"
    if tamper == "evidence":
        chain[0]["evidence_sha256"] = hashlib.sha256(b"changed").hexdigest()
    if tamper == "previous":
        chain[1]["prev_hash"] = "bad"
    if tamper == "delete":
        chain.pop()
    if tamper == "reorder":
        chain.reverse()
    assert not verify_entries(chain, root)


def test_report_escapes_untrusted_text():
    run = {
        "name": "<script>alert(1)</script>",
        "provenance": "test",
        "events": [],
        "states": {},
        "protocol": {"steps": []},
        "metrics": {},
    }
    assert "<script>" not in render_report(run, "root")


def test_replay_api_without_keys(tmp_path):
    with TestClient(create_app(cfg(tmp_path))) as client:
        assert client.get("/api/health").json()["replay_mode"]
        assert len(client.get("/api/samples").json()) == 6
        result = client.post("/api/runs/sample/skipped-cap").json()
        assert result["provenance"] == "synthetic"
        assert any(e["kind"] == "skipped" for e in result["events"])
        assert client.get("/api/runs/" + result["id"] + "/report").status_code == 200
        assert client.post("/api/runs/" + result["id"] + "/verify").json()["valid"]
        assert client.get("/api/runs/bad-id").status_code == 404
        assert client.post("/api/protocols", files={"video": ("v.mp4", b"x")}).status_code == 409


def test_sample_provenance_no_fabricated_metrics():
    r = sample_run("clean")
    assert r["metrics"]["model_calls"] == 0
    assert r["metrics"]["latency_ms"] is None
    assert not r["protocol"]["verified"]


def test_cache_detects_payload_edit(tmp_path):
    cache = ReplayCache(tmp_path)
    cache.put("sam", "key", {"mask": "original"}, "live-meta-sam-3.1")
    path = tmp_path / "sam/key.json"
    value = json.loads(path.read_text())
    value["payload"]["mask"] = "changed"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        cache.get("sam", "key")


def test_validation_refuses_identical_expert_takes(tmp_path):
    from app.samples import sample_protocol
    from app.service import process_validation

    folder = tmp_path / "jobs/same"
    folder.mkdir(parents=True)
    (folder / "original.mp4").write_bytes(b"identical-recording")
    (folder / "heldout.mp4").write_bytes(b"identical-recording")
    (folder / "protocol.json").write_text(sample_protocol().model_dump_json(by_alias=True))
    process_validation(cfg(tmp_path), "same", {}, False)
    status = json.loads((folder / "status.json").read_text())
    assert status["status"] == "error"
    assert "must differ" in status["error"]


def test_sam_video_cost_uses_processed_frame_usage():
    assert MetaClient.estimate("sam", {"video_frames_processed": 50}) == 0.01


def test_model_opinion_rejects_coerced_strings():
    with pytest.raises(ValidationError):
        Opinion.model_validate_json('{"completed":"true","confidence":"0.9","reason":"coercion"}')
