"""The specialist loop: reason, look things up, return a validated contract.

Domain-agnostic. It knows that a specialist calls deterministic lookup tools and
must finish by submitting an object that validates against a declared contract.
It does not know what the lookups are or what the contract means.

Two properties are worth naming, because both are the difference between an
agent and a formatter:

* The MODEL chooses which lookups to make and in what order. It is handed the
  tools, not a pre-fetched brief. If we gathered the facts for it and asked only
  for a verdict, calling the result an agent would be generous.

* The contract is enforced, and a malformed submission is handed back as a tool
  error with the validation message so the model can correct it — inside the
  same step budget. Prose never crosses the boundary.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError

from .events import EventType
from .limits import HardStop, SpendLedger
from .llm import ModelClient, charge


class ContractNotSubmitted(RuntimeError):
    """The specialist never produced a valid contract within its step budget."""


def _as_tool_result(tool_use_id: str, payload: Any, *, is_error: bool = False) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": payload if isinstance(payload, str) else json.dumps(payload),
        **({"is_error": True} if is_error else {}),
    }


async def run_tool_loop(
    *,
    client: ModelClient,
    ledger: SpendLedger,
    agent: str,
    system: str,
    task: str,
    lookup_tools: list[dict[str, Any]],
    submit_tool: dict[str, Any],
    dispatch: Callable[[str, dict[str, Any]], Any],
    parse: Callable[[dict[str, Any]], BaseModel],
    emit: Callable[..., None] = lambda **_: None,
    effort: str = "high",
    max_tokens: int = 16000,
) -> BaseModel:
    """Run one specialist to a validated finding.

    The step budget is the shared ledger's, so four specialists cannot each
    quietly take the maximum. On the final permitted step the submit tool is
    forced, so the run ends with a contract rather than another lookup.
    """
    tools = [*lookup_tools, submit_tool]
    submit_name = submit_tool["name"]
    max_steps = ledger.limits.max_steps_per_agent

    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

    for step in range(1, max_steps + 1):
        ledger.begin_step(agent)
        final_step = step == max_steps

        reply = await client.complete(
            system=system,
            messages=messages,
            tools=tools,
            tool_choice={"type": "tool", "name": submit_name} if final_step else None,
            max_tokens=max_tokens,
            effort=effort,
        )
        charge(ledger, agent, reply)

        # Echo the assistant turn back verbatim. Thinking blocks in particular
        # must be replayed unedited, so the raw content is used rather than a
        # reconstruction of it.
        messages.append(
            {"role": "assistant", "content": reply.raw_content or reply.text}
        )

        submission = reply.call_named(submit_name)
        if submission is not None:
            try:
                finding = parse(submission.input)
            # ValidationError is a ValueError, so this covers both a schema
            # violation and a rule the parse function enforces itself.
            except ValueError as invalid:
                detail = (
                    invalid.errors(include_url=False)
                    if isinstance(invalid, ValidationError)
                    else str(invalid)
                )
                emit(
                    type=EventType.AGENT_TOOL_CALL.value,
                    agent=agent,
                    actor_kind="tool",
                    tool=submit_name,
                    summary="rejected by contract",
                    duration_ms=0.0,
                    error=detail,
                )
                if final_step:
                    raise ContractNotSubmitted(
                        f"{agent} submitted an invalid {submit_name} on its last "
                        f"permitted step: {invalid}"
                    ) from invalid
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            _as_tool_result(
                                submission.id,
                                f"Rejected by the contract: {invalid}. "
                                "Resubmit with these fields corrected.",
                                is_error=True,
                            )
                        ],
                    }
                )
                continue
            return finding

        if not reply.tool_calls:
            # The model answered in prose instead of using a tool. Say so
            # plainly rather than trying to parse whatever it wrote.
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Respond only by calling a tool. Use the lookup tools to "
                        f"gather what you need, then call {submit_name}."
                    ),
                }
            )
            continue

        results = []
        for call in reply.tool_calls:
            try:
                results.append(_as_tool_result(call.id, dispatch(call.name, call.input)))
            except HardStop:
                raise
            except Exception as failure:
                results.append(
                    _as_tool_result(
                        call.id, f"{type(failure).__name__}: {failure}", is_error=True
                    )
                )
        messages.append({"role": "user", "content": results})

    raise ContractNotSubmitted(
        f"{agent} exhausted {max_steps} steps without submitting a {submit_name}"
    )
