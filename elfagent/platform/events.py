"""The normalised event stream the front end animates against (BUILD_SPEC §4.1).

There are three trace surfaces fed by TWO data sources, and getting this wrong
is the single easiest mistake to make by taking the convenient path:

  1. Live orchestration view (our React app)  <- THIS event stream, real-time.
  2. Trace drawer (our React app)             <- these same events, captured.
  3. LangSmith console (as-is)                <- LangSmith, the "is this real?" proof.

LangSmith is the recording and observability backend. It is after-the-fact and
cannot show live execution, so it is NOT the data source for the live fan-out.
These events are emitted by LangGraph nodes as they execute, via LangGraph's own
stream writer, and surfaced to the API as they happen.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    SIGNAL_FIRED = "signal_fired"
    FAN_OUT = "fan_out"

    AGENT_STARTED = "agent_started"
    AGENT_TOOL_CALL = "agent_tool_call"
    AGENT_RETURNED = "agent_returned"
    AGENT_FAILED = "agent_failed"

    JUDGMENT_STARTED = "judgment_started"
    JUDGMENT_RETURNED = "judgment_returned"

    AWAITING_HUMAN = "awaiting_human"
    DECISION_RECORDED = "decision_recorded"

    LIMIT_EXCEEDED = "limit_exceeded"
    RUN_FAILED = "run_failed"
    RUN_COMPLETED = "run_completed"


class OrchestrationEvent(BaseModel):
    """One thing that happened, in order, as it happened."""

    type: EventType
    run_id: str
    seq: int = 0
    at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    # Which specialist this concerns, when it concerns one.
    agent: str | None = None

    # Whether the actor is an AGENT (reasons) or a TOOL (deterministic lookup).
    # Carried on the event, not inferred by the UI, so the tool-vs-agent
    # distinction is structural rather than a label someone remembered to add.
    actor_kind: str | None = None

    payload: dict[str, Any] = Field(default_factory=dict)


class EventSink:
    """Collects a run's events in order and assigns sequence numbers.

    The same events feed the live stream and, once the run is finished, the
    trace drawer — so surface 2 never has to be reconstructed from a different
    source than surface 1.
    """

    def __init__(self, run_id: str, start_seq: int = 0) -> None:
        self.run_id = run_id
        # A resumed run continues the original sequence rather than restarting
        # at 1. Two events numbered 1 in one trace would sort the human's
        # decision ahead of the run that produced it.
        self._seq = start_seq
        self.events: list[OrchestrationEvent] = []

    def emit(
        self,
        type: EventType,
        *,
        agent: str | None = None,
        actor_kind: str | None = None,
        **payload: Any,
    ) -> OrchestrationEvent:
        self._seq += 1
        event = OrchestrationEvent(
            type=type,
            run_id=self.run_id,
            seq=self._seq,
            agent=agent,
            actor_kind=actor_kind,
            payload=payload,
        )
        self.events.append(event)
        return event
