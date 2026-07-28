"""The PACKAGING specialist — an agent, not a tool (BUILD_SPEC §5.4).

Question: *is packaging and labelling ready per market, and where is the long
pole?*

The tools can report that artwork is blocked and that two labelling
requirements are unmet. What they cannot do is judge which gap actually drives
the date — which is the long pole and which are cosmetic, and whether a
blocked artwork state is a consequence of something upstream or a cause in its
own right. Ranking gaps by their effect on the timeline is the judgment.
"""

from __future__ import annotations

from typing import Any

from elfagent.platform.agent_loop import run_tool_loop
from elfagent.platform.registry import SpecialistContext

from ..contracts import PackagingFinding
from ..toolbox import ToolBox
from ..warehouse import warehouse
from .common import SHARED_RULES, market_tool, submit_tool, task_brief

AGENT = "packaging"

QUESTION = "Is packaging and labelling ready per market, and where is the long pole?"

WHY_AGENT = (
    "It judges which packaging gap actually drives the timeline versus which "
    "are cosmetic. Ranking gaps by their effect on a date is judgment, not a "
    "status lookup."
)

SYSTEM = f"""\
You are the packaging and labelling specialist on a launch readiness review. \
You assess whether artwork and on-pack labelling are ready in each market.

Artwork is one state per market. Labelling is several requirements per market, \
and they are not equal — some are quick corrections and some require the pack \
to be redesigned and reprinted.

The question that is distinctly yours is WHERE THE LONG POLE IS. Do not just \
list what is unmet. Decide which single gap actually drives the date in the \
worst market, and name it. If artwork is blocked pending a change that has not \
happened yet, the blocking change is the long pole, not the artwork state that \
follows from it. If a market has several unmet requirements, say which one \
finishes last.

If every market is ready, say so and set the long pole to null rather than \
inventing one.

{SHARED_RULES}

When you have what you need, call submit_packaging_finding. That call is your \
entire answer — nothing you write outside it is read."""

SUBMIT_TOOL = submit_tool(
    "submit_packaging_finding",
    "Submit your finished packaging assessment. Call this once, after you have "
    "looked up every market you were asked about.",
    {
        "long_pole_market": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": (
                "The market whose packaging gap drives the timeline, or null "
                "if no market is gated on packaging."
            ),
        }
    },
)

LOOKUP_TOOLS: list[dict[str, Any]] = [
    market_tool(
        "get_artwork_status",
        "Call this for each target market to get the state of packaging "
        "artwork there.",
    ),
    market_tool(
        "get_labelling_requirements",
        "Call this for each target market to get every on-pack labelling "
        "requirement that applies there and whether it is met. Several can "
        "apply to one market.",
    ),
]

TOOL_NAMES = tuple(tool["name"] for tool in LOOKUP_TOOLS)


def build(client, *, db_path: str | None = None, effort: str = "high"):
    async def run(ctx: SpecialistContext) -> PackagingFinding:
        with warehouse(db_path) as con:
            box = ToolBox(
                con, sku_id=ctx.subject["sku_id"], agent=AGENT, emit=ctx.emit
            )

            def dispatch(name: str, args: dict[str, Any]) -> Any:
                market = args.get("market", "")
                if name == "get_artwork_status":
                    return box.artwork_status(market).model_dump(mode="json")
                if name == "get_labelling_requirements":
                    return [
                        r.model_dump(mode="json")
                        for r in box.labelling_requirements(market)
                    ]
                raise KeyError(f"{AGENT} has no tool named {name!r}")

            def parse(args: dict[str, Any]) -> PackagingFinding:
                return PackagingFinding.model_validate(
                    {**args, "agent": AGENT, "semantic_version": ctx.semantic_version}
                )

            return await run_tool_loop(  # type: ignore[return-value]
                client=client,
                ledger=ctx.ledger,
                agent=AGENT,
                system=SYSTEM,
                task=task_brief(
                    ctx.subject,
                    "Assess packaging and labelling readiness, and identify the "
                    "long pole.",
                ),
                lookup_tools=LOOKUP_TOOLS,
                submit_tool=SUBMIT_TOOL,
                dispatch=dispatch,
                parse=parse,
                emit=ctx.emit,
                effort=effort,
            )

    return run
