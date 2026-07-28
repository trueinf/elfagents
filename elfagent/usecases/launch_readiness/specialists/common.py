"""Shared shapes for the four specialists.

Every specialist answers a different question over different data, but they all
return the same base contract and they all take market codes as tool arguments.
Those parts live here so the differences between the four are the interesting
parts — the question, the tools, the judgment — rather than repeated schema.
"""

from __future__ import annotations

from typing import Any

from ..contracts import Lean

MARKET_ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "market": {"type": "string", "description": "Market code, e.g. DE."},
        "ready": {
            "anyOf": [{"type": "boolean"}, {"type": "null"}],
            "description": (
                "true if ready on your dimension, false if not, null if "
                "genuinely conditional or ambiguous. Use null rather than "
                "rounding an ambiguous case to a boolean."
            ),
        },
        "gate_type": {
            "anyOf": [
                {"type": "string", "enum": ["hard", "conditional"]},
                {"type": "null"},
            ],
            "description": (
                "'hard' for a block that cannot be traded against a schedule "
                "preference, 'conditional' where a path through it exists, "
                "null when the market is clear on your dimension."
            ),
        },
        "detail": {"type": "string", "description": "One sentence on why."},
    },
    "required": ["market", "ready", "gate_type", "detail"],
    "additionalProperties": False,
}

# Numerical bounds (confidence 0..1) are deliberately absent: strict tool
# schemas do not support them. The contract enforces the range on our side and
# a violation comes back to the model as a correction.
_BASE_PROPERTIES: dict[str, Any] = {
    "lean": {
        "type": "string",
        "enum": [lean.value for lean in Lean],
        "description": (
            "Your recommendation for this launch, from your dimension only: "
            "go if every market is ready, slip if the launch should wait, "
            "partial if some markets are ready and others are not, hold if it "
            "should not proceed at all."
        ),
    },
    "confidence": {"type": "number", "description": "Between 0 and 1."},
    "rationale": {"type": "string", "description": "One paragraph."},
    "evidence": {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "The concrete facts your lean rests on, each traceable to a tool "
            "result."
        ),
    },
    "per_market": {"type": "array", "items": MARKET_ITEM},
}

_BASE_REQUIRED = ["lean", "confidence", "rationale", "evidence", "per_market"]


def submit_tool(
    name: str, description: str, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    extra = extra or {}
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {**_BASE_PROPERTIES, **extra},
            "required": [*_BASE_REQUIRED, *extra.keys()],
            "additionalProperties": False,
        },
    }


def market_tool(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Market code."}
            },
            "required": ["market"],
            "additionalProperties": False,
        },
    }


def no_arg_tool(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    }


SHARED_RULES = """\
Your remit is your dimension only. You never see the other specialists' \
conclusions, and you must not speculate about them — reach your own view from \
the data you retrieve, and say plainly where your dimension is clear even if \
you suspect something else might block the launch.

A tool result of "no_record" means nothing is on file. It does NOT mean the \
answer is favourable. Say so explicitly when you rely on it.

Reason only from what the tools return. Do not supply facts from your own \
knowledge — if you need one, look it up.

Keep your rationale to one tight paragraph. State the finding and the reason \
for it; leave out restatements of the data, caveats, and commentary on your \
own process. Assess exactly the markets you are given and nothing beyond them."""


def task_brief(subject: dict[str, Any], instruction: str) -> str:
    return (
        f"{instruction}\n\n"
        f"launch_id: {subject.get('launch_id')}\n"
        f"sku: {subject.get('sku_id')} — {subject.get('sku_name')}\n"
        f"brand: {subject.get('brand')}\n"
        f"target markets: {', '.join(subject.get('target_markets', []))}\n"
        f"first ship date: {subject.get('first_ship_date')} "
        f"(T-minus {subject.get('countdown_weeks')} weeks)"
    )
