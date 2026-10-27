from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Present(StrictModel):
    op: Literal["present"] = "present"
    obj: str


class Absent(StrictModel):
    op: Literal["absent"] = "absent"
    obj: str


class Inside(StrictModel):
    op: Literal["inside"] = "inside"
    a: str
    b: str
    min_containment: float = Field(default=0.8, ge=0, le=1)


class Touching(StrictModel):
    op: Literal["touching"] = "touching"
    a: str
    b: str
    max_gap_px: float = Field(default=8, ge=0, le=200)


class Near(StrictModel):
    op: Literal["near"] = "near"
    a: str
    b: str
    max_dist_norm: float = Field(default=0.15, ge=0, le=2)


class Count(StrictModel):
    op: Literal["count"] = "count"
    obj_class: str
    eq: int = Field(ge=0, le=100)


class Moved(StrictModel):
    op: Literal["moved"] = "moved"
    obj: str
    min_dist_norm: float = Field(default=0.1, gt=0, le=2)
    within_s: float = Field(default=5, gt=0, le=60)


class Order(StrictModel):
    op: Literal["order"] = "order"
    first: str
    then: str


Predicate = Annotated[
    Present | Absent | Inside | Touching | Near | Count | Moved | Order, Field(discriminator="op")
]


class ObjectSpec(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    sam_prompt: str = Field(min_length=1, max_length=200)
    obj_class: str = Field(alias="class")
    # Optional explicit HSV calibration. Never silently infer colors from object names.
    hsv_lower: tuple[int, int, int] | None = None
    hsv_upper: tuple[int, int, int] | None = None


class Step(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    title: str = Field(min_length=1, max_length=200)
    narration_hint: str = ""
    pre: list[Predicate] = Field(default_factory=list)
    action: list[Predicate] = Field(default_factory=list)
    post: list[Predicate] = Field(min_length=1)
    group: str | None = None
    min_dwell_s: float = Field(default=0, ge=0)
    max_dwell_s: float = Field(default=60, gt=0, le=600)
    critical: bool = True

    @model_validator(mode="after")
    def valid_dwell(self) -> "Step":
        if self.min_dwell_s > self.max_dwell_s:
            raise ValueError("minimum dwell exceeds maximum")
        return self


class Protocol(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    objects: list[ObjectSpec] = Field(min_length=1, max_length=20)
    steps: list[Step] = Field(min_length=1, max_length=30)
    order_strict: bool = True
    verified: bool = False

    @model_validator(mode="after")
    def references(self) -> "Protocol":
        names = [o.name for o in self.objects]
        if len(names) != len(set(names)):
            raise ValueError("duplicate objects")
        if "hand" not in names:
            self.objects.append(
                ObjectSpec.model_validate({"name": "hand", "sam_prompt": "hand", "class": "hand"})
            )
        names = [o.name for o in self.objects]
        if len({s.id for s in self.steps}) != len(self.steps):
            raise ValueError("duplicate step IDs")
        seen_groups: set[str] = set()
        last: str | None = None
        for step in self.steps:
            if step.group and step.group != last:
                if step.group in seen_groups:
                    raise ValueError("unordered groups must be contiguous")
                seen_groups.add(step.group)
            last = step.group
            for p in step.pre + step.action + step.post:
                for key in ("obj", "a", "b", "first", "then"):
                    ref = getattr(p, key, None)
                    if ref is not None and ref not in names:
                        raise ValueError(f"unknown object {ref}")
        return self


EventKind = Literal[
    "step_started",
    "step_completed",
    "skipped",
    "out_of_order",
    "wrong_object",
    "dwell_exceeded",
    "dwell_too_short",
    "uncertain",
    "escalated",
    "resolved",
    "shadow_disagreement",
]
Tier = Literal["rules", "glimmer", "spark"]


class Event(StrictModel):
    t: float = Field(ge=0)
    step_id: str | None
    kind: EventKind
    tier: Tier = "rules"
    confidence: float = Field(ge=0, le=1)
    evidence_frame: str | None = None
    detail: str


class Opinion(StrictModel):
    completed: bool
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=1000)


class TranscriptTurn(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str

    @model_validator(mode="after")
    def ordered(self) -> "TranscriptTurn":
        if self.end < self.start:
            raise ValueError("transcript ends before it starts")
        return self
