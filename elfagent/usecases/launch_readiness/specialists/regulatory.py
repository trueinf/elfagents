"""The REGULATORY specialist — an agent, not a tool (BUILD_SPEC §5.1).

The question the orchestrator asks it: *is this SKU legally clear to ship in
each target market, and if not, is the gate hard or conditional?*

That question has no deterministic answer. The tools can report that a formula
is at 22% and that the market's limit is 20% — arithmetic. What they cannot do
is decide whether that exceedance is fatal or fixable, whether an in-progress
notification is a blocker or a scheduling detail, or whether a market that
fails on one filing is affected by another market's separate filing. Those are
judgments about severity and path, and they are why this is an agent.
"""

from __future__ import annotations

from typing import Any

from elfagent.platform.agent_loop import run_tool_loop
from elfagent.platform.registry import SpecialistContext

from ..contracts import Lean, RegulatoryFinding
from ..toolbox import ToolBox
from ..warehouse import warehouse

AGENT = "regulatory"

QUESTION = (
    "Is this SKU legally clear to ship in each target market, and where it is "
    "not, is the gate a hard block or a conditional one?"
)

WHY_AGENT = (
    "It must interpret the difference between an outright prohibition and a "
    "conditional restriction that has been exceeded, and weigh notification "
    "state against a ship date. That is a judgment about severity and path, "
    "not a flag lookup."
)

SYSTEM = """\
You are the regulatory specialist on a launch readiness review. You assess one \
launch and decide, per market, whether it is legally clear to ship.

Your remit is legal clearance only. You do not assess inventory, artwork, \
retailer setup, or commercial timing, and you never see the other specialists' \
conclusions — reach your own from the data you retrieve.

Two gates matter, and they are independent:

1. INGREDIENTS. A prohibited substance is banned at any concentration and no \
reformulation of concentration helps — that market is closed to this formula. \
A restricted substance is permitted up to a limit; exceeding it blocks THIS \
formula but a compliant reformulation would clear the market. Treat those two \
as different findings, because they imply different paths and different dates.

2. PRE-MARKET NOTIFICATION. Some markets require a filing before goods may be \
placed on the market. Different markets file on different portals, and one \
market's filing says nothing about another's. A filing that is in progress is \
not a filing that is complete.

A tool result of "no_record" means nothing is on file for that market. It does \
NOT mean the market is permitted. Say so explicitly when you rely on it.

Reason only from what the tools return. Do not supply limits, statuses, or \
substances from your own knowledge — if you need a fact, look it up.

Keep your rationale to one tight paragraph. State the finding and the reason \
for it; leave out restatements of the data, caveats, and commentary on your own \
process. Assess exactly the markets you are given, and do not extend the \
analysis to markets, SKUs, or questions outside the launch as briefed.

When you have what you need, call submit_regulatory_finding. That call is your \
entire answer — nothing you write outside it is read."""


# Numerical bounds (confidence 0..1) are deliberately absent from this schema:
# strict tool schemas do not support them. The contract enforces the range on
# our side, and a violation comes back to the model as a correction.
_MARKET_ITEM = {
    "type": "object",
    "properties": {
        "market": {"type": "string", "description": "Market code, e.g. DE."},
        "ready": {
            "anyOf": [{"type": "boolean"}, {"type": "null"}],
            "description": (
                "true if legally clear, false if blocked, null if genuinely "
                "conditional or ambiguous. Use null rather than rounding."
            ),
        },
        "gate_type": {
            "anyOf": [
                {"type": "string", "enum": ["hard", "conditional"]},
                {"type": "null"},
            ],
            "description": (
                "'hard' for a legal block that cannot be traded against a "
                "schedule preference, 'conditional' where a path through it "
                "exists, null when the market is clear."
            ),
        },
        "detail": {"type": "string", "description": "One sentence on why."},
    },
    "required": ["market", "ready", "gate_type", "detail"],
    "additionalProperties": False,
}

SUBMIT_TOOL: dict[str, Any] = {
    "name": "submit_regulatory_finding",
    "description": (
        "Submit your finished regulatory assessment. Call this once, after you "
        "have looked up every market you were asked about."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "lean": {
                "type": "string",
                "enum": [lean.value for lean in Lean],
                "description": (
                    "Your overall recommendation for this launch: go if every "
                    "market is clear, slip if the launch should wait, partial "
                    "if some markets are clear and others are not, hold if it "
                    "should not proceed at all."
                ),
            },
            "confidence": {
                "type": "number",
                "description": "Between 0 and 1.",
            },
            "rationale": {"type": "string", "description": "One paragraph."},
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "The concrete facts the lean rests on, each traceable to a "
                    "tool result."
                ),
            },
            "per_market": {"type": "array", "items": _MARKET_ITEM},
            "hard_gate_markets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Markets carrying a hard legal block.",
            },
        },
        "required": [
            "lean",
            "confidence",
            "rationale",
            "evidence",
            "per_market",
            "hard_gate_markets",
        ],
        "additionalProperties": False,
    },
}

LOOKUP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_ingredient_restrictions",
        "description": (
            "Call this for each target market to get the formula's ingredients "
            "with the restriction that applies in that market and whether the "
            "concentration exceeds it. Returns annex_status, max_limit_pct and "
            "exceeds_limit per ingredient."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Market code."}
            },
            "required": ["market"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_notification_status",
        "description": (
            "Call this for each target market to get the pre-market "
            "notification portal that applies there and the state of the "
            "filing. Markets file separately; check each one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Market code."}
            },
            "required": ["market"],
            "additionalProperties": False,
        },
    },
]

TOOL_NAMES = tuple(tool["name"] for tool in LOOKUP_TOOLS)


def _task(subject: dict[str, Any]) -> str:
    return (
        "Assess legal clearance for this launch.\n\n"
        f"launch_id: {subject.get('launch_id')}\n"
        f"sku: {subject.get('sku_id')} — {subject.get('sku_name')}\n"
        f"brand: {subject.get('brand')}\n"
        f"target markets: {', '.join(subject.get('target_markets', []))}\n"
        f"first ship date: {subject.get('first_ship_date')} "
        f"(T-minus {subject.get('countdown_weeks')} weeks)"
    )


def build(client, *, db_path: str | None = None, effort: str = "high"):
    """Return the specialist's run function, bound to a model client.

    The warehouse handle is held here rather than passed through graph state:
    state crosses a serialisation boundary at every checkpoint, and a live
    connection cannot survive that. Each run opens its own read-only
    connection, so four specialists executing in parallel are not sharing one
    handle.
    """

    async def run(ctx: SpecialistContext) -> RegulatoryFinding:
        with warehouse(db_path) as con:
            box = ToolBox(
                con, sku_id=ctx.subject["sku_id"], agent=AGENT, emit=ctx.emit
            )

            def dispatch(name: str, args: dict[str, Any]) -> Any:
                market = args.get("market", "")
                if name == "get_ingredient_restrictions":
                    return [
                        r.model_dump(mode="json")
                        for r in box.ingredient_restrictions(market)
                    ]
                if name == "get_notification_status":
                    return box.notification_status(market).model_dump(mode="json")
                raise KeyError(f"{AGENT} has no tool named {name!r}")

            def parse(args: dict[str, Any]) -> RegulatoryFinding:
                # `agent` and `semantic_version` are facts we own, not the
                # model's to assert — so they are never in the schema it fills.
                return RegulatoryFinding.model_validate(
                    {**args, "agent": AGENT, "semantic_version": ctx.semantic_version}
                )

            finding = await run_tool_loop(
                client=client,
                ledger=ctx.ledger,
                agent=AGENT,
                system=SYSTEM,
                task=_task(ctx.subject),
                lookup_tools=LOOKUP_TOOLS,
                submit_tool=SUBMIT_TOOL,
                dispatch=dispatch,
                parse=parse,
                emit=ctx.emit,
                effort=effort,
            )
            return finding  # type: ignore[return-value]

    return run
