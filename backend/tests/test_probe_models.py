"""Probe contracts without live providers or credentials."""

import json
import sys

import httpx
import pytest
from app.config import Settings
from app.glimmer_client import GlimmerClient
from app.model_output import ModelOutputIncomplete

from scripts import probe_models


def test_probe_refuses_missing_paid_flag_before_reading_configuration(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["probe_models.py", "--kind", "open-image", "--image", "x.jpg", "--run-id", "probe"],
    )
    monkeypatch.setattr(probe_models, "Settings", lambda: pytest.fail("must require consent first"))
    with pytest.raises(SystemExit) as exc:
        probe_models.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("finish,content", [("stop", "invalid-json"), ("length", "")])
def test_open_probe_one_attempt_retains_raw_even_when_validation_fails(tmp_path, finish, content):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"synthetic-image-placeholder")
    raw = {
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2},
    }
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=raw)

    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        replay_mode=False,
        glimmer_base_url="https://inference.baseten.co/v1",
        glimmer_model="meta-models/muse-spark-open-1026",
    )
    client = GlimmerClient(settings, "one-call", httpx.MockTransport(handle))
    target = tmp_path / "response.json"
    with pytest.raises((ValueError, ModelOutputIncomplete)):
        client.opinion("describe", [image], max_attempts=1, raw_response=target)
    assert len(calls) == 1
    assert json.loads(target.read_text()) == raw
    assert target.stat().st_mode & 0o777 == 0o600
