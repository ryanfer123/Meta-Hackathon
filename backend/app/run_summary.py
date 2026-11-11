"""Read-only summaries of deterministic results; no model opinion becomes a verdict."""

from typing import Any

RULE_FLAGS = {"skipped", "out_of_order", "wrong_object", "dwell_exceeded", "dwell_too_short"}


def summarize(run: dict[str, Any]) -> dict[str, Any]:
    events = run.get("events", [])
    flags = {
        e.get("step_id") for e in events if e.get("tier") == "rules" and e.get("kind") in RULE_FLAGS
    }
    items = []
    for step in run.get("protocol", {}).get("steps", []):
        state = run.get("states", {}).get(step["id"], "PENDING")
        category = (
            "flagged" if step["id"] in flags else "confirmed" if state == "DONE" else "unconfirmed"
        )
        items.append({"id": step["id"], "title": step["title"], "category": category})
    return {
        "confirmed": sum(s["category"] == "confirmed" for s in items),
        "flagged": sum(s["category"] == "flagged" for s in items),
        "unconfirmed": sum(s["category"] == "unconfirmed" for s in items),
        "steps": items,
        "scope": "Configured visible rules only. Unconfirmed means insufficient evidence, not a proven mistake. Model opinions do not change these counts.",
    }
