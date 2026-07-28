"""Typed contracts — the spine of the platform (BUILD_SPEC §6).

Every hand-off between nodes carries a validated object, never prose. That kills
the format-mismatch failure mode and makes a run inspectable after the fact.

These base classes are DOMAIN-AGNOSTIC. They know that specialists produce a
lean with confidence and evidence, and that a judgment layer reconciles several
of those into one recommendation with dissent preserved. They do not know what
the leans are called or what a segment is.

Each use case supplies its own vocabulary by parameterising the generic:

    launch readiness  ->  Lean = go | slip | partial | hold, segment = market
    deductions        ->  Lean = accept | dispute | investigate, segment = claim line

That is what makes "one platform, four use cases" true rather than aspirational.
Adding a use case means declaring an enum and a set of specialists, not editing
anything in this file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The lean vocabulary is supplied by the use case, not fixed here.
LeanT = TypeVar("LeanT", bound=Enum)


class GateType(str, Enum):
    """Why a segment is not ready.

    The distinction is load-bearing. A HARD gate is a legal or physical block
    that cannot be traded against a schedule preference. A CONDITIONAL gate is
    real but has a path through it. Collapsing the two into a single boolean is
    what turns a judgment call into a flag lookup.
    """

    HARD = "hard"
    CONDITIONAL = "conditional"


class SegmentAssessment(BaseModel):
    """Readiness of one slice of the subject.

    A "segment" is whatever a use case slices by — market, retailer, channel,
    claim line. `ready` is deliberately tri-state: None means conditional or
    ambiguous, and that ambiguity must survive to the human rather than being
    rounded to a boolean somewhere in the middle of the graph.
    """

    model_config = ConfigDict(populate_by_name=True)

    segment: str
    ready: bool | None = None
    gate_type: GateType | None = None
    detail: str = ""


class Finding(BaseModel, Generic[LeanT]):
    """The base shape every specialist returns.

    A specialist that cannot express its conclusion in this shape is doing
    something other than assessing readiness, which is a design signal worth
    listening to.
    """

    model_config = ConfigDict(populate_by_name=True)

    agent: str
    lean: LeanT
    confidence: float = Field(ge=0, le=1)
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    segments: list[SegmentAssessment] = Field(default_factory=list)

    # Which governed definition set this finding was computed against, so a run
    # can always be tied back to the semantics that produced it.
    semantic_version: str

    def segment(self, name: str) -> SegmentAssessment | None:
        return next((s for s in self.segments if s.segment == name), None)

    def hard_gated_segments(self) -> list[str]:
        return [s.segment for s in self.segments if s.gate_type is GateType.HARD]


class Recommendation(BaseModel, Generic[LeanT]):
    """What judgment produces. Recommends; never acts."""

    model_config = ConfigDict(populate_by_name=True)

    subject_id: str
    recommended_action: LeanT
    per_segment_action: list[SegmentAssessment] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    # How the findings were combined — the reasoning, not a restatement.
    reconciliation: str

    # Findings pointing the other way, PRESERVED. Never summarised away.
    dissent: list[str] = Field(default_factory=list)

    # The raw specialist findings, for the trace panel.
    findings: list[Finding[LeanT]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _dissent_required_when_leans_conflict(self) -> "Recommendation[LeanT]":
        """False consensus is a documented failure mode; its absence is the point.

        BUILD_SPEC §10 asks for this to be asserted in code rather than trusted
        to a prompt. If the specialists disagreed and the reconciliation came
        back with an empty dissent list, the run is wrong — fail loudly here
        rather than shipping a confident-looking recommendation that quietly
        dropped the minority view.
        """
        leans = {f.lean for f in self.findings}
        if len(leans) > 1 and not self.dissent:
            disagreement = ", ".join(
                f"{f.agent}={getattr(f.lean, 'value', f.lean)}" for f in self.findings
            )
            raise ValueError(
                "dissent must not be empty when specialist leans conflict "
                f"({disagreement}). Collapsing to false consensus is a documented "
                "failure mode this contract exists to prevent."
            )
        return self

    @property
    def is_contested(self) -> bool:
        return len({f.lean for f in self.findings}) > 1


class HumanDecision(BaseModel, Generic[LeanT]):
    """The decision a human actually took. Closes the loop.

    The system recommends; it cannot act. No tool anywhere writes this — it
    arrives from the human gate and is recorded (BUILD_SPEC §1.4, §10).
    """

    model_config = ConfigDict(populate_by_name=True)

    subject_id: str
    decided_action: LeanT
    decided_by: str
    followed_recommendation: bool
    note: str = ""
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
