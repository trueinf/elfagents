"""The Regulatory agent end-to-end, driven by a scripted model (§12 step 3).

No API key and no network. The model's replies are scripted, but everything
else is real: the tools hit the actual warehouse, the contract really validates,
the ledger really counts, and the graph really runs and pauses.

What this proves is the plumbing — that the agent asks its tools, receives true
facts, and can only return a valid contract. What it deliberately does NOT
prove is that a real model reasons its way to the right lean from those facts;
that needs a key and is the remaining half of step 3.
"""

from __future__ import annotations

import pytest

from elfagent.platform import Orchestrator, RunLimits, UseCase, sqlite_checkpointer
from elfagent.platform.agent_loop import ContractNotSubmitted
from elfagent.platform.events import EventType
from elfagent.platform.llm import ModelRefused, ModelReply, ScriptedClient, ToolCall
from elfagent.usecases.launch_readiness import signal
from elfagent.usecases.launch_readiness.contracts import (
    LaunchRecommendation,
    Lean,
    MarketReadiness,
    RegulatoryFinding,
)
from elfagent.usecases.launch_readiness.usecase import build_use_case

MARKETS = ["US", "DE", "UK"]


@pytest.fixture
def launch() -> dict:
    return next(q for q in signal.queue() if q["launch_id"] == "LAUNCH-1001")


def _call(name: str, **args) -> ToolCall:
    return ToolCall(id=f"toolu_{name}_{args.get('market', '')}", name=name, input=args)


def _reply(*calls: ToolCall, text: str = "") -> ModelReply:
    return ModelReply(
        text=text,
        tool_calls=list(calls),
        stop_reason="tool_use" if calls else "end_turn",
        input_tokens=1200,
        output_tokens=180,
        usd=0.0105,
        raw_content=[{"type": "text", "text": text or "..."}],
    )


def _lookups() -> ModelReply:
    """One turn asking every lookup for every market — six calls in parallel."""
    return _reply(
        *[_call("get_ingredient_restrictions", market=m) for m in MARKETS],
        *[_call("get_notification_status", market=m) for m in MARKETS],
    )


GOOD_SUBMISSION = {
    "lean": "partial",
    "confidence": 0.8,
    "rationale": "Germany is blocked on this formula; the US and UK are clear.",
    "evidence": [
        "DE: Ascorbic Acid 22% exceeds the restricted limit of 20%",
        "DE: notification in_progress on CPNP",
        "UK: 22% is within the 25% limit; SCPN filing complete",
    ],
    "per_market": [
        {"market": "US", "ready": True, "gate_type": None, "detail": "No gate."},
        {
            "market": "DE",
            "ready": False,
            "gate_type": "hard",
            "detail": "Concentration exceeds the limit and notification is incomplete.",
        },
        {"market": "UK", "ready": True, "gate_type": None, "detail": "Clear."},
    ],
    "hard_gate_markets": ["DE"],
}


def _submit(**overrides) -> ModelReply:
    return _reply(
        _call("submit_regulatory_finding", **{**GOOD_SUBMISSION, **overrides})
    )


async def _passthrough_judgment(ctx, findings):
    """Judgment is exercised in its own tests; here it stays out of the way."""
    lone = findings[0]
    return LaunchRecommendation(
        subject_id=ctx.subject_id,
        recommended_action=lone.lean,
        per_market_action=[
            MarketReadiness(
                market=s.segment, ready=s.ready, gate_type=s.gate_type, detail=s.detail
            )
            for s in lone.segments
        ],
        confidence=lone.confidence,
        reconciliation="single specialist under test",
        findings=list(findings),
    )


def _regulatory_only(client) -> UseCase:
    """The Regulatory agent alone, so its tests do not depend on its peers."""
    full = build_use_case(client)
    return UseCase(
        key=full.key,
        title=full.title,
        subject_label=full.subject_label,
        signal=full.signal,
        specialists=tuple(s for s in full.specialists if s.name == "regulatory"),
        judgment=_passthrough_judgment,
        recommendation_model=full.recommendation_model,
        tools=full.tools,
        semantic_version=full.semantic_version,
    )


async def _run(client, launch, *, limits=None):
    use_case = _regulatory_only(client)
    ctx_limits = limits or RunLimits(max_steps_per_agent=4)
    async with sqlite_checkpointer(":memory:") as cp:
        orch = Orchestrator(use_case, checkpointer=cp, limits=ctx_limits)
        events = [
            e
            async for e in orch.astream(
                launch["launch_id"], subject=launch, thread_id="t-reg"
            )
        ]
        state = await orch.state("t-reg")
    return events, state


# ------------------------------------------------------------- happy path


async def test_agent_returns_a_validated_finding(launch):
    client = ScriptedClient([_lookups(), _submit()])
    events, state = await _run(client, launch)

    returned = [e for e in events if e.type is EventType.AGENT_RETURNED]
    assert len(returned) == 1
    payload = returned[0].payload["finding"]

    assert payload["agent"] == "regulatory"
    assert payload["lean"] == "partial"
    assert payload["hard_gate_markets"] == ["DE"]
    assert [m["market"] for m in payload["per_market"]] == MARKETS
    assert payload["per_market"][1]["gate_type"] == "hard"

    # Re-validates against the declared contract after the state round-trip.
    finding = RegulatoryFinding.model_validate(state["values"]["findings"][0])
    assert finding.lean is Lean.PARTIAL
    assert finding.hard_gated_segments() == ["DE"]


async def test_agent_and_version_are_supplied_by_us_not_the_model(launch):
    """Provenance fields aren't in the schema, so the model cannot assert them."""
    schema = None
    client = ScriptedClient([_lookups(), _submit()])
    events, _ = await _run(client, launch)

    payload = next(
        e for e in events if e.type is EventType.AGENT_RETURNED
    ).payload["finding"]
    assert payload["semantic_version"] == "launch_ready@v3"

    from elfagent.usecases.launch_readiness.specialists.regulatory import SUBMIT_TOOL

    schema = SUBMIT_TOOL["input_schema"]["properties"]
    assert "agent" not in schema and "semantic_version" not in schema


async def test_the_model_is_handed_real_warehouse_facts(launch):
    """The agent reasons over the seed data, not over anything we narrated."""
    client = ScriptedClient([_lookups(), _submit()])
    await _run(client, launch)

    # The second call carries the tool results from the first.
    results = client.calls[1]["messages"][-1]["content"]
    blob = " ".join(r["content"] for r in results)

    assert "22.0" in blob and "20.0" in blob, "the DE exceedance must reach the model"
    assert "annex_iii_restricted" in blob, "restricted must be distinguishable"
    assert "CPNP" in blob and "in_progress" in blob
    assert "SCPN" in blob and "complete" in blob


async def test_every_tool_call_is_traced_as_a_tool(launch):
    client = ScriptedClient([_lookups(), _submit()])
    events, _ = await _run(client, launch)

    tool_events = [e for e in events if e.type is EventType.AGENT_TOOL_CALL]
    assert len(tool_events) == 6
    assert {e.actor_kind for e in tool_events} == {"tool"}
    assert all(e.agent == "regulatory" for e in tool_events)


async def test_spend_is_charged_to_the_shared_ledger(launch):
    client = ScriptedClient([_lookups(), _submit()])
    _, state = await _run(client, launch)

    spend = state["values"]["spend"]
    assert spend["by_agent"]["regulatory"]["steps"] == 2
    assert spend["total_tokens"] == 2 * (1200 + 180)
    assert spend["total_usd"] == pytest.approx(0.021)


# ---------------------------------------------------- the contract holds


async def test_a_malformed_submission_is_rejected_and_corrected(launch):
    """Confidence of 1.5 is out of contract. The model gets told, and fixes it."""
    client = ScriptedClient(
        [_lookups(), _submit(confidence=1.5), _submit(confidence=0.7)]
    )
    events, _ = await _run(client, launch)

    rejection = [
        e
        for e in events
        if e.type is EventType.AGENT_TOOL_CALL
        and e.payload.get("summary") == "rejected by contract"
    ]
    assert len(rejection) == 1
    assert "less_than_equal" in str(rejection[0].payload["error"])

    # The correction was fed back as a tool error, not silently dropped.
    correction = client.calls[2]["messages"][-1]["content"][0]
    assert correction["is_error"] is True
    assert "Rejected by the contract" in correction["content"]

    finding = next(
        e for e in events if e.type is EventType.AGENT_RETURNED
    ).payload["finding"]
    assert finding["confidence"] == 0.7


async def test_a_prose_answer_is_refused_not_parsed(launch):
    """No prose crosses the boundary — the model is told to use the tool."""
    client = ScriptedClient([_reply(text="Germany looks blocked to me."), _submit()])
    await _run(client, launch)

    nudge = client.calls[1]["messages"][-1]
    assert nudge["role"] == "user"
    assert "Respond only by calling a tool" in nudge["content"]


async def test_the_submit_tool_is_forced_on_the_final_step(launch):
    client = ScriptedClient([_lookups(), _lookups(), _submit()])
    await _run(client, launch, limits=RunLimits(max_steps_per_agent=3))

    assert client.calls[0]["tool_choice"] is None
    assert client.calls[1]["tool_choice"] is None
    assert client.calls[2]["tool_choice"] == {
        "type": "tool",
        "name": "submit_regulatory_finding",
    }


async def test_a_run_that_never_submits_fails_loudly(launch):
    client = ScriptedClient([_lookups(), _lookups()])
    events, _ = await _run(client, launch, limits=RunLimits(max_steps_per_agent=2))

    failed = [e for e in events if e.type is EventType.RUN_FAILED]
    assert failed, "a specialist that never submits must fail the run"
    assert "without submitting" in str(failed[-1].payload["detail"])


async def test_an_unknown_tool_name_comes_back_as_an_error_not_a_crash(launch):
    client = ScriptedClient([_reply(_call("get_the_answer", market="DE")), _submit()])
    await _run(client, launch)

    result = client.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    assert "get_the_answer" in result["content"]


# ------------------------------------------------------------ human gate


async def test_the_graph_still_pauses_for_the_human(launch):
    client = ScriptedClient([_lookups(), _submit()])
    events, state = await _run(client, launch)

    assert any(e.type is EventType.AWAITING_HUMAN for e in events)
    assert state["awaiting_human"] is True
    assert state["values"].get("decision") is None

    recommendation = state["values"]["recommendation"]
    assert recommendation["recommended_action"] == "partial"
    assert [m["market"] for m in recommendation["per_market_action"]] == MARKETS


# --------------------------------------------------------------- refusal


async def test_a_refusal_is_raised_not_read_as_content():
    """Opus 5 returns HTTP 200 on a refusal; content[0] would be nonsense."""
    from elfagent.platform.llm import AnthropicClient

    class _Refusing:
        class beta:
            class messages:
                @staticmethod
                async def create(**_):
                    class Details:
                        category = "cyber"

                    class Response:
                        stop_reason = "refusal"
                        stop_details = Details()
                        content: list = []
                        usage = type("U", (), {"input_tokens": 5, "output_tokens": 0})()

                    return Response()

    client = AnthropicClient(client=_Refusing())
    with pytest.raises(ModelRefused, match="cyber"):
        await client.complete(system="s", messages=[], tools=[])
