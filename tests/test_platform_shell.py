"""Proves the platform shell before any agent exists (BUILD_SPEC step 2).

Every non-negotiable in §10 that the shell is responsible for is asserted here
with stub specialists and no LLM key: parallel fan-out, typed contracts, star
topology, preserved dissent, durable checkpointing across a process boundary,
a real human gate, and hard stop conditions.

The stub use case deliberately uses a DIFFERENT lean vocabulary from launch
readiness (keep/drop/defer). If the shell can run a use case whose leans it has
never heard of, the platform/usecase separation is real rather than claimed.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum

import pytest

from elfagent.platform import (
    ActorKind,
    AgentSpec,
    Finding,
    GateType,
    HardStop,
    Orchestrator,
    Recommendation,
    RunLimits,
    SegmentAssessment,
    SpecialistContext,
    ToolSpec,
    UseCase,
    sqlite_checkpointer,
)
from elfagent.platform.events import EventType

STUB_DELAY = 0.25


class Colour(str, Enum):
    """A lean vocabulary the platform has never heard of."""

    KEEP = "keep"
    DROP = "drop"
    DEFER = "defer"


ColourFinding = Finding[Colour]
ColourRecommendation = Recommendation[Colour]

# What judgment actually received, so the typed hand-off can be asserted from
# the inside rather than inferred from what ended up in state.
JUDGMENT_SAW: dict = {}


def _stub(name: str, lean: Colour, *, delay: float = STUB_DELAY):
    async def run(ctx: SpecialistContext) -> ColourFinding:
        ctx.emit(
            type=EventType.AGENT_TOOL_CALL.value,
            agent=name,
            actor_kind="tool",
            tool=f"get_{name}_facts",
            result="ok",
        )
        await asyncio.sleep(delay)
        return ColourFinding(
            agent=name,
            lean=lean,
            confidence=0.8,
            rationale=f"{name} reasoned to {lean.value}",
            evidence=[f"{name}: one fact"],
            segments=[
                SegmentAssessment(
                    segment="alpha",
                    ready=lean is Colour.KEEP,
                    gate_type=None if lean is Colour.KEEP else GateType.HARD,
                    detail="stub",
                )
            ],
            semantic_version="stub@v1",
        )

    return run


async def _judgment(ctx: SpecialistContext, findings: list[ColourFinding]):
    JUDGMENT_SAW["types"] = [type(f) for f in findings]
    JUDGMENT_SAW["leans"] = [f.lean for f in findings]
    leans = {f.lean for f in findings}
    dissent = (
        [
            f"{f.agent} argued {f.lean.value}"
            for f in findings
            if f.lean is not Colour.KEEP
        ]
        if len(leans) > 1
        else []
    )
    return ColourRecommendation(
        subject_id=ctx.subject_id,
        recommended_action=Colour.KEEP,
        per_segment_action=[SegmentAssessment(segment="alpha", ready=True, detail="ok")],
        confidence=0.6,
        reconciliation="stub reconciliation",
        dissent=dissent,
        findings=findings,
    )


def _agent(name: str, lean: Colour, tools: tuple[str, ...] = ()) -> AgentSpec:
    return AgentSpec(
        name, "q?", "requires judgment", _stub(name, lean), tools,
        finding_model=ColourFinding,
    )


def _use_case(specialists=None, judgment=None) -> UseCase:
    specialists = specialists or (
        _agent("alpha", Colour.KEEP, ("t1",)),
        _agent("bravo", Colour.DROP, ("t2",)),
        _agent("charlie", Colour.KEEP),
        _agent("delta", Colour.DEFER),
    )
    return UseCase(
        key="stub",
        title="Stub",
        subject_label="thing",
        signal=lambda: [{"id": "S-1"}],
        specialists=specialists,
        judgment=judgment or _judgment,
        recommendation_model=ColourRecommendation,
        tools=(ToolSpec("t1", "deterministic lookup", "same inputs, same answer"),),
        semantic_version="stub@v1",
    )


async def _drain(orch, subject_id="S-1", thread_id="t-1"):
    return [e async for e in orch.astream(subject_id, thread_id=thread_id)]


# ---------------------------------------------------------------- fan-out


async def test_specialists_run_in_parallel_not_in_sequence(tmp_path):
    """Four 0.25s specialists must take ~0.25s, not ~1.0s."""
    async with sqlite_checkpointer(str(tmp_path / "cp.sqlite")) as cp:
        orch = Orchestrator(_use_case(), checkpointer=cp)
        start = time.monotonic()
        events = await _drain(orch)
        elapsed = time.monotonic() - start

    sequential = 4 * STUB_DELAY
    assert elapsed < sequential * 0.6, (
        f"fan-out took {elapsed:.2f}s; sequential would be {sequential:.2f}s. "
        "The specialists are not running concurrently."
    )
    returned = [e for e in events if e.type is EventType.AGENT_RETURNED]
    assert {e.agent for e in returned} == {"alpha", "bravo", "charlie", "delta"}


async def test_judgment_receives_validated_contracts_not_dicts(tmp_path):
    """State is JSON so it survives a checkpoint; the contract is re-established
    at the boundary, so judgment never reasons over loose dicts."""
    JUDGMENT_SAW.clear()
    async with sqlite_checkpointer(str(tmp_path / "cp.sqlite")) as cp:
        orch = Orchestrator(_use_case(), checkpointer=cp)
        await _drain(orch)
        state = await orch.state("t-1")

    assert JUDGMENT_SAW["types"] == [ColourFinding] * 4
    assert all(isinstance(l, Colour) for l in JUDGMENT_SAW["leans"])

    raw = state["values"]["findings"]
    assert len(raw) == 4
    assert all(isinstance(f, dict) for f in raw), "state must stay serialisable"


async def test_specialist_returning_loose_data_is_rejected(tmp_path):
    """No prose, no bare dicts. The format-mismatch failure mode dies here."""

    async def liar(ctx: SpecialistContext):
        return {"agent": "liar", "lean": "keep", "confidence": 0.5}

    spec = AgentSpec("liar", "q?", "why", liar, finding_model=ColourFinding)
    async with sqlite_checkpointer(":memory:") as cp:
        orch = Orchestrator(_use_case(specialists=(spec,)), checkpointer=cp)
        events = await _drain(orch, thread_id="t-liar")

    failed = [e for e in events if e.type is EventType.RUN_FAILED]
    assert failed and "contract requires" in str(failed[-1].payload)


async def test_re_running_a_thread_replaces_findings_rather_than_appending(tmp_path):
    """"Run again" must mean run again, not run more.

    The fan-in reducer appends, which is right within one run and wrong across
    two — a second run on the same thread would hand judgment eight findings
    from four specialists, with nothing on screen looking obviously broken.
    """
    db = str(tmp_path / "rerun.sqlite")
    async with sqlite_checkpointer(db) as cp:
        orch = Orchestrator(_use_case(), checkpointer=cp)
        await _drain(orch, thread_id="t-rerun")
        first = await orch.state("t-rerun")
        assert len(first["values"]["findings"]) == 4

        await _drain(orch, thread_id="t-rerun")
        second = await orch.state("t-rerun")

    assert len(second["values"]["findings"]) == 4, (
        f"re-running appended instead of replacing: "
        f"{len(second['values']['findings'])} findings from 4 specialists"
    )


async def test_specialists_are_never_handed_each_others_findings():
    """Star topology, enforced by the shape of the context object."""
    seen: dict = {}

    async def snoop(ctx: SpecialistContext):
        seen["fields"] = set(vars(ctx))
        return await _stub("snoop", Colour.KEEP, delay=0)(ctx)

    uc = _use_case(
        specialists=(
            AgentSpec("snoop", "q?", "why", snoop, finding_model=ColourFinding),
        ),
        judgment=_judgment,
    )
    async with sqlite_checkpointer(":memory:") as cp:
        await _drain(Orchestrator(uc, checkpointer=cp), thread_id="t-snoop")

    assert "findings" not in seen["fields"]
    assert "recommendation" not in seen["fields"]
    assert seen["fields"] == {
        "subject_id",
        "subject",
        "ledger",
        "semantic_version",
        "emit",
    }


# ---------------------------------------------------------------- dissent


def test_conflicting_leans_with_empty_dissent_is_rejected():
    """False consensus must fail loudly, in code, not be trusted to a prompt."""
    findings = [
        ColourFinding(
            agent=n, lean=l, confidence=0.8, rationale="r", semantic_version="stub@v1"
        )
        for n, l in [("a", Colour.KEEP), ("b", Colour.DROP)]
    ]
    with pytest.raises(ValueError, match="dissent must not be empty"):
        Recommendation[Colour](
            subject_id="S-1",
            recommended_action=Colour.KEEP,
            confidence=0.6,
            reconciliation="collapsed the minority view",
            dissent=[],
            findings=findings,
        )


def test_unanimous_leans_may_have_empty_dissent():
    findings = [
        ColourFinding(
            agent=n, lean=Colour.KEEP, confidence=0.8, rationale="r",
            semantic_version="stub@v1",
        )
        for n in ("a", "b")
    ]
    rec = Recommendation[Colour](
        subject_id="S-1",
        recommended_action=Colour.KEEP,
        confidence=0.9,
        reconciliation="unanimous",
        findings=findings,
    )
    assert rec.dissent == []
    assert rec.is_contested is False


async def test_dissent_survives_to_the_recommendation(tmp_path):
    async with sqlite_checkpointer(str(tmp_path / "cp.sqlite")) as cp:
        orch = Orchestrator(_use_case(), checkpointer=cp)
        events = await _drain(orch)

    judged = next(e for e in events if e.type is EventType.JUDGMENT_RETURNED)
    assert judged.payload["recommendation"]["dissent"], (
        "specialists disagreed but the recommendation carried no dissent"
    )


# ------------------------------------------------------------- human gate


async def test_graph_pauses_at_the_human_gate(tmp_path):
    async with sqlite_checkpointer(str(tmp_path / "cp.sqlite")) as cp:
        orch = Orchestrator(_use_case(), checkpointer=cp)
        events = await _drain(orch)
        state = await orch.state("t-1")

    assert any(e.type is EventType.AWAITING_HUMAN for e in events)
    assert state["awaiting_human"] is True
    assert state["values"].get("decision") is None, "nothing may write the decision"


async def test_durable_checkpoint_survives_a_new_process(tmp_path):
    """The kill-and-resume demo, in miniature.

    The run is started by one Orchestrator over one connection, then abandoned.
    A completely separate Orchestrator opens the same file and resumes — which
    is what happens when the process is killed and restarted. An in-memory
    saver would pass no part of this.
    """
    db = str(tmp_path / "durable.sqlite")

    async with sqlite_checkpointer(db) as cp:
        await _drain(Orchestrator(_use_case(), checkpointer=cp), thread_id="t-kill")

    # ---- process boundary: new checkpointer, new orchestrator, same file ----

    async with sqlite_checkpointer(db) as cp:
        orch = Orchestrator(_use_case(), checkpointer=cp)
        before = await orch.state("t-kill")
        assert before["awaiting_human"] is True
        assert len(before["values"]["findings"]) == 4, "checkpoint lost the findings"

        decision = {
            "decided_action": "keep",
            "decided_by": "Director of Commercialization",
            "followed_recommendation": True,
        }
        resumed = [e async for e in orch.submit_decision("t-kill", decision)]
        after = await orch.state("t-kill")

    assert any(e.type is EventType.DECISION_RECORDED for e in resumed)
    assert after["values"]["decision"] == decision
    assert after["awaiting_human"] is False


# ------------------------------------------------------------- hard stops


async def test_spend_cap_stops_the_run(tmp_path):
    async def greedy(ctx: SpecialistContext):
        ctx.ledger.begin_step("greedy")
        ctx.ledger.charge("greedy", input_tokens=1000, output_tokens=1000, usd=99.0)
        raise AssertionError("charge() should have raised before returning")

    uc = _use_case(
        specialists=(
            AgentSpec("greedy", "q?", "why", greedy, finding_model=ColourFinding),
        )
    )
    async with sqlite_checkpointer(str(tmp_path / "cp.sqlite")) as cp:
        orch = Orchestrator(uc, checkpointer=cp, limits=RunLimits(max_usd_per_run=0.50))
        events = await _drain(orch, thread_id="t-spend")

    failed = [e for e in events if e.type is EventType.RUN_FAILED]
    assert failed, "run should have failed on the spend cap"
    assert "max_usd_per_run" in str(failed[-1].payload)


def test_step_cap_is_enforced_in_code():
    from elfagent.platform.limits import SpendLedger

    ledger = SpendLedger(RunLimits(max_steps_per_agent=3))
    for _ in range(3):
        ledger.begin_step("a")
    with pytest.raises(HardStop) as exc:
        ledger.begin_step("a")
    assert exc.value.limit == "max_steps_per_agent"


def test_ledger_is_shared_across_agents_not_per_agent():
    """Four agents must not each stay under the cap while blowing the total."""
    from elfagent.platform.limits import SpendLedger

    ledger = SpendLedger(RunLimits(max_usd_per_run=1.00))
    for agent in ("a", "b", "c"):
        ledger.charge(agent, input_tokens=0, output_tokens=0, usd=0.30)
    with pytest.raises(HardStop) as exc:
        ledger.charge("d", input_tokens=0, output_tokens=0, usd=0.30)
    assert exc.value.limit == "max_usd_per_run"


# ---------------------------------------------------------------- registry


def test_registry_classifies_tools_and_agents_structurally():
    """Credibility signal #1 is data in the registry, not a line in a script."""
    anatomy = _use_case().anatomy()

    assert [a["kind"] for a in anatomy["agents"]] == [ActorKind.AGENT.value] * 4
    assert all(a["why_agent"] for a in anatomy["agents"])
    assert [t["kind"] for t in anatomy["tools"]] == [ActorKind.TOOL.value]
    assert all(t["why_tool"] for t in anatomy["tools"])


def test_use_case_rejects_duplicate_specialists():
    dup = (_agent("same", Colour.KEEP), _agent("same", Colour.DROP))
    with pytest.raises(ValueError, match="duplicate specialist"):
        _use_case(specialists=dup)


def test_use_case_rejects_a_specialist_with_no_declared_contract():
    """Typed contracts are non-negotiable, so this fails at registration."""
    naked = AgentSpec("naked", "q?", "why", _stub("naked", Colour.KEEP))
    with pytest.raises(ValueError, match="declare no finding_model"):
        _use_case(specialists=(naked,))
