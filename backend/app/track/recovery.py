"""One bounded attempt to recover missing pixels; completion remains a rule decision."""

import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.budget import BudgetExceeded
from app.meta_client import MetaClient
from app.model_output import ModelOutputIncomplete
from app.schemas import Event, ObjectSpec, Protocol
from app.track.geometry import Detection, FrameState
from app.track.sam import decode


class RefinedPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    object_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    prompt: str = Field(min_length=1, max_length=80)

    @field_validator("prompt")
    @classmethod
    def short_noun_phrase(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z]+(?:[ -][A-Za-z]+){0,11}", value):
            raise ValueError("Use one short noun phrase with no commands, lists or newlines")
        blocked = {
            "ignore",
            "return",
            "output",
            "detect",
            "segment",
            "show",
            "find",
            "draw",
            "select",
            "complete",
            "mark",
            "approve",
            "instructions",
            "system",
            "then",
            "and",
            "or",
            "near",
            "inside",
            "touching",
            "with",
            "without",
            "next",
        }
        if set(re.findall(r"[a-z]+", value.lower())) & blocked:
            raise ValueError("Only the object's appearance may refine its noun phrase")
        return value


@dataclass(frozen=True)
class RecoveryResult:
    frames: list[FrameState]
    actions: list[dict[str, Any]]
    changed_frame: int | None = None


def _words(value: str) -> set[str]:
    return set(re.findall(r"[a-z]+", value.lower()))


def _same_object(plan: RefinedPrompt, obj: ObjectSpec, protocol: Protocol) -> bool:
    if plan.object_name != obj.name or plan.prompt.casefold() == obj.sam_prompt.strip().casefold():
        return False
    original_words = re.findall(r"[a-z]+", obj.sam_prompt.lower())
    noun = original_words[-1] if original_words else ""
    class_words = _words(obj.obj_class)
    words = _words(plan.prompt)
    if noun not in words and not (class_words and class_words <= words):
        return False
    # Do not introduce a different known object class into this single-concept query.
    other_classes = {
        other.obj_class.lower() for other in protocol.objects if other.obj_class != obj.obj_class
    }
    return not any(_words(other) <= words for other in other_classes if _words(other))


def recover_once(
    client: MetaClient,
    protocol: Protocol,
    frames: list[FrameState],
    sampled_paths: list[tuple[float, Path]],
    events: list[Event],
    video_hash: str,
) -> RecoveryResult:
    """Refine one unknown object on one frame at the first uncertain step.

    The persisted per-run claim prevents repeated refinement plans on retries. A
    plan uses the normal strict structured client (at most three schema attempts),
    followed by at most one separately budgeted/cached SAM image request. Existing
    known evidence and the protocol are untouched. The caller must replay rules.
    """
    event = next((event for event in events if event.kind == "uncertain"), None)
    step = next((step for step in protocol.steps if event and step.id == event.step_id), None)
    if event is None or step is None:
        return RecoveryResult(
            frames, [{"attempted": False, "status": "skipped", "reason": "no uncertain step"}]
        )
    names = {
        str(getattr(predicate, key))
        for predicate in step.pre + step.action + step.post
        for key in ("obj", "a", "b")
        if hasattr(predicate, key)
    }
    paths = dict(sampled_paths)
    target: tuple[int, ObjectSpec, Path] | None = None
    nearby = sorted(
        ((i, frame) for i, frame in enumerate(frames) if abs(frame.t - event.t) <= 1),
        key=lambda pair: (abs(pair[1].t - event.t), pair[1].t),
    )
    for index, frame in nearby:
        path = paths.get(frame.t)
        if path is None or not path.is_file():
            continue
        obj = next(
            (
                obj
                for obj in protocol.objects
                if obj.name in names and frame.objects.get(obj.name) is None
            ),
            None,
        )
        if obj is not None:
            target = index, obj, path
            break
    if target is None:
        return RecoveryResult(
            frames,
            [
                {
                    "attempted": False,
                    "status": "skipped",
                    "reason": "no missing referenced object on a nearby sampled frame",
                }
            ],
        )
    index, obj, path = target
    marker = client.budget.log_path(client.run_id).parent / "recovery.json"
    try:
        with marker.open("x") as claim:
            claim.write('{"status":"attempting"}\n')
    except FileExistsError:
        return RecoveryResult(
            frames,
            [
                {
                    "attempted": False,
                    "status": "skipped",
                    "reason": "per-job recovery allowance already used",
                }
            ],
        )
    action: dict[str, Any] = {
        "attempted": True,
        "status": "attempting",
        "step_id": step.id,
        "object_name": obj.name,
        "frame_index": index,
        "t": frames[index].t,
        "original_prompt": obj.sam_prompt,
        "reason": "missing object at uncertain step",
    }

    def finish(
        status: str, reason: str, output: list[FrameState] = frames, changed: int | None = None
    ) -> RecoveryResult:
        action.update(status=status, reason=reason)
        marker.write_text(json.dumps(action, sort_keys=True) + "\n")
        client.tracking_notice("active_recovery", json.dumps(action, sort_keys=True))
        return RecoveryResult(output, [action], changed)

    try:
        plan = client.structured(
            "Refine a segmentation noun phrase for the SAME existing object in this image. "
            "Describe only its visible appearance; do not add another object or decide step completion. "
            "Return the exact object_name below and one different, short noun phrase (max80 characters). "
            "No commands, lists, relations or new objects. Target: "
            + json.dumps(
                {"object_name": obj.name, "class": obj.obj_class, "original_prompt": obj.sam_prompt}
            ),
            RefinedPrompt,
            [path],
        )
        if not _same_object(plan, obj, protocol):
            return finish(
                "rejected", "refinement changed identity, concept, or did not change the prompt"
            )
        action["refined_prompt"] = plan.prompt
        candidates = decode(
            client.segment(path, plan.prompt, video_hash, index),
            frames[index].width,
            frames[index].height,
        )
        if len(candidates) != 1:
            return finish("unresolved", "image query had zero or multiple candidates")
        candidate = candidates[0]
        mask = candidate.mask
        if (
            not math.isfinite(candidate.score)
            or not 0.7 <= candidate.score <= 1
            or mask is None
            or not mask.any()
        ):
            return finish(
                "unresolved",
                "image query did not establish one nonempty mask with confidence at least0.7",
            )
        if frames[index].objects.get(obj.name) is not None:
            return finish("skipped", "existing evidence is never replaced")
        objects = dict(frames[index].objects)
        objects[obj.name] = Detection(mask, candidate.score, obj.obj_class)
        output = list(frames)
        output[index] = replace(frames[index], objects=objects)
        return finish(
            "recovered", "one missing mask recovered; rules must be replayed", output, index
        )
    except BudgetExceeded:
        finish("budget_denied", "budget refused a recovery call; no further request permitted")
        raise
    except (ValueError, httpx.HTTPError, ModelOutputIncomplete) as exc:
        return finish("unresolved", "recovery failed: " + type(exc).__name__)
