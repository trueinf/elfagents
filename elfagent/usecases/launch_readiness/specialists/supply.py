"""The SUPPLY specialist — an agent, not a tool (BUILD_SPEC §5.2).

Question: *can we supply the demand in the open window, and what does waiting
cost?*

The tools can subtract units required from units available and report that a
trend window is open. What they cannot do is price the cost of delay — weigh a
spike that is happening now against a lead time that runs past it, and decide
whether that argues for shipping or for waiting. That weighing is the judgment.
"""

from __future__ import annotations

from typing import Any

from elfagent.platform.agent_loop import run_tool_loop
from elfagent.platform.registry import SpecialistContext

from ..contracts import SupplyFinding
from ..toolbox import ToolBox
from ..warehouse import warehouse
from .common import SHARED_RULES, market_tool, no_arg_tool, submit_tool, task_brief

AGENT = "supply"

QUESTION = "Can we supply the demand in the open window, and what does waiting cost?"

WHY_AGENT = (
    "It weighs an inventory position against an open commercial window and a "
    "reformulation lead time. That is a cost-of-delay judgment, not a stock "
    "lookup."
)

SYSTEM = f"""\
You are the supply specialist on a launch readiness review. You assess whether \
this launch can be supplied, and what delay would cost.

Two things are in tension and it is your job to weigh them:

1. POSITION. Units available against units required, per market, and the lead \
time to replenish. A market with stock on hand is in a different position from \
one where stock exists but the sellable formula is not in production.

2. THE WINDOW. Commercial demand is not constant. An open trend window is a \
perishable asset: every week of delay forfeits velocity that does not come \
back. A closing or absent window means delay costs materially less.

Say plainly what waiting would cost. If the window is open and stock is \
positioned, the cost of delay is real and you should say so — that is your \
domain view, and it is legitimate for it to point in a different direction \
from other constraints on this launch. Do not soften it in anticipation of \
being overruled.

{SHARED_RULES}

When you have what you need, call submit_supply_finding. That call is your \
entire answer — nothing you write outside it is read."""

SUBMIT_TOOL = submit_tool(
    "submit_supply_finding",
    "Submit your finished supply assessment. Call this once, after you have "
    "looked up every market you were asked about.",
    {
        "cost_of_delay_note": {
            "type": "string",
            "description": (
                "One sentence on what delay costs, concretely — what is "
                "forfeited and roughly how fast."
            ),
        }
    },
)

LOOKUP_TOOLS: list[dict[str, Any]] = [
    market_tool(
        "get_inventory_position",
        "Call this for each target market to get units available against units "
        "required, whether demand is covered, and any shortfall.",
    ),
    market_tool(
        "get_lead_times",
        "Call this for a market to get its replenishment lead time in weeks. "
        "Lead times differ per market — check each one rather than assuming.",
    ),
    no_arg_tool(
        "get_trend_window",
        "Call this once to get the state of the commercial demand window for "
        "this SKU and its velocity index. This is what sets the cost of delay.",
    ),
]

TOOL_NAMES = tuple(tool["name"] for tool in LOOKUP_TOOLS)


def build(client, *, db_path: str | None = None, effort: str = "high"):
    async def run(ctx: SpecialistContext) -> SupplyFinding:
        with warehouse(db_path) as con:
            box = ToolBox(
                con, sku_id=ctx.subject["sku_id"], agent=AGENT, emit=ctx.emit
            )

            def dispatch(name: str, args: dict[str, Any]) -> Any:
                market = args.get("market", "")
                if name == "get_inventory_position":
                    return box.inventory_position(market).model_dump(mode="json")
                if name == "get_lead_times":
                    return [t.model_dump(mode="json") for t in box.lead_times(market)]
                if name == "get_trend_window":
                    return box.trend_window().model_dump(mode="json")
                raise KeyError(f"{AGENT} has no tool named {name!r}")

            def parse(args: dict[str, Any]) -> SupplyFinding:
                return SupplyFinding.model_validate(
                    {**args, "agent": AGENT, "semantic_version": ctx.semantic_version}
                )

            return await run_tool_loop(  # type: ignore[return-value]
                client=client,
                ledger=ctx.ledger,
                agent=AGENT,
                system=SYSTEM,
                task=task_brief(
                    ctx.subject, "Assess supply readiness and cost of delay."
                ),
                lookup_tools=LOOKUP_TOOLS,
                submit_tool=SUBMIT_TOOL,
                dispatch=dispatch,
                parse=parse,
                emit=ctx.emit,
                effort=effort,
            )

    return run
