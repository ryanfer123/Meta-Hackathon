from collections.abc import Callable
from pathlib import Path

import httpx

from app.schemas import Event, Opinion, Tier

Ask = Callable[[str, list[Path]], Opinion]
_UNAVAILABLE = (RuntimeError, OSError, ValueError, httpx.HTTPError)


class Verifier:
    def __init__(
        self, glimmer: Ask, spark: Ask, api_only: bool = False, open_tier_label: str = "glimmer"
    ) -> None:
        self.glimmer, self.spark = glimmer, spark
        self.api_only = api_only
        self.open_tier_label = open_tier_label
        self.shadow: list[dict[str, object]] = []

    def _record(
        self,
        event: Event,
        tier: Tier,
        answer: Opinion | None,
        reason: str = "Model review unavailable",
        escalated: bool = False,
    ) -> None:
        row: dict[str, object] = {
            "step_id": event.step_id,
            "tier": tier,
            "model_label": self.open_tier_label if tier == "glimmer" else "spark",
            "available": answer is not None,
        }
        if answer is not None:
            row.update(agree=answer.completed, opinion=answer.model_dump())
        else:
            row["reason"] = reason
        if escalated:
            row.update(escalated_from="glimmer", escalated_from_label=self.open_tier_label)
        self.shadow.append(row)

    def review(
        self, event: Event, prompt: str, frames: list[Path], shadow: bool = False
    ) -> list[Event]:
        events: list[Event] = []
        answer: Opinion | None = None
        tier: Tier = "spark" if self.api_only else "glimmer"
        if not self.api_only:
            try:
                answer = self.glimmer(prompt, frames)
                if shadow:
                    self._record(event, "glimmer", answer)
            except _UNAVAILABLE as exc:
                if shadow:
                    self._record(event, "glimmer", None, type(exc).__name__)
            if shadow and answer and not answer.completed:
                events.append(
                    event.model_copy(
                        update={
                            "kind": "shadow_disagreement",
                            "tier": "glimmer",
                            "detail": self.open_tier_label + " advisory: " + answer.reason,
                            "confidence": answer.confidence,
                        }
                    )
                )
        escalate = not self.api_only and (
            answer is None or answer.confidence < 0.7 or (shadow and not answer.completed)
        )
        if self.api_only or escalate:
            previous = answer
            if escalate:
                events.append(
                    event.model_copy(
                        update={
                            "kind": "escalated",
                            "tier": "spark",
                            "detail": self.open_tier_label
                            + " unavailable, uncertain or disagrees.",
                        }
                    )
                )
            tier = "spark"
            try:
                answer = self.spark(
                    prompt
                    + " Advisory only. Never override deterministic rules. Open-tier answer: "
                    + (previous.model_dump_json() if previous else "unavailable"),
                    frames,
                )
                if shadow:
                    self._record(event, "spark", answer, escalated=escalate)
            except _UNAVAILABLE as exc:
                if shadow:
                    self._record(event, "spark", None, type(exc).__name__, escalated=escalate)
                events.append(
                    event.model_copy(
                        update={
                            "kind": "uncertain",
                            "tier": "spark",
                            "detail": "Model review unavailable; human review required. Rules unchanged.",
                        }
                    )
                )
                return events
            if shadow and escalate:
                # Preserve both answers in an evidence event, even if Spark agrees with rules.
                events.append(
                    event.model_copy(
                        update={
                            "kind": "uncertain",
                            "tier": "spark",
                            "confidence": answer.confidence,
                            "detail": "Advisory shadow escalation; rules unchanged. "
                            + self.open_tier_label
                            + ": "
                            + (previous.model_dump_json() if previous else "unavailable")
                            + "; spark: "
                            + answer.model_dump_json(),
                        }
                    )
                )
            elif shadow and not answer.completed:
                events.append(
                    event.model_copy(
                        update={
                            "kind": "shadow_disagreement",
                            "tier": "spark",
                            "detail": answer.reason,
                            "confidence": answer.confidence,
                        }
                    )
                )
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
