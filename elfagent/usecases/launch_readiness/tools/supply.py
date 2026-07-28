"""TOOLS for the Supply agent — deterministic lookups (BUILD_SPEC §5.5).

These report position. They do not decide what waiting costs — weighing an open
trend window against a reformulation lead time is the judgment the agent makes.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..warehouse import one, rows
from .sentinels import NO_RECORD


class InventoryPosition(BaseModel):
    sku_id: str
    market: str
    units_available: int = 0
    units_required: int = 0
    units_short: int = 0
    covers_demand: bool = False
    on_record: bool = True
    note: str = ""


class LeadTime(BaseModel):
    sku_id: str
    market: str
    lead_time_weeks: int | None = None
    note: str = ""


class TrendWindow(BaseModel):
    sku_id: str
    window_status: str
    velocity_index: int = 0
    note: str = ""


def get_inventory_position(con, sku_id: str, market: str) -> InventoryPosition:
    row = one(
        con,
        """
        select sku_id, market, units_available, units_required, note
        from stg_inventory
        where sku_id = ? and market = ?
        """,
        (sku_id, market),
    )
    if row is None:
        return InventoryPosition(
            sku_id=sku_id,
            market=market,
            on_record=False,
            note="no inventory record on file for this market",
        )
    available = int(row["units_available"])
    required = int(row["units_required"])
    return InventoryPosition(
        sku_id=row["sku_id"],
        market=row["market"],
        units_available=available,
        units_required=required,
        units_short=max(0, required - available),
        covers_demand=available >= required,
        note=row["note"] or "",
    )


def get_lead_times(con, sku_id: str, market: str | None = None) -> list[LeadTime]:
    """Replenishment lead time per market.

    Keyed by SKU *and* market, not SKU alone — a market whose formula is not in
    production has a materially different lead time from one that is stocked,
    and collapsing them would hide the whole reason a partial launch is on the
    table.
    """
    sql = """
        select sku_id, market, lead_time_weeks, note
        from stg_inventory
        where sku_id = ?
    """
    params: tuple = (sku_id,)
    if market is not None:
        sql += " and market = ?"
        params += (market,)
    sql += " order by market"

    found = rows(con, sql, params)
    if not found:
        return [
            LeadTime(
                sku_id=sku_id,
                market=market or NO_RECORD,
                note="no lead time on record",
            )
        ]
    return [
        LeadTime(
            sku_id=r["sku_id"],
            market=r["market"],
            lead_time_weeks=int(r["lead_time_weeks"]),
            note=r["note"] or "",
        )
        for r in found
    ]


def get_trend_window(con, sku_id: str) -> TrendWindow:
    row = one(
        con,
        """
        select sku_id, window_status, velocity_index, note
        from stg_trend_signals
        where sku_id = ?
        """,
        (sku_id,),
    )
    if row is None:
        return TrendWindow(
            sku_id=sku_id,
            window_status=NO_RECORD,
            note="no trend signal on record",
        )
    return TrendWindow(
        sku_id=row["sku_id"],
        window_status=row["window_status"],
        velocity_index=int(row["velocity_index"]),
        note=row["note"] or "",
    )
