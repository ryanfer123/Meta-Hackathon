import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.meta_client import image_url
from app.model_output import ModelOutputIncomplete, ensure_complete, json_object_text
from app.replay_cache import canonical
from app.schemas import Opinion


class GlimmerClient:
    def __init__(
        self, settings: Settings, run_id: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.settings, self.run_id = settings, run_id
        self.transport = transport

    def opinion(
        self,
        prompt: str,
        frames: list[Path],
        *,
        max_attempts: int = 3,
        raw_response: Path | None = None,
    ) -> Opinion:
        if not 1 <= max_attempts <= 3:
            raise ValueError("Opinion attempts must be between 1 and 3")
        if not self.settings.glimmer_base_url or self.settings.replay_mode:
            raise RuntimeError("Glimmer endpoint is not configured")
        host = urlparse(self.settings.glimmer_base_url).hostname
        is_local = host in ("localhost", "127.0.0.1", "::1")
        feedback = ""
        for attempt in range(max_attempts):
            start = time.perf_counter()
            status = "error"
            usage: dict[str, Any] = {}
            error_type: str | None = None
            try:
                content: list[dict[str, Any]] = [
                    {
                        "type": "text",
                        "text": prompt
                        + feedback
                        + " Return JSON only: "
                        + json.dumps(Opinion.model_json_schema()),
                    }
                ]
                content.extend(
                    {"type": "image_url", "image_url": {"url": image_url(p)}} for p in frames[:3]
                )
                with httpx.Client(timeout=90, transport=self.transport) as client:
                    response = client.post(
                        self.settings.glimmer_base_url.rstrip("/") + "/chat/completions",
                        headers={
                            "Authorization": "Bearer "
                            + self.settings.glimmer_api_key.get_secret_value()
                        },
                        json={
                            "model": self.settings.glimmer_model,
                            "max_tokens": self.settings.glimmer_max_tokens,
                            "messages": [{"role": "user", "content": content}],
                        },
                    )
                    response.raise_for_status()
                    raw = response.json()
                if raw_response is not None:
                    raw_response.parent.mkdir(parents=True, exist_ok=True)
                    raw_response.write_text(json.dumps(raw, indent=2))
                    raw_response.chmod(0o600)
                usage = raw.get("usage", {})
                ensure_complete(raw)
                result = Opinion.model_validate_json(
                    json_object_text(raw["choices"][0]["message"]["content"])
                )
                status = "ok"
                return result
            except ModelOutputIncomplete:
                error_type = "incomplete"
                raise
            except (ValidationError, ValueError) as exc:
                error_type = "validation"
                feedback = " Correct validation errors: " + str(exc)
                if attempt == max_attempts - 1:
                    raise
            finally:
                path = self.settings.data_dir / "runs" / self.run_id / "calls.jsonl"
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("ab") as log:
                    log.write(
                        canonical(
                            {
                                "model": self.settings.glimmer_model,
                                "tier": self.settings.open_tier_label,
                                "routing_tier": "glimmer",
                                "open_tier_label": self.settings.open_tier_label,
                                "latency_ms": (time.perf_counter() - start) * 1000,
                                "status": status,
                                "error_type": error_type,
                                "usage": usage,
                                "cost_estimate_usd": None,
                                "cloud_frames": 0 if is_local else len(frames[:3]),
                                "local_frames": len(frames[:3]) if is_local else 0,
                            }
                        )
                        + b"\n"
                    )
        raise RuntimeError("unreachable")
