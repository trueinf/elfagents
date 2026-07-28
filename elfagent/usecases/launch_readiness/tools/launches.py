"""TOOLS for reading the launch calendar — deterministic (BUILD_SPEC §5.5).

These read the governed `launches` mart rather than raw tables, because the
queue and the countdown are governed facts. The specialists read the underlying
staging tables instead: they reason over the evidence, with the governed metric
available as the baseline they can agree or disagree with.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ..warehouse import one, rows


def _split(value: str | None) -> list[str]:
    return [part for part in (value or "").split(";") if part]


class LaunchRecord(BaseModel):
    launch_id: str
    sku_id: str
    sku_name: str
    brand: str
    category: str
    target_markets: list[str] = Field(default_factory=list)
    first_ship_date: date
    countdown_weeks: int
    scenario: str

    # The governed metric's view, before any agent has reasoned about it.
    readiness_shape: str
    ready_markets: list[str] = Field(default_factory=list)
    blocked_markets: list[str] = Field(default_factory=list)

    at_gate_threshold: bool
    semantic_version: str

    def as_subject(self) -> dict:
        """The launch context the orchestrator hands to every specialist."""
        return self.model_dump(mode="json")


def _record(row: dict) -> LaunchRecord:
    return LaunchRecord(
        launch_id=row["launch_id"],
        sku_id=row["sku_id"],
        sku_name=row["sku_name"],
        brand=row["brand"],
        category=row["category"],
        target_markets=_split(row["target_markets"]),
        first_ship_date=row["first_ship_date"],
        countdown_weeks=int(row["countdown_weeks"]),
        scenario=row["scenario"],
        readiness_shape=row["readiness_shape"],
        ready_markets=_split(row["ready_markets"]),
        blocked_markets=_split(row["blocked_markets"]),
        at_gate_threshold=bool(row["at_gate_threshold"]),
        semantic_version=row["semantic_version"],
    )


_SELECT = """
    select launch_id, sku_id, sku_name, brand, category, target_markets,
           first_ship_date, countdown_weeks, scenario, readiness_shape,
           ready_markets, blocked_markets, at_gate_threshold, semantic_version
    from launches
"""


def get_launch(con, launch_id: str) -> LaunchRecord | None:
    row = one(con, _SELECT + " where launch_id = ?", (launch_id,))
    return _record(row) if row else None


def launches_at_gate(con) -> list[LaunchRecord]:
    """Every launch that has reached the countdown threshold."""
    return [
        _record(r)
        for r in rows(
            con, _SELECT + " where at_gate_threshold order by first_ship_date"
        )
    ]


def all_launches(con) -> list[LaunchRecord]:
    return [_record(r) for r in rows(con, _SELECT + " order by first_ship_date")]
