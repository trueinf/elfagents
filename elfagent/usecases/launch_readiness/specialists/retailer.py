"""The RETAILER specialist — an agent, not a tool (BUILD_SPEC §5.3).

Question: *which markets and channels are commercially ready to receive this
now, and is a partial launch viable?*

The tools can count how many channels have completed setup and name the
accounts still waiting on a compliance dossier. What they cannot do is decide
whether launching only the ready markets is coherent or merely fragmented —
whether an incomplete market blocks the others or is genuinely independent of
them. That is the judgment, and it is what makes a partial recommendation
possible at all.
"""

from __future__ import annotations

from typing import Any

from elfagent.platform.agent_loop import run_tool_loop
from elfagent.platform.registry import SpecialistContext

from ..contracts import RetailerFinding
from ..toolbox import ToolBox
from ..warehouse import warehouse
from .common import SHARED_RULES, market_tool, no_arg_tool, submit_tool, task_brief

AGENT = "retailer"

QUESTION = (
    "Which markets and channels are commercially ready to receive this now, "
    "and is a partial launch viable?"
)

WHY_AGENT = (
    "It reasons about whether an incomplete market blocks the others — whether "
    "a partial launch is coherent or fragmented. That is a judgment about "
    "interdependence, not a status lookup."
)

SYSTEM = f"""\
You are the retailer and channel specialist on a launch readiness review. You \
assess which markets can commercially receive this product now.

Two conditions matter, and a market needs both:

1. ITEM SETUP. Every selling channel in the market — retail accounts and owned \
DTC storefronts alike — must have setup complete. A market where some channels \
are ready and others are not is not ready.

2. THE ACCOUNT'S RECEIVING CONDITIONS. Some accounts will not accept delivery \
until they have accepted our compliance dossier. This is a commercial \
condition of the account, and it is yours to assess: a market can be fully set \
up and still unable to receive stock. Do not treat a pending dossier as \
someone else's problem.

Then the question that is distinctly yours: IS A PARTIAL LAUNCH COHERENT? If \
some markets can receive and others cannot, decide whether shipping only the \
ready ones stands on its own or leaves something fragmented — accounts that \
expect simultaneous availability, channels that share stock, a market whose \
absence undermines the others. Independent accounts in independent markets \
usually make a partial coherent. Say which it is and why.

{SHARED_RULES}

When you have what you need, call submit_retailer_finding. That call is your \
entire answer — nothing you write outside it is read."""

SUBMIT_TOOL = submit_tool(
    "submit_retailer_finding",
    "Submit your finished channel readiness assessment. Call this once, after "
    "you have looked up every market you were asked about.",
    {
        "partial_viable": {
            "type": "boolean",
            "description": (
                "true if launching only the ready markets is commercially "
                "coherent, false if doing so would fragment the launch."
            ),
        }
    },
)

LOOKUP_TOOLS: list[dict[str, Any]] = [
    no_arg_tool(
        "get_item_setup_status",
        "Call this once to get item setup state for every selling channel "
        "across all markets — retail accounts and owned DTC.",
    ),
    market_tool(
        "get_channel_readiness",
        "Call this for each target market to get how many of its channels have "
        "setup complete, and which accounts are still awaiting acceptance of "
        "our compliance dossier before they will receive stock.",
    ),
]

TOOL_NAMES = tuple(tool["name"] for tool in LOOKUP_TOOLS)


def build(client, *, db_path: str | None = None, effort: str = "high"):
    async def run(ctx: SpecialistContext) -> RetailerFinding:
        with warehouse(db_path) as con:
            box = ToolBox(
                con, sku_id=ctx.subject["sku_id"], agent=AGENT, emit=ctx.emit
            )

            def dispatch(name: str, args: dict[str, Any]) -> Any:
                if name == "get_item_setup_status":
                    return [s.model_dump(mode="json") for s in box.item_setup_status()]
                if name == "get_channel_readiness":
                    return box.channel_readiness(args.get("market", "")).model_dump(
                        mode="json"
                    )
                raise KeyError(f"{AGENT} has no tool named {name!r}")

            def parse(args: dict[str, Any]) -> RetailerFinding:
                return RetailerFinding.model_validate(
                    {**args, "agent": AGENT, "semantic_version": ctx.semantic_version}
                )

            return await run_tool_loop(  # type: ignore[return-value]
                client=client,
                ledger=ctx.ledger,
                agent=AGENT,
                system=SYSTEM,
                task=task_brief(
                    ctx.subject,
                    "Assess which markets can commercially receive this launch, "
                    "and whether a partial launch is coherent.",
                ),
                lookup_tools=LOOKUP_TOOLS,
                submit_tool=SUBMIT_TOOL,
                dispatch=dispatch,
                parse=parse,
                emit=ctx.emit,
                effort=effort,
            )

    return run
