"""Reconciliation — four findings into one recommendation (BUILD_SPEC §12 step 5).

This is the hard part, and the part the demo exists to show. Four specialists,
each correct within its own domain, reach conflicting conclusions. Judgment has
to produce one answer without pretending the disagreement did not happen.

Two things are enforced in code rather than asked for in a prompt:

1. **Dissent must survive.** The `Recommendation` contract refuses to construct
   when the specialists' leans differ and the dissent list is empty. A
   reconciliation that quietly drops the minority view cannot be returned.

2. **A hard gate cannot be traded away.** No market that any specialist marked
   as hard-gated may come back marked ready. This is the difference between a
   constraint and a preference, and it is the one thing a persuasive-sounding
   paragraph must not be able to talk its way around. A recommendation that
   violates it is rejected and handed back for correction.

Everything else — how to weigh an open window against a slipped market, whether
a partial is coherent, how much confidence to express — is genuinely the
model's judgment.
"""

from __future__ import annotations

from typing import Any

from elfagent.platform.agent_loop import run_tool_loop
from elfagent.platform.contracts import GateType
from elfagent.platform.registry import SpecialistContext

from .contracts import LaunchFinding, LaunchRecommendation
from .specialists.common import MARKET_ITEM

AGENT = "judgment"

SYSTEM = """\
You are the judgment layer of a launch readiness review. Four specialists have \
each assessed one dimension of the same launch, independently and without \
seeing each other's work. Your job is to reconcile their findings into one \
recommendation for the human who owns the decision.

They may disagree. That is expected and it is not a defect — each is correct \
within its own domain, and the disagreement is the information. Your job is \
not to find the average.

How to reconcile:

CONSTRAINTS OUTRANK PREFERENCES. A hard gate is something that cannot be \
traded — a legal block, a physical impossibility. A commercial argument, \
however well-founded, is a preference: it says the cost of waiting is high, \
not that waiting is impossible. When a hard gate and a preference point in \
opposite directions, the gate wins. Say so explicitly rather than implying it.

MARKETS CAN BE SEPARABLE. If one market is gated and the others are not, and \
the specialists indicate the markets are commercially independent, then \
recommending a partial launch is usually right — ship what is ready, hold what \
is not. Do not slip a clear market because a different one is blocked, and do \
not ship a blocked market because others are clear.

PRESERVE THE DISSENT. Any specialist whose lean you did not follow must appear \
in the dissent list. State what they argued and why you overrode it. The \
distinction that matters: was the finding overridden by a RULE (its argument \
was valid but outranked) or by EVIDENCE (its argument did not hold up)? Say \
which. A dissent entry that only restates the majority view is worthless — the \
human reading this needs to see the strongest version of the case you did not \
take, so they can overrule you if they disagree.

CONFIDENCE REFLECTS THE RECONCILIATION, NOT THE AVERAGE. Four confident \
specialists who disagree do not produce a confident recommendation.

You recommend; you do not decide. A human owns this call and will read your \
reconciliation before making it. Write it for them: one tight paragraph, the \
reasoning rather than a restatement of the findings.

When you are ready, call submit_recommendation. That call is your entire \
answer — nothing you write outside it is read."""

SUBMIT_TOOL: dict[str, Any] = {
    "name": "submit_recommendation",
    "description": "Submit your reconciled recommendation. Call this once.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "recommended_action": {
                "type": "string",
                "enum": ["go", "slip", "partial", "hold"],
                "description": (
                    "go to launch everything now, slip to wait, partial to "
                    "launch the ready markets and hold the rest, hold to not "
                    "proceed."
                ),
            },
            "confidence": {"type": "number", "description": "Between 0 and 1."},
            "reconciliation": {
                "type": "string",
                "description": (
                    "One paragraph on how you combined the four findings and "
                    "why. The reasoning, not a summary of the inputs."
                ),
            },
            "dissent": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "One entry per specialist whose lean you did not follow. "
                    "Name them, state their case at its strongest, and say "
                    "whether they were overridden by rule or by evidence."
                ),
            },
            "per_market_action": {
                "type": "array",
                "items": MARKET_ITEM,
                "description": (
                    "The action for each market. 'ready' true means ship it "
                    "now, false means hold it."
                ),
            },
        },
        "required": [
            "recommended_action",
            "confidence",
            "reconciliation",
            "dissent",
            "per_market_action",
        ],
        "additionalProperties": False,
    },
}


def render(findings: list[LaunchFinding]) -> str:
    """The four findings, as the judgment layer sees them."""
    blocks = []
    for finding in findings:
        lines = [
            f"### {finding.agent.upper()}",
            f"lean: {finding.lean.value}   confidence: {finding.confidence}",
            f"rationale: {finding.rationale}",
        ]
        for segment in finding.segments:
            gate = segment.gate_type.value if segment.gate_type else "none"
            lines.append(
                f"  - {segment.segment}: ready={segment.ready} gate={gate} "
                f"— {segment.detail}"
            )
        for item in finding.evidence:
            lines.append(f"  evidence: {item}")

        # The specialist-specific fields carry the part of each finding that
        # does not fit the shared shape, and they are often the load-bearing
        # detail — whether a partial is viable, what delay costs.
        for extra in (
            "hard_gate_markets",
            "cost_of_delay_note",
            "partial_viable",
            "long_pole_market",
        ):
            if hasattr(finding, extra):
                lines.append(f"  {extra}: {getattr(finding, extra)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def hard_gated_markets(findings: list[LaunchFinding]) -> set[str]:
    return {
        segment.segment
        for finding in findings
        for segment in finding.segments
        if segment.gate_type is GateType.HARD
    }


def build(client, *, effort: str = "high"):
    async def judgment(
        ctx: SpecialistContext, findings: list[LaunchFinding]
    ) -> LaunchRecommendation:
        if not findings:
            raise ValueError("judgment received no findings")

        gated = hard_gated_markets(findings)

        def parse(args: dict[str, Any]) -> LaunchRecommendation:
            recommendation = LaunchRecommendation.model_validate(
                {
                    **args,
                    "subject_id": ctx.subject_id,
                    "findings": [f.model_dump(mode="json") for f in findings],
                }
            )
            # The system recommends; it may not recommend shipping into a hard
            # legal gate. Checked here so no amount of persuasive reconciliation
            # can produce one.
            overridden = [
                market.segment
                for market in recommendation.per_segment_action
                if market.segment in gated and market.ready
            ]
            if overridden:
                raise ValueError(
                    f"markets {overridden} carry a hard gate from a specialist "
                    "and cannot be marked ready. A hard gate is a constraint, "
                    "not a preference — hold those markets and record the "
                    "trade-off in your dissent instead."
                )
            return recommendation

        task = (
            "Reconcile these four specialist findings into one recommendation "
            f"for launch {ctx.subject_id} "
            f"({ctx.subject.get('sku_name')}, markets "
            f"{', '.join(ctx.subject.get('target_markets', []))}).\n\n"
            f"{render(findings)}"
        )

        return await run_tool_loop(  # type: ignore[return-value]
            client=client,
            ledger=ctx.ledger,
            agent=AGENT,
            system=SYSTEM,
            task=task,
            lookup_tools=[],
            submit_tool=SUBMIT_TOOL,
            dispatch=lambda name, args: (_ for _ in ()).throw(
                KeyError(f"judgment has no tool named {name!r}")
            ),
            parse=parse,
            emit=ctx.emit,
            effort=effort,
        )

    return judgment
