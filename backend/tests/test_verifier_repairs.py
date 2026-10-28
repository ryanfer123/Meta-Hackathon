"""T5 advisory branches, strict extraction and targeted repairs. No network calls."""

import json
from pathlib import Path

import httpx
import pytest
from app import service
from app.audit.report import render_report
from app.config import Settings
from app.glimmer_client import GlimmerClient
from app.main import create_app
from app.meta_client import MetaClient
from app.model_output import ModelOutputIncomplete, json_object_text
from app.samples import sample_protocol
from app.schemas import Event, Opinion
from app.supervise.verifier import Verifier
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect


def completion():
    return Event(t=2, step_id="cap", kind="step_completed", confidence=1, detail="Rules completed")


def answer(completed=True, confidence=0.9):
    return Opinion(completed=completed, confidence=confidence, reason="mock advisory")


def offline(*args):
    raise RuntimeError("Unavailable")


def test_shadow_agreement_never_escalates():
    verifier = Verifier(lambda *_: answer(), lambda *_: pytest.fail("Unexpected escalation"))
    event = completion()
    assert verifier.review(event, "review", [], shadow=True) == []
    assert verifier.shadow == [
        {
            "step_id": "cap",
            "tier": "glimmer",
            "model_label": "glimmer",
            "available": True,
            "agree": True,
            "opinion": answer().model_dump(),
        }
    ]
    assert event.kind == "step_completed"


@pytest.mark.parametrize("open_answer", [answer(False), answer(True, 0.4)])
def test_shadow_escalation_records_both_answers_and_preserves_rules(open_answer):
    verifier = Verifier(lambda *_: open_answer, lambda *_: answer(), open_tier_label="spark-open")
    event = completion()
    events = verifier.review(event, "review", [], shadow=True)
    assert len(verifier.shadow) == 2
    escalated = verifier.shadow[-1]
    assert escalated["tier"] == "spark"
    assert escalated["escalated_from"] == "glimmer"
    assert escalated["escalated_from_label"] == "spark-open"
    assert escalated["agree"] is True
    assert escalated["opinion"] == answer().model_dump()
    assert "spark-open:" in events[-1].detail and "; spark:" in events[-1].detail
    assert '"completed":true' in events[-1].detail
    assert all(e.kind != "step_completed" for e in events)
    assert event.kind == "step_completed"


def test_shadow_open_unavailable_records_spark_result():
    verifier = Verifier(offline, lambda *_: answer())
    events = verifier.review(completion(), "review", [], shadow=True)
    assert events[0].kind == "escalated"
    assert verifier.shadow[0]["available"] is False
    assert verifier.shadow[1]["available"] is True
    assert verifier.shadow[1]["agree"] is True
    assert "unavailable; spark:" in events[-1].detail


def test_shadow_both_unavailable_remains_uncertain():
    verifier = Verifier(offline, offline)
    events = verifier.review(completion(), "review", [], shadow=True)
    assert [r["available"] for r in verifier.shadow] == [False, False]
    assert verifier.shadow[-1]["escalated_from"] == "glimmer"
    assert events[-1].kind == "uncertain"
    assert "human review" in events[-1].detail


@pytest.mark.parametrize(
    "wrapped",
    [
        '```json\n{"completed":true,"confidence":0.9,"reason":"brace } and escaped \\" quote"}\n```',
        'Thinking {not JSON}. Final answer: {"completed":true,"confidence":0.9,"reason":"done"} trailing text',
    ],
)
def test_json_extractor_handles_wrappers_and_escaped_braces(wrapped):
    assert Opinion.model_validate_json(json_object_text(wrapped)).completed


def test_extracted_object_still_requires_strict_schema():
    with pytest.raises(ValidationError):
        Opinion.model_validate_json(
            json_object_text(
                '```json\n{"completed":"true","confidence":0.9,"reason":"no coercion"}\n```'
            )
        )
    with pytest.raises(ValueError):
        json_object_text('{"completed":')


def cfg(tmp_path, **kwargs):
    return Settings(
        _env_file=None, data_dir=tmp_path, replay_mode=False, model_api_key="mock", **kwargs
    )


def test_glimmer_fenced_reply_configured_tokens_auth_and_cloud_egress(tmp_path):
    seen = []
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"synthetic-image-mock-only")

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert str(request.url) == "https://inference.baseten.co/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer mock-open-key"
        assert body["model"] == "meta-models/muse-spark-open-1026"
        assert body["max_tokens"] == 3456
        assert body["messages"][0]["content"][1]["type"] == "image_url"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "Thinking first. ```json\n"
                            + answer().model_dump_json()
                            + "\n```"
                        },
                    }
                ]
            },
        )

    client = GlimmerClient(
        cfg(
            tmp_path,
            glimmer_base_url="https://inference.baseten.co/v1",
            glimmer_api_key="mock-open-key",
            glimmer_model="meta-models/muse-spark-open-1026",
            glimmer_max_tokens=3456,
            open_tier_label="spark-open",
        ),
        "open",
        httpx.MockTransport(handler),
    )
    assert client.opinion("review", [frame]).completed
    log = json.loads((tmp_path / "runs/open/calls.jsonl").read_text())
    assert log["cloud_frames"] == 1 and log["local_frames"] == 0
    assert log["tier"] == "spark-open" and log["open_tier_label"] == "spark-open"
    assert "mock-open-key" not in (tmp_path / "runs/open/calls.jsonl").read_text()
    assert len(seen) == 1


@pytest.mark.parametrize("provider", ["meta", "open"])
def test_incomplete_output_is_logged_once_as_error_not_schema_retry(tmp_path, provider):
    calls = []

    def handler(request):
        calls.append(1)
        if provider == "meta":
            return httpx.Response(200, json={"status": "incomplete", "output": []})
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
        )

    transport = httpx.MockTransport(handler)
    settings = cfg(tmp_path, glimmer_base_url="http://127.0.0.1:8001/v1")
    with pytest.raises(ModelOutputIncomplete):
        if provider == "meta":
            client = MetaClient(settings, provider, transport)
            try:
                client.structured("review", Opinion)
            finally:
                client.close()
        else:
            GlimmerClient(settings, provider, transport).opinion("review", [])
    log = json.loads((tmp_path / "runs" / provider / "calls.jsonl").read_text())
    assert log["status"] == "error"
    if provider == "open":
        assert log["error_type"] == "incomplete"
    assert len(calls) == 1


def test_meta_extractor_repairs_invalid_json_then_accepts_fence(tmp_path):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        text = (
            "incomplete JSON {"
            if len(calls) == 1
            else "```json\n" + answer().model_dump_json() + "\n```"
        )
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": text}]}]}
        )

    client = MetaClient(cfg(tmp_path), "json", httpx.MockTransport(handler))
    try:
        assert client.structured("review", Opinion).completed
    finally:
        client.close()
    assert len(calls) == 2
    assert "Previous response invalid" in str(calls[-1])


def test_failure_selection_includes_discrimination_controls_and_both_replays():
    protocol = sample_protocol()
    result = {
        "steps": {"approach": False, "return": True},
        "counterfactuals": [
            {"step": "return", "swap_with": "cap", "eligible": True, "flagged": False},
            {"step": "label", "eligible": False, "flagged": False},
        ],
        "replay_states": {
            "compile_replay": {"approach": "DONE", "label": "ACTIVE"},
            "held_out": {"return": "PENDING"},
        },
    }
    assert service.failing_step_ids(protocol, result) == ["approach", "return", "cap", "label"]


@pytest.mark.parametrize("case", ["unchanged", "changed", "no-failures"])
def test_validation_repairs_only_failed_step_and_stops_early(tmp_path, monkeypatch, case):
    changed = case == "changed"
    job = "repair"
    folder = tmp_path / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "original.mp4").write_bytes(b"compile")
    (folder / "heldout.mp4").write_bytes(b"heldout")
    protocol = sample_protocol()
    (folder / "protocol.json").write_text(protocol.model_dump_json(by_alias=True))
    calls = []
    validations = []

    def validate(protocol, a, b, ranges):
        validations.append(1)
        good = changed and len(validations) > 1
        return {
            "checks": {"discriminative": good},
            "verified": good,
            "steps": {
                s.id: (s.id != "cap" or good or case == "no-failures") for s in protocol.steps
            },
            "counterfactuals": [],
            "replay_states": {
                "compile_replay": {s.id: "DONE" for s in protocol.steps},
                "held_out": {s.id: "DONE" for s in protocol.steps},
            },
            "repair_rounds": 0,
        }

    def repair(client, step, diagnostics, frames):
        calls.append(step.id)
        return step.model_copy(update={"title": "Repaired cap"}) if changed else step

    monkeypatch.setattr(service, "sample", lambda *a: [(0, Path("mock.jpg"))])
    monkeypatch.setattr(service, "keyframes", lambda *a, **kw: [])
    monkeypatch.setattr(service, "track", lambda *a: [])
    monkeypatch.setattr(service, "validate_protocol", validate)
    monkeypatch.setattr(service, "repair_step", repair)
    service.process_validation(cfg(tmp_path), job, {}, True)
    result = json.loads((folder / "self_check.json").read_text())
    if case == "no-failures":
        assert calls == []
        assert len(validations) == 1
        assert result["repair_rounds"] == 0
        assert len(result["repair_history"]) == 1
        return
    assert calls == ["cap"]
    assert len(validations) == (2 if changed else 1)
    assert result["repair_rounds"] == 1
    assert result["repair_history"][1]["attempted_steps"] == ["cap"]
    assert result["repair_history"][1]["repaired_steps"] == (["cap"] if changed else [])
    assert result["repair_history"][1]["changed_steps"] == (["cap"] if changed else [])


def test_repair_stops_without_identifiable_failing_steps(tmp_path, monkeypatch):
    protocol = sample_protocol()
    assert (
        service.failing_step_ids(
            protocol,
            {
                "steps": {s.id: True for s in protocol.steps},
                "counterfactuals": [],
                "replay_states": {"compile_replay": {s.id: "DONE" for s in protocol.steps}},
            },
        )
        == []
    )


def test_report_and_metrics_display_configured_open_model_label(tmp_path):
    run = {
        "name": "Test",
        "provenance": "test",
        "protocol": {"steps": []},
        "states": {},
        "events": [{**completion().model_dump(), "tier": "glimmer"}],
        "metrics": {"open_tier_label": "spark-open"},
    }
    assert "<td>spark-open</td>" in render_report(run, "root")
    folder = tmp_path / "runs/job"
    folder.mkdir(parents=True)
    (folder / "calls.jsonl").write_text(json.dumps({"tier": "glimmer"}) + "\n")
    metrics = service.call_metrics(cfg(tmp_path, open_tier_label="spark-open"), "job", [])
    assert metrics["tier_distribution"] == {"spark-open": 1}
    assert metrics["open_tier_label"] == "spark-open"


def test_unused_websocket_endpoint_is_removed(tmp_path):
    with TestClient(create_app(cfg(tmp_path))) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/runs/" + "a" * 32):
                pytest.fail("Unused websocket route should not accept connections")


def test_spark_open_configuration_never_uses_default_glimmer_display_label():
    settings = Settings(_env_file=None, glimmer_model="meta-models/muse-spark-open-1026")
    assert settings.open_tier_label == "spark-open"
    assert Settings(_env_file=None).open_tier_label == "glimmer"


def test_glimmer_invalid_schema_retries_are_bounded(tmp_path):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "```json\n{}\n```"}}]})

    client = GlimmerClient(
        cfg(tmp_path, glimmer_base_url="http://localhost:8001/v1"),
        "bad",
        httpx.MockTransport(handler),
    )
    with pytest.raises(ValidationError):
        client.opinion("review", [])
    assert len(calls) == 3
    assert "Correct validation errors" in str(calls[-1])


def test_native_detail_preserves_incomplete_sam_observations_via_real_client(tmp_path, monkeypatch):
    from scripts import spike

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"synthetic-placeholder")
    text = (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(
            200,
            json={
                "status": "incomplete",
                "output": [{"content": [{"type": "output_text", "text": text}]}],
                "usage": {"video_frames_processed": 8},
            },
        )

    monkeypatch.setattr(
        spike,
        "video_metadata",
        lambda _: {"duration_s": 2, "source_average_fps": 4, "source_frames": 8},
    )
    client = MetaClient(cfg(tmp_path), "partial-video", httpx.MockTransport(handler))
    try:
        observed = spike.native_video_detail(client, video, "tube")
    finally:
        client.close()
    assert observed["evidence_status"] == "unknown"
    assert observed["response_status"] == "incomplete"
    assert observed["usage"]["video_frames_processed"] == 8
    assert observed["frame_indices_in_output_order"] == [0]
    assert len(calls) == 1
    log = json.loads((tmp_path / "runs/partial-video/calls.jsonl").read_text())
    assert log["status"] == "error"


def test_image_tracking_does_not_cache_or_use_incomplete_sam_geometry(tmp_path):
    text = (Path(__file__).parent / "fixtures/sam_synthetic.txt").read_text()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(
            200,
            json={
                "status": "incomplete",
                "output": [{"content": [{"type": "output_text", "text": text}]}],
            },
        )

    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"synthetic-placeholder")
    client = MetaClient(cfg(tmp_path), "partial-image", httpx.MockTransport(handler))
    try:
        assert client.segment(frame, "tube", "hash", 0) == ""
        assert client.segment(frame, "tube", "hash", 0) == ""
    finally:
        client.close()
    assert len(calls) == 2  # A later explicit request must not hit a cached partial mask.
