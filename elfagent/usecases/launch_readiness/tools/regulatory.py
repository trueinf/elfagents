"""TOOLS for the Regulatory agent — deterministic lookups (BUILD_SPEC §5.5).

Same inputs, same answer, no interpretation. These read facts and perform one
arithmetic comparison. What they deliberately do NOT do is decide whether a
gate is fatal or fixable, or whether an incomplete notification is a blocker or
a scheduling detail. That is the judgment the agent exists to make, and moving
it in here would turn the agent into a formatter.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from ..warehouse import one, rows
from .sentinels import NO_RECORD


class AnnexStatus(str, Enum):
    NONE = "none"
    ANNEX_II_PROHIBITED = "annex_ii_prohibited"
    ANNEX_III_RESTRICTED = "annex_iii_restricted"
    NO_RECORD = NO_RECORD


class IngredientRestriction(BaseModel):
    inci_name: str
    market: str
    concentration_pct: float
    annex_status: AnnexStatus
    max_limit_pct: float | None = None
    exceeds_limit: bool = False
    note: str = ""


class NotificationState(BaseModel):
    sku_id: str
    market: str
    portal: str
    status: str
    note: str = ""


def get_ingredient_restrictions(con, sku_id: str, market: str) -> list[IngredientRestriction]:
    """Every ingredient in the formula, with the restriction that applies in
    this market and whether the formula's concentration exceeds it.

    `exceeds_limit` is arithmetic, not judgment: is 22.0 greater than 20.0. What
    an exceedance MEANS — reformulate, or abandon the market — depends on
    whether the substance is conditionally restricted or outright prohibited,
    and that reading is the agent's.
    """
    found = rows(
        con,
        """
        select
            si.inci_name,
            ? as market,
            si.concentration_pct,
            i.annex_status,
            i.max_limit_pct,
            i.note
        from stg_sku_ingredients si
        left join stg_ingredients i
            on i.inci_name = si.inci_name
           and i.market = ?
        where si.sku_id = ?
        order by si.inci_name
        """,
        (market, market, sku_id),
    )

    results: list[IngredientRestriction] = []
    for row in found:
        status = row["annex_status"] or NO_RECORD
        limit = row["max_limit_pct"]
        concentration = float(row["concentration_pct"])
        exceeds = (
            status == AnnexStatus.ANNEX_II_PROHIBITED.value
            or (limit is not None and concentration > float(limit))
        )
        results.append(
            IngredientRestriction(
                inci_name=row["inci_name"],
                market=market,
                concentration_pct=concentration,
                annex_status=AnnexStatus(status),
                max_limit_pct=float(limit) if limit is not None else None,
                exceeds_limit=exceeds,
                note=row["note"] or "no restriction on record for this market",
            )
        )
    return results


def get_notification_status(con, sku_id: str, market: str) -> NotificationState:
    """Which pre-market notification portal applies here, and where it stands.

    The EU files on CPNP; Great Britain files on SCPN. They are separate
    filings on separate portals, which is why one can be complete while the
    other is not — a structural fact, not a coincidence of this dataset.
    """
    row = one(
        con,
        """
        select sku_id, market, portal, status, note
        from stg_notifications
        where sku_id = ? and market = ?
        """,
        (sku_id, market),
    )
    if row is None:
        return NotificationState(
            sku_id=sku_id,
            market=market,
            portal=NO_RECORD,
            status=NO_RECORD,
            note="no notification record on file for this market",
        )
    return NotificationState(**row)
