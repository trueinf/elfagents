"""The orchestrator — a LangGraph star graph (BUILD_SPEC §4).

    SIGNAL (deterministic, not an agent)
        |
    ORCHESTRATOR ---> specialist ---.
        |         \-> specialist ---+--> JUDGMENT --> HUMAN GATE --> decision
        |         \-> specialist ---'      (reconcile,     (graph
        |         \-> specialist ---'       preserve        genuinely
                                            dissent)        pauses)

Why a star and not peer-to-peer: multi-agent systems where agents call each
other fail at high rates (Berkeley MAST: 41-86.7% across seven frameworks), and
the failures concentrate in inter-agent hand-offs where context degrades. One
coordinator holding state structurally eliminates that class of failure. Here
that is enforced by construction — specialists are handed a SpecialistContext
that does not contain the other findings, and there is no edge between them.

This module is DOMAIN-AGNOSTIC. It knows about specialists, judgment and a human
gate. It knows nothing about launches, markets or regulatory annexes.
"""

from __future__ import annotations

import operator
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncIterator, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

try:  # LangGraph's per-node stream writer — how nodes emit in real time.
    from langgraph.config import get_stream_writer
except ImportError:  # pragma: no cover
    get_stream_writer = None  # type: ignore[assignment]

from .events import EventSink, EventType, OrchestrationEvent
from .limits import HardStop, RunLimits, SpendLedger
from .registry import SpecialistContext, UseCase


def accumulate(existing: list | None, incoming: list | None) -> list:
    """Collect findings from parallel specialists; `None` resets the slot.

    A plain `operator.add` reducer is correct within one run and wrong across
    two: re-running an existing thread would append to the previous run's
    findings, and judgment would reconcile eight findings from four
    specialists without anything looking obviously broken. The reset is what
    makes "run again" mean run again rather than run more.
    """
    if incoming is None:
        return []
    return [*(existing or []), *incoming]


class RunState(TypedDict, total=False):
    """Graph state.

    Everything here is plain JSON-serialisable data, deliberately. State crosses
    a serialisation boundary at every checkpoint, and a run resumed in a fresh
    process gets dicts back, not Python objects. Storing validated models here
    would work right up until the kill-and-resume demo, then quietly fail.

    Typing is not weakened by this — it is enforced at the boundaries instead:
    a specialist must return its declared `finding_model`, and judgment
    re-validates every finding back into that model before reasoning over it.
    The contract is checked twice rather than assumed once.
    """

    run_id: str
    subject_id: str
    subject: dict[str, Any]

    # Reducer: parallel specialists each append their own finding, so the
    # fan-in is an accumulation rather than four nodes racing to overwrite one
    # slot. This is what makes the parallel fan-out safe.
    findings: Annotated[list[dict[str, Any]], accumulate]

    recommendation: dict[str, Any]
    decision: dict[str, Any]
    spend: dict[str, Any]


def _emitter():
    """Return an emit(**kwargs) bound to LangGraph's stream writer.

    Falls back to a no-op when there is no active stream (e.g. a plain
    ainvoke), so nodes never have to care whether anyone is listening.
    """
    if get_stream_writer is None:
        return lambda **kw: None
    try:
        writer = get_stream_writer()
    except Exception:
        return lambda **kw: None
    return lambda **kw: writer(kw)


@asynccontextmanager
async def sqlite_checkpointer(path: str):
    """Durable checkpointing to a file (BUILD_SPEC §10).

    A file, not memory, precisely because the demo kills the process mid-run
    and resumes. An in-memory saver would make that demo a lie.
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    async with AsyncSqliteSaver.from_conn_string(path) as checkpointer:
        yield checkpointer


class Orchestrator:
    """Runs one use case. Holds shared state; specialists never talk directly."""

    def __init__(
        self,
        use_case: UseCase,
        *,
        checkpointer: Any,
        limits: RunLimits | None = None,
    ) -> None:
        self.use_case = use_case
        self.limits = limits or RunLimits()
        self.checkpointer = checkpointer
        self.graph = self._build()

    # ---------------------------------------------------------------- graph

    def _build(self):
        g = StateGraph(RunState)

        for spec in self.use_case.specialists:
            g.add_node(spec.name, self._specialist_node(spec))
            # Fan out: every specialist hangs off START, so they all run in the
            # same superstep — genuinely concurrent, not sequenced.
            g.add_edge(START, spec.name)
            # Fan in: judgment waits for all of them.
            g.add_edge(spec.name, "judgment")

        g.add_node("judgment", self._judgment_node)
        g.add_node("human_gate", self._human_gate_node)
        g.add_edge("judgment", "human_gate")
        g.add_edge("human_gate", END)

        return g.compile(checkpointer=self.checkpointer)

    def _context(
        self, state: RunState, config: RunnableConfig, emit
    ) -> SpecialistContext:
        ledger: SpendLedger = config["configurable"]["ledger"]
        return SpecialistContext(
            subject_id=state["subject_id"],
            subject=state.get("subject", {}),
            ledger=ledger,
            semantic_version=self.use_case.semantic_version,
            emit=emit,
        )

    def _specialist_node(self, spec):
        async def node(state: RunState, config: RunnableConfig) -> dict:
            emit = _emitter()
            emit(
                type=EventType.AGENT_STARTED.value,
                agent=spec.name,
                actor_kind="agent",
                question=spec.question,
                tools=list(spec.tools),
            )
            ctx = self._context(state, config, emit)
            try:
                finding = await spec.run(ctx)
                if not isinstance(finding, spec.finding_model):
                    raise TypeError(
                        f"{spec.name} returned {type(finding).__name__}; "
                        f"contract requires {spec.finding_model.__name__}"
                    )
            except HardStop as stop:
                emit(
                    type=EventType.LIMIT_EXCEEDED.value,
                    agent=spec.name,
                    limit=stop.limit,
                    detail=stop.detail,
                )
                raise
            except Exception as exc:
                emit(
                    type=EventType.AGENT_FAILED.value,
                    agent=spec.name,
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise

            emit(
                type=EventType.AGENT_RETURNED.value,
                agent=spec.name,
                actor_kind="agent",
                finding=finding.model_dump(mode="json"),
            )
            return {"findings": [finding.model_dump(mode="json")]}

        node.__name__ = spec.name
        return node

    async def _judgment_node(self, state: RunState, config: RunnableConfig) -> dict:
        emit = _emitter()

        # Re-validate every finding back into its declared contract before
        # judgment reasons over it. This is the second half of the typed
        # hand-off, and the half that still holds after a resume from disk.
        findings = [
            self.use_case.finding_model_for(raw["agent"]).model_validate(raw)
            for raw in state.get("findings", [])
        ]

        emit(
            type=EventType.JUDGMENT_STARTED.value,
            agent="judgment",
            actor_kind="agent",
            finding_count=len(findings),
            leans={f.agent: getattr(f.lean, "value", f.lean) for f in findings},
        )
        ctx = self._context(state, config, emit)
        recommendation = await self.use_case.judgment(ctx, findings)
        if not isinstance(recommendation, self.use_case.recommendation_model):
            raise TypeError(
                f"judgment returned {type(recommendation).__name__}; contract "
                f"requires {self.use_case.recommendation_model.__name__}"
            )

        payload = recommendation.model_dump(mode="json")
        ledger: SpendLedger = config["configurable"]["ledger"]
        snapshot = ledger.snapshot()
        emit(
            type=EventType.JUDGMENT_RETURNED.value,
            agent="judgment",
            actor_kind="agent",
            recommendation=payload,
            # What the run actually cost, on the stream rather than only in
            # state. A caller that watches events and never reads state — the
            # API's spend accounting, for one — would otherwise see nothing.
            spend=snapshot,
        )
        return {"recommendation": payload, "spend": snapshot}

    async def _human_gate_node(self, state: RunState, config: RunnableConfig) -> dict:
        """The gate is first-class state. The graph genuinely stops here.

        Nothing downstream of this node can run until a human supplies a
        decision. There is no tool anywhere that writes one — the value arrives
        from outside the system, via resume (BUILD_SPEC §1.4, §10).
        """
        decision = interrupt(
            {
                "subject_id": state["subject_id"],
                "recommendation": state.get("recommendation"),
            }
        )
        emit = _emitter()
        emit(
            type=EventType.DECISION_RECORDED.value,
            agent="human_gate",
            actor_kind="human",
            decision=decision,
        )
        return {"decision": decision}

    # --------------------------------------------------------------- stream

    async def _pump(self, stream, sink: EventSink) -> AsyncIterator[OrchestrationEvent]:
        async for mode, chunk in stream:
            if mode == "custom" and isinstance(chunk, dict):
                data = dict(chunk)
                try:
                    etype = EventType(data.pop("type"))
                except (KeyError, ValueError):
                    continue
                yield sink.emit(
                    etype,
                    agent=data.pop("agent", None),
                    actor_kind=data.pop("actor_kind", None),
                    **data,
                )
            elif mode == "updates" and isinstance(chunk, dict):
                if "__interrupt__" in chunk:
                    interrupts = chunk["__interrupt__"]
                    value = interrupts[0].value if interrupts else {}
                    payload = value if isinstance(value, dict) else {"value": value}
                    yield sink.emit(EventType.AWAITING_HUMAN, **payload)

    async def astream(
        self,
        subject_id: str,
        *,
        subject: dict[str, Any] | None = None,
        thread_id: str | None = None,
    ) -> AsyncIterator[OrchestrationEvent]:
        """Run the flow, yielding events AS THEY HAPPEN.

        This is the data source for the live orchestration view (BUILD_SPEC
        §4.1 surface 1). The events come off LangGraph's own stream as nodes
        execute — not from polling LangSmith after the fact, which could not
        animate a fan-out even in principle.
        """
        thread_id = thread_id or f"run_{uuid.uuid4().hex[:8]}"
        sink = EventSink(thread_id)
        ledger = SpendLedger(self.limits)
        config = {
            "configurable": {"thread_id": thread_id, "ledger": ledger},
            # Stamped onto the LangSmith trace so the recorded run can be found
            # again by thread. Without it the console shows a list of runs with
            # no way to tell which one the app is displaying — and "flip to the
            # same run in raw tooling" becomes "go and hunt for it".
            "run_name": f"{self.use_case.key}:{subject_id}",
            "metadata": {
                "elfagent_thread": thread_id,
                "elfagent_subject": subject_id,
                "elfagent_use_case": self.use_case.key,
            },
        }

        yield sink.emit(
            EventType.RUN_STARTED,
            subject_id=subject_id,
            use_case=self.use_case.key,
            thread_id=thread_id,
        )
        yield sink.emit(
            EventType.FAN_OUT,
            topology="star",
            parallel=True,
            agents=[s.name for s in self.use_case.specialists],
        )

        initial: RunState = {
            "run_id": thread_id,
            "subject_id": subject_id,
            "subject": subject or {},
            # None, not [] — an empty list would be appended to whatever a
            # previous run on this thread left behind.
            "findings": None,  # type: ignore[typeddict-item]
            "recommendation": None,  # type: ignore[typeddict-item]
            "decision": None,  # type: ignore[typeddict-item]
        }

        try:
            async for event in self._pump(
                self.graph.astream(
                    initial, config=config, stream_mode=["custom", "updates"]
                ),
                sink,
            ):
                yield event
        except HardStop as stop:
            yield sink.emit(
                EventType.RUN_FAILED, reason="hard_stop", limit=stop.limit,
                detail=stop.detail, spend=ledger.snapshot(),
            )
        except Exception as exc:
            yield sink.emit(
                EventType.RUN_FAILED,
                reason="exception",
                detail=f"{type(exc).__name__}: {exc}",
                spend=ledger.snapshot(),
            )

    async def submit_decision(
        self, thread_id: str, decision: dict[str, Any], *, start_seq: int = 0
    ) -> AsyncIterator[OrchestrationEvent]:
        """Resume a paused run with the human's decision, and record it.

        `start_seq` continues the numbering of the run being resumed, so the
        captured trace stays in one ordered sequence across the pause.
        """
        sink = EventSink(thread_id, start_seq=start_seq)
        config = {
            "configurable": {
                "thread_id": thread_id,
                "ledger": SpendLedger(self.limits),
            }
        }
        async for event in self._pump(
            self.graph.astream(
                Command(resume=decision), config=config, stream_mode=["custom", "updates"]
            ),
            sink,
        ):
            yield event
        yield sink.emit(EventType.RUN_COMPLETED, thread_id=thread_id)

    async def state(self, thread_id: str) -> dict[str, Any]:
        """Current checkpointed state — what a resumed process picks back up."""
        snapshot = await self.graph.aget_state(
            {"configurable": {"thread_id": thread_id}}
        )
        return {
            "values": snapshot.values,
            "next": list(snapshot.next),
            "awaiting_human": "human_gate" in snapshot.next,
        }
