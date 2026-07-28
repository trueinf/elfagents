"""TOOLS for the Retailer agent — deterministic lookups (BUILD_SPEC §5.5).

`compliance_dossier_status` is a retailer-side RECEIVING condition: has this
account accepted our compliance dossier. EU accounts require it before they will
take delivery. It is commercial-operations data the Retailer agent owns, not
regulatory data borrowed from another specialist — which matters, because under
star topology the Retailer agent never sees the Regulatory finding and must
reach its own conclusion about which markets can receive stock.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..warehouse import rows


class ItemSetup(BaseModel):
    sku_id: str
    retailer: str
    market: str
    channel: str
    status: str
    compliance_dossier_status: str
    note: str = ""


class ChannelReadiness(BaseModel):
    sku_id: str
    market: str
    channel_count: int = 0
    setup_complete_count: int = 0
    all_setup_complete: bool = False
    accounts_awaiting_dossier: list[str] = []
    on_record: bool = True


def get_item_setup_status(
    con, sku_id: str, retailer: str | None = None
) -> list[ItemSetup]:
    sql = """
        select sku_id, retailer, market, channel, status,
               compliance_dossier_status, note
        from stg_item_setup
        where sku_id = ?
    """
    params: tuple = (sku_id,)
    if retailer is not None:
        sql += " and retailer = ?"
        params += (retailer,)
    sql += " order by market, retailer"
    return [ItemSetup(**r) for r in rows(con, sql, params)]


def get_channel_readiness(con, sku_id: str, market: str) -> ChannelReadiness:
    """Every selling channel in a market — retail accounts and owned DTC.

    Reports two independent things without ranking them: whether setup is
    complete, and which accounts are still waiting on a compliance dossier. A
    market can be fully set up and still unable to receive stock. Deciding
    whether that makes a partial launch coherent or merely fragmented is the
    agent's call.
    """
    found = rows(
        con,
        """
        select retailer, status, compliance_dossier_status
        from stg_item_setup
        where sku_id = ? and market = ?
        order by retailer
        """,
        (sku_id, market),
    )
    if not found:
        return ChannelReadiness(sku_id=sku_id, market=market, on_record=False)

    complete = [r for r in found if r["status"] == "complete"]
    awaiting = [
        r["retailer"]
        for r in found
        if r["compliance_dossier_status"] not in ("accepted", "not_required")
    ]
    return ChannelReadiness(
        sku_id=sku_id,
        market=market,
        channel_count=len(found),
        setup_complete_count=len(complete),
        all_setup_complete=len(complete) == len(found),
        accounts_awaiting_dossier=awaiting,
    )
