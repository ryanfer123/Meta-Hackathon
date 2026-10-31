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
Use independently identifiable physical objects, not overlapping names for parts of one object.
Do not invent left/right rope segments or indistinguishable end identities as separate objects.
Avoid moved on a deforming whole object: its centroid can stay still while its shape changes.
If a procedure cannot be represented by these predicates, return only directly checkable handling
steps; never invent predicates that certify topology or infer action order from a finished shape.
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
