"""Tolerate presentation wrappers; keep schema validation and completion strict."""

import json
from typing import Any


class ModelOutputIncomplete(RuntimeError):
    """The provider stopped before producing a complete answer. Never auto-retry."""


def ensure_complete(raw: dict[str, Any]) -> None:
    if raw.get("status") == "incomplete" or any(
        choice.get("finish_reason") == "length" for choice in raw.get("choices", [])
    ):
        raise ModelOutputIncomplete("Model output was incomplete or exhausted its token budget")


def json_object_text(content: str) -> str:
    """Extract the first valid balanced object, ignoring prose and Markdown fences.

    JSONDecoder handles escaped quotes, nested objects and braces inside strings.
    The returned object is still validated by the caller's strict Pydantic schema.
    """
    if not isinstance(content, str):
        raise ValueError("Model answer must contain a JSON object")
    decoder = json.JSONDecoder()
    for start, char in enumerate(content):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(content[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
    raise ValueError("Model answer did not contain a complete JSON object")
