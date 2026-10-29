"""Conservative narration-based timing proposals, never visual ground truth."""

import math
import re
from collections import Counter

from app.learn.validate import StepRange
from app.schemas import Protocol, TranscriptTurn

_STOP = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "the",
    "then",
    "this",
    "to",
    "with",
    "now",
}
_NEGATIVE = {"not", "never", "skip", "without", "dont"}


def _words(text: str) -> set[str]:
    text = re.sub(r"([a-z]+)[ _-]+(\d+)", r"\1\2", text.lower().replace("'", ""))
    return set(re.findall(r"[a-z0-9]+", text)) - _STOP


def suggest_boundaries(
    protocol: Protocol, turns: list[TranscriptTurn], duration: float
) -> dict[str, StepRange]:
    """Match a unique positive narration turn to a step with distinctive shared words.

    Repeated, compound, negative and overlapping matches stay unassigned. The half-
    second padding only proposes a before/after view: a person must check the video
    and confirm or edit every range before validation can use it.
    """
    vocab = {
        step.id: _words(f"{step.id} {step.title} {step.narration_hint}") for step in protocol.steps
    }
    frequency = Counter(word for words in vocab.values() for word in words)
    candidates: dict[str, list[int]] = {}
    for step_id, words in vocab.items():
        matches = []
        for index, turn in enumerate(turns):
            spoken = _words(turn.text)
            shared = spoken & words
            if (
                not spoken & _NEGATIVE
                and len(shared) >= 2
                and any(frequency[word] == 1 for word in shared)
                and 0 <= turn.start < turn.end <= duration
            ):
                matches.append(index)
        candidates[step_id] = matches
    unique = {step: matches[0] for step, matches in candidates.items() if len(matches) == 1}
    uses = Counter(index for matches in candidates.values() for index in matches)
    ranges = {
        step: StepRange(
            start=max(0, turns[index].start - 0.5), end=min(duration, turns[index].end + 0.5)
        )
        for step, index in unique.items()
        if uses[index] == 1
    }
    conflicting = {
        step_id
        for step_id, value in ranges.items()
        for other_id, other in ranges.items()
        if step_id != other_id and value.start <= other.end and other.start <= value.end
    }
    return {step: value for step, value in ranges.items() if step not in conflicting}


def validate_step_ranges(
    protocol: Protocol, ranges: dict[str, StepRange], duration: float | None = None
) -> None:
    """Reject incomplete, placeholder or impossible timings before paid tracking."""
    if set(ranges) != {step.id for step in protocol.steps}:
        raise ValueError("Confirm a valid start/end range for every protocol step")
    if ranges and all(value.start == 0 and value.end == 1 for value in ranges.values()):
        raise ValueError("Replace the 0–1 second placeholders with reviewed timings for every step")
    if duration is not None and (not math.isfinite(duration) or duration <= 0):
        raise ValueError("Cannot establish the original recording duration")
    for step in protocol.steps:
        value = ranges[step.id]
        if value.start >= value.end:
            raise ValueError(f"Step '{step.title}': start must be before end")
        if duration is not None and value.end > duration:
            raise ValueError(
                f"Step '{step.title}': end must be at or before the original recording's {duration:g} seconds"
            )
