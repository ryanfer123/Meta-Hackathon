import hashlib
import json
from pathlib import Path
from typing import Any

from app.replay_cache import canonical, digest


def build_chain(
    events: list[dict[str, Any]], evidence: dict[str, bytes]
) -> tuple[list[dict[str, Any]], str]:
    chain: list[dict[str, Any]] = []
    previous = "0" * 64
    for event in events:
        ref = event.get("evidence_frame")
        entry = {
            "event": event,
            "evidence_sha256": hashlib.sha256(evidence[ref]).hexdigest()
            if ref in evidence
            else None,
            "prev_hash": previous,
        }
        current = digest(entry)
        chain.append({**entry, "hash": current, "canonical_entry": canonical(entry).decode()})
        previous = current
    return chain, previous


def verify_entries(
    entries: list[dict[str, Any]],
    trusted_root: str | None = None,
    evidence: dict[str, bytes] | None = None,
) -> bool:
    previous = "0" * 64
    for entry in entries:
        try:
            payload = {k: entry[k] for k in ("event", "evidence_sha256", "prev_hash")}
            if payload["prev_hash"] != previous or digest(payload) != entry["hash"]:
                return False
            if evidence is not None and payload["evidence_sha256"] is not None:
                ref = payload["event"]["evidence_frame"]
                if (
                    ref not in evidence
                    or hashlib.sha256(evidence[ref]).hexdigest() != payload["evidence_sha256"]
                ):
                    return False
            previous = entry["hash"]
        except (KeyError, TypeError, ValueError):
            return False
    return trusted_root is None or previous == trusted_root


def verify_chain(path: Path, trusted_root: str | None = None) -> bool:
    try:
        entries = json.loads(path.read_text())
        return isinstance(entries, list) and verify_entries(entries, trusted_root)
    except (OSError, ValueError):
        return False
