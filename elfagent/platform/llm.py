"""Model access for the platform — one provider, one key, spend-capped.

Two implementations satisfy the same protocol:

  AnthropicClient  the real thing.
  ScriptedClient   a deterministic stub that returns pre-written replies.

The stub is not a testing convenience bolted on afterwards — it is what lets the
entire specialist loop (tool selection, contract validation, retry on malformed
output, step and spend caps) be asserted without a network call or an API key.
A test suite that can only run when a key is present is a test suite that stops
running.

This module is domain-agnostic: it knows about models, tools and token cost, and
nothing about launches.
"""

from __future__ import annotations

import copy
import os
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .limits import SpendLedger

# USD per million tokens (input, output). Kept here rather than inferred so the
# ledger charges real numbers and the trace can show an honest cost.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-fable-5": (10.00, 50.00),
}

DEFAULT_MODEL = "claude-opus-5"


class ModelRefused(RuntimeError):
    """The model declined the request.

    Claude Opus 5 returns a successful HTTP 200 with stop_reason "refusal" when
    its safety classifiers decline — `content` is empty or partial. Reading
    content[0] blindly would produce a confident-looking finding from nothing,
    so this surfaces as a hard failure instead.
    """


class ToolCall(BaseModel):
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ModelReply(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0

    # LangSmith reads token usage off an LLM run's output under this exact key.
    # Without it the trace shows the call tree but reports zero tokens and no
    # cost, which is a thin answer to "is this real?".
    usage_metadata: dict[str, int] = Field(default_factory=dict)

    # The assistant turn's raw content blocks, kept verbatim so the next request
    # can echo them back unchanged. Thinking blocks in particular must not be
    # edited or reconstructed between turns.
    #
    # Excluded from serialisation: these are provider SDK objects, and letting
    # them into a trace payload makes the whole output unserialisable — which
    # silently costs the usage figures alongside it. Attribute access is
    # unaffected, so the echo-back path still gets them unchanged.
    raw_content: Any = Field(default=None, exclude=True)

    def call_named(self, name: str) -> ToolCall | None:
        return next((c for c in self.tool_calls if c.name == name), None)


class ModelClient(Protocol):
    model: str

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = ...,
        max_tokens: int = ...,
        effort: str = ...,
    ) -> ModelReply: ...


def price(model: str, input_tokens: int, output_tokens: int) -> float:
    rate_in, rate_out = PRICING.get(model, PRICING[DEFAULT_MODEL])
    return (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000


def _traced(fn):
    """Register model calls with LangSmith.

    LangGraph's nodes are instrumented automatically, but these calls go
    straight to the Anthropic SDK rather than through LangChain, so without
    this the trace tree would show four agent nodes with nothing inside them —
    a weak answer to "is this real?". Decorating here nests each model call
    under the node that made it.

    Degrades to a no-op when langsmith is absent or tracing is off.
    """
    try:
        from langsmith import traceable
    except ImportError:  # pragma: no cover
        return fn
    return traceable(run_type="llm", name="anthropic.messages")(fn)


class AnthropicClient:
    """The real client.

    Notes on the request shape, because several of these would be silent
    mistakes rather than obvious ones:

    * No `temperature` / `top_p` / `top_k` — removed on Claude Opus 5; sending
      any of them is a 400. Behaviour is steered by prompting instead.
    * No `thinking` config — thinking is ON by default on Claude Opus 5, and
      `budget_tokens` is a 400. Depth is controlled by `output_config.effort`.
      Because thinking shares the `max_tokens` ceiling with the response, that
      ceiling is set generously.
    * `fallbacks: "default"` is enabled. Claude Opus 5's classifiers can decline
      a request, and benign regulatory or security-adjacent wording is exactly
      the kind of thing that can trip them. With fallbacks on, the API re-runs
      the declined request on a fallback model server-side instead of handing
      back a refusal.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        client: Any = None,
    ) -> None:
        self.model = model
        if client is not None:
            self._client = client
            return
        from anthropic import AsyncAnthropic

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = AsyncAnthropic(api_key=key) if key else AsyncAnthropic()

    @_traced
    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int = 16000,
        effort: str = "high",
    ) -> ModelReply:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "tools": tools,
            "output_config": {"effort": effort},
            "betas": ["server-side-fallback-2026-07-01"],
            "fallbacks": "default",
        }
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        response = await self._client.beta.messages.create(**kwargs)

        # Check the stop reason BEFORE touching content.
        if response.stop_reason == "refusal":
            category = getattr(getattr(response, "stop_details", None), "category", None)
            raise ModelRefused(
                f"model declined the request (category={category!r}); "
                "no finding was produced"
            )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, input=dict(block.input))
                )

        usage = response.usage
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        # Stamp the run directly rather than relying on the tracer inferring
        # usage from the return value.
        try:
            from langsmith import get_current_run_tree

            tree = get_current_run_tree()
            if tree is not None:
                tree.metadata["model"] = self.model
                tree.metadata["effort"] = effort
                tree.metadata["usd"] = round(
                    price(self.model, input_tokens, output_tokens), 6
                )
                tree.metadata["usage_metadata"] = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
        except Exception:
            pass

        return ModelReply(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usd=price(self.model, input_tokens, output_tokens),
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            raw_content=response.content,
        )


class ScriptedClient:
    """A deterministic stand-in. Returns pre-written replies, in order.

    Lets the whole specialist loop be tested — including the paths that only
    happen when a model misbehaves — with no key and no network.
    """

    def __init__(
        self, replies: list[ModelReply], *, model: str = "scripted"
    ) -> None:
        self.model = model
        self._replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int = 16000,
        effort: str = "high",
    ) -> ModelReply:
        self.calls.append(
            {
                "system": system,
                # Snapshot, not a reference: the loop mutates this list after
                # the call returns, and recording the live object would make
                # every entry show the final state instead of what was sent.
                "messages": copy.deepcopy(messages),
                "tools": [t["name"] for t in tools],
                "tool_choice": tool_choice,
                "effort": effort,
            }
        )
        if not self._replies:
            raise AssertionError(
                f"ScriptedClient exhausted after {len(self.calls)} calls; "
                "the loop asked for more turns than the script provides"
            )
        return self._replies.pop(0)


class RoutedScriptedClient:
    """A stub that routes replies by which agent is calling.

    `ScriptedClient` pops replies in call order, which is fine for one agent
    and useless for four running concurrently — the interleaving is
    nondeterministic, so a flat script would hand the wrong reply to the wrong
    specialist at random. This routes on the submit tool in the request, which
    uniquely identifies the caller, and keeps a separate queue per agent.
    """

    def __init__(
        self, scripts: dict[str, list[ModelReply]], *, model: str = "routed"
    ) -> None:
        self.model = model
        self._scripts = {key: list(value) for key, value in scripts.items()}
        self.calls: list[dict[str, Any]] = []

    @staticmethod
    def _route(tools: list[dict[str, Any]]) -> str:
        for tool in tools:
            if tool["name"].startswith("submit_"):
                return tool["name"]
        raise AssertionError("no submit tool in request; cannot route")

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int = 16000,
        effort: str = "high",
    ) -> ModelReply:
        key = self._route(tools)
        self.calls.append(
            {
                "route": key,
                "messages": copy.deepcopy(messages),
                "tools": [t["name"] for t in tools],
                "tool_choice": tool_choice,
            }
        )
        queue = self._scripts.get(key)
        if not queue:
            raise AssertionError(f"no scripted reply left for {key!r}")
        return queue.pop(0)


def charge(ledger: SpendLedger, agent: str, reply: ModelReply) -> None:
    ledger.charge(
        agent,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        usd=reply.usd,
    )
