"""Response-space limits are configurable without bypassing dollar reservations."""

import json

import httpx
import pytest
from app.config import Settings
from app.meta_client import MetaClient
from app.schemas import Opinion
from pydantic import ValidationError


@pytest.mark.parametrize("tokens", [12000, 16000])
def test_spark_structured_uses_configured_output_limit(tmp_path, tokens):
    seen = []

    def response(request):
        seen.append(json.loads(request.content)["max_output_tokens"])
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "completed": False,
                                        "confidence": 0.5,
                                        "reason": "test opinion",
                                    }
                                ),
                            }
                        ]
                    }
                ],
            },
        )

    client = MetaClient(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            replay_mode=False,
            model_api_key="mock-key",
            spark_max_output_tokens=tokens,
        ),
        "configured-response",
        httpx.MockTransport(response),
    )
    try:
        assert not client.structured("review", Opinion).completed
    finally:
        client.close()
    assert seen == [tokens]
    assert (
        json.loads((tmp_path / "runs/configured-response/calls.jsonl").read_text())["reserved_usd"]
        == 0.25
    )


@pytest.mark.parametrize("tokens", [0, 24001])
def test_spark_output_limit_stays_bounded(tokens):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, spark_max_output_tokens=tokens)
