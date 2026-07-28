"""TOOLS for the Packaging agent — deterministic lookups (BUILD_SPEC §5.5).

Artwork state is one flag per market; labelling is several requirements per
market. That asymmetry is deliberate — judging WHICH gap actually drives the
timeline is only a real question when there is more than one gap to choose
between.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..warehouse import one, rows
from .sentinels import NO_RECORD


class ArtworkState(BaseModel):
    sku_id: str
    market: str
    status: str
    note: str = ""


class LabellingRequirement(BaseModel):
    sku_id: str
    market: str
    requirement: str
    status: str
    note: str = ""


def get_artwork_status(con, sku_id: str, market: str) -> ArtworkState:
    row = one(
        con,
        """
        select sku_id, market, status, note
        from stg_artwork
        where sku_id = ? and market = ?
        """,
        (sku_id, market),
    )
    if row is None:
        return ArtworkState(
            sku_id=sku_id,
            market=market,
            status=NO_RECORD,
            note="no artwork record on file for this market",
        )
    return ArtworkState(**row)


def get_labelling_requirements(
    con, sku_id: str, market: str
) -> list[LabellingRequirement]:
    found = rows(
        con,
        """
        select sku_id, market, requirement, status, note
        from stg_labelling_requirements
        where sku_id = ? and market = ?
        order by requirement
        """,
        (sku_id, market),
    )
    if not found:
        return [
            LabellingRequirement(
                sku_id=sku_id,
                market=market,
                requirement=NO_RECORD,
                status=NO_RECORD,
                note="no labelling requirements on file for this market",
            )
        ]
    return [LabellingRequirement(**r) for r in found]
