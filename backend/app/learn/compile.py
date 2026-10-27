from pathlib import Path

from app.meta_client import MetaClient
from app.schemas import Protocol, Step, TranscriptTurn

PROMPT = """Convert an expert demonstration to a machine-checkable physical protocol.
Return ONLY strict Protocol JSON. List distinct visible objects and short concrete SAM prompts.
Every postcondition must be false before and true after the action. Never use an already-true
condition. Use only present, absent, inside, touching, near, count, moved, order. Add action predicates
for hand/object interactions where observable. Consistent names; hand is implicit. Independent steps
share a contiguous group. Geometry cannot prove liquid transfer, concentration, volume or sterility.
Only describe visible handling; do not infer hidden properties. Verified MUST be false.
"""


def compile_protocol(
    client: MetaClient, frames: list[Path], turns: list[TranscriptTurn]
) -> Protocol:
    prompt = PROMPT + "\nFrame timestamps in filenames: " + str([p.name for p in frames])
    prompt += "\nNarration: " + str([t.model_dump() for t in turns])
    result = client.structured(prompt, Protocol, frames)
    result.verified = False
    return result


def repair_step(client: MetaClient, step: Step, diagnostics: str, frames: list[Path]) -> Step:
    return client.structured(
        "Repair this step using observed predicate diagnostics. Preserve id. "
        + step.model_dump_json()
        + "\n"
        + diagnostics,
        Step,
        frames,
    )
