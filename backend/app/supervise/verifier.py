from collections.abc import Callable
from pathlib import Path

import httpx

from app.schemas import Event, Opinion, Tier

Ask = Callable[[str, list[Path]], Opinion]


class Verifier:
    def __init__(self, glimmer: Ask, spark: Ask) -> None:
        self.glimmer, self.spark = glimmer, spark
        self.shadow: list[dict[str, object]] = []

    def review(
        self, event: Event, prompt: str, frames: list[Path], shadow: bool = False
    ) -> list[Event]:
        events: list[Event] = []
        answer: Opinion | None = None
        tier: Tier = "glimmer"
        try:
            answer = self.glimmer(prompt, frames)
            if shadow:
                self.shadow.append(
                    {
                        "step_id": event.step_id,
                        "available": True,
                        "agree": answer.completed,
                        "opinion": answer.model_dump(),
                    }
                )
        except (RuntimeError, OSError, ValueError, httpx.HTTPError) as exc:
            if shadow:
                self.shadow.append(
                    {"step_id": event.step_id, "available": False, "reason": type(exc).__name__}
                )
        if shadow and answer and not answer.completed:
            events.append(
                event.model_copy(
                    update={
                        "kind": "shadow_disagreement",
                        "tier": "glimmer",
                        "detail": answer.reason,
                        "confidence": answer.confidence,
                    }
                )
            )
        if answer is None or answer.confidence < 0.7 or (shadow and not answer.completed):
            events.append(
                event.model_copy(
                    update={
                        "kind": "escalated",
                        "tier": "spark",
                        "detail": "Glimmer unavailable, uncertain or disagrees.",
                    }
                )
            )
            tier = "spark"
            try:
                answer = self.spark(
                    prompt + " Advisory review only. Glimmer: " + str(answer), frames
                )
            except (RuntimeError, OSError, ValueError, httpx.HTTPError):
                events.append(
                    event.model_copy(
                        update={
                            "kind": "uncertain",
                            "tier": "spark",
                            "detail": "Model review unavailable; human review required.",
                        }
                    )
                )
                return events
        if not shadow:
            assert answer is not None
            events.append(
                event.model_copy(
                    update={
                        "kind": "uncertain",
                        "tier": tier,
                        "confidence": answer.confidence,
                        "detail": "Advisory only; rule evidence still required. " + answer.reason,
                    }
                )
            )
        return events
