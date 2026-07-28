"""Launch-readiness contracts (BUILD_SPEC §6).

This is the whole of what the use case adds to the platform's contract spine: a
lean vocabulary, a name for what a segment is, and four specialist-specific
extra fields. Everything else — validation, the dissent rule, serialisation —
comes from elfagent.platform.contracts unchanged.
"""

from __future__ import annotations

from enum import Enum

from pydantic import AliasChoices, ConfigDict, Field

from elfagent.platform.contracts import (
    Finding,
    Recommendation,
    SegmentAssessment,
)


class Lean(str, Enum):
    """This use case's vocabulary. The platform has no opinion about it."""

    GO = "go"
    SLIP = "slip"
    PARTIAL = "partial"
    HOLD = "hold"


class MarketReadiness(SegmentAssessment):
    """A segment, for this use case, is a market.

    `ready` stays tri-state from the base contract: None means conditional or
    ambiguous. Combined with `gate_type`, that is what carries the
    "restricted, not banned" nuance through to the human instead of rounding it
    to a boolean somewhere in the middle of the graph.
    """

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    segment: str = Field(
        serialization_alias="market",
        validation_alias=AliasChoices("market", "segment"),
    )

    @property
    def market(self) -> str:
        return self.segment


class LaunchFinding(Finding[Lean]):
    """Base for the four specialists. Segments are markets."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    segments: list[MarketReadiness] = Field(
        default_factory=list,
        serialization_alias="per_market",
        validation_alias=AliasChoices("per_market", "segments"),
    )

    @property
    def per_market(self) -> list[MarketReadiness]:
        return self.segments


class RegulatoryFinding(LaunchFinding):
    # Markets with a hard legal block — the thing that cannot be traded against
    # a schedule preference.
    hard_gate_markets: list[str] = Field(default_factory=list)


class SupplyFinding(LaunchFinding):
    cost_of_delay_note: str = ""


class RetailerFinding(LaunchFinding):
    # Whether shipping only the ready markets is coherent or merely fragmented.
    partial_viable: bool = False


class PackagingFinding(LaunchFinding):
    long_pole_market: str | None = None


class LaunchRecommendation(Recommendation[Lean]):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    per_segment_action: list[MarketReadiness] = Field(
        default_factory=list,
        serialization_alias="per_market_action",
        validation_alias=AliasChoices("per_market_action", "per_segment_action"),
    )
    findings: list[LaunchFinding] = Field(default_factory=list)

    @property
    def per_market_action(self) -> list[MarketReadiness]:
        return self.per_segment_action
