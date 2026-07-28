"""Binds the tools to a run: one connection, one SKU, one emitting agent.

The tools themselves stay pure functions of (connection, arguments) so they can
be unit-tested against seed data with no agent, no model and no graph. This
wrapper adds the three things a run needs and a test does not: the SKU is bound
once instead of repeated at every call site, each call is timed, and each call
is emitted onto the event stream so the trace drawer can show what the agent
actually looked up.

Every emitted call carries actor_kind="tool". The tool-vs-agent distinction is
therefore visible in the trace itself, per call, rather than being a caption
added afterwards.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from pydantic import BaseModel

from elfagent.platform.events import EventType

from . import tools as T


def _summarise(result: Any) -> str:
    """A short, human-readable result for the trace row."""
    if isinstance(result, list):
        if not result:
            return "no rows"
        if isinstance(result[0], T.IngredientRestriction):
            worst = next((r for r in result if r.exceeds_limit), None)
            if worst is None:
                return f"{len(result)} ingredients · all within limits"
            limit = (
                f"limit {worst.max_limit_pct:g}%"
                if worst.max_limit_pct is not None
                else "prohibited"
            )
            return (
                f"{worst.inci_name} {worst.concentration_pct:g}% "
                f"exceeds {limit} ({worst.annex_status.value})"
            )
        if isinstance(result[0], T.LabellingRequirement):
            unmet = [r for r in result if r.status != "met"]
            return f"{len(result)} requirements · {len(unmet)} unmet"
        if isinstance(result[0], T.ItemSetup):
            done = [r for r in result if r.status == "complete"]
            return f"{len(done)}/{len(result)} channels complete"
        if isinstance(result[0], T.LeadTime):
            weeks = [f"{r.market} {r.lead_time_weeks}w" for r in result]
            return " · ".join(weeks)
        return f"{len(result)} rows"

    if isinstance(result, T.NotificationState):
        return f"{result.portal} · {result.status}"
    if isinstance(result, T.InventoryPosition):
        if not result.on_record:
            return "no record"
        return (
            f"{result.units_available:,} of {result.units_required:,} required"
            + ("" if result.covers_demand else f" · short {result.units_short:,}")
        )
    if isinstance(result, T.TrendWindow):
        return f"window {result.window_status} · velocity {result.velocity_index}"
    if isinstance(result, T.ChannelReadiness):
        if not result.on_record:
            return "no record"
        awaiting = (
            f" · awaiting dossier: {', '.join(result.accounts_awaiting_dossier)}"
            if result.accounts_awaiting_dossier
            else ""
        )
        return (
            f"{result.setup_complete_count}/{result.channel_count} set up{awaiting}"
        )
    if isinstance(result, T.ArtworkState):
        return result.status
    if isinstance(result, BaseModel):
        return type(result).__name__
    return str(result)


def _jsonable(result: Any) -> Any:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, list):
        return [_jsonable(item) for item in result]
    return result


class ToolBox:
    """Tools bound to one SKU, for one agent, on one connection."""

    def __init__(self, con, *, sku_id: str, agent: str, emit: Callable | None = None):
        self._con = con
        self.sku_id = sku_id
        self.agent = agent
        self._emit = emit or (lambda **kw: None)
        self.calls: list[dict[str, Any]] = []

    def _call(self, name: str, fn: Callable, **kwargs: Any) -> Any:
        started = time.perf_counter()
        result = fn(self._con, self.sku_id, **kwargs)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        record = {
            "tool": name,
            "args": {"sku_id": self.sku_id, **kwargs},
            "summary": _summarise(result),
            "duration_ms": duration_ms,
        }
        self.calls.append(record)
        self._emit(
            type=EventType.AGENT_TOOL_CALL.value,
            agent=self.agent,
            actor_kind="tool",
            result=_jsonable(result),
            **record,
        )
        return result

    # ------------------------------------------------------------ regulatory

    def ingredient_restrictions(self, market: str) -> list[T.IngredientRestriction]:
        return self._call(
            "get_ingredient_restrictions", T.get_ingredient_restrictions, market=market
        )

    def notification_status(self, market: str) -> T.NotificationState:
        return self._call(
            "get_notification_status", T.get_notification_status, market=market
        )

    # ---------------------------------------------------------------- supply

    def inventory_position(self, market: str) -> T.InventoryPosition:
        return self._call(
            "get_inventory_position", T.get_inventory_position, market=market
        )

    def lead_times(self, market: str | None = None) -> list[T.LeadTime]:
        return self._call("get_lead_times", T.get_lead_times, market=market)

    def trend_window(self) -> T.TrendWindow:
        return self._call("get_trend_window", T.get_trend_window)

    # -------------------------------------------------------------- retailer

    def item_setup_status(self, retailer: str | None = None) -> list[T.ItemSetup]:
        return self._call(
            "get_item_setup_status", T.get_item_setup_status, retailer=retailer
        )

    def channel_readiness(self, market: str) -> T.ChannelReadiness:
        return self._call(
            "get_channel_readiness", T.get_channel_readiness, market=market
        )

    # ------------------------------------------------------------- packaging

    def artwork_status(self, market: str) -> T.ArtworkState:
        return self._call("get_artwork_status", T.get_artwork_status, market=market)

    def labelling_requirements(self, market: str) -> list[T.LabellingRequirement]:
        return self._call(
            "get_labelling_requirements", T.get_labelling_requirements, market=market
        )
