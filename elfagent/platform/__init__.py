"""The elfagent platform shell — domain-agnostic by design (BUILD_SPEC §4, §7).

Nothing in this package knows what a launch, a market or a regulatory annex is.
A use case plugs in by declaring its lean vocabulary, its specialists and a
judgment function; see elfagent/usecases/.
"""

from .contracts import (
    Finding,
    GateType,
    HumanDecision,
    Recommendation,
    SegmentAssessment,
)
from .events import EventSink, EventType, OrchestrationEvent
from .limits import HardStop, RunLimits, SpendLedger
from .orchestrator import Orchestrator, RunState, sqlite_checkpointer
from .registry import (
    ActorKind,
    AgentSpec,
    Registry,
    SpecialistContext,
    ToolSpec,
    UseCase,
    registry,
)
from .tracing import TracingConfig, configure_tracing, run_url

__all__ = [
    "ActorKind",
    "AgentSpec",
    "EventSink",
    "EventType",
    "Finding",
    "GateType",
    "HardStop",
    "HumanDecision",
    "Orchestrator",
    "OrchestrationEvent",
    "Recommendation",
    "Registry",
    "RunLimits",
    "RunState",
    "SegmentAssessment",
    "SpecialistContext",
    "SpendLedger",
    "ToolSpec",
    "TracingConfig",
    "UseCase",
    "configure_tracing",
    "registry",
    "run_url",
    "sqlite_checkpointer",
]
