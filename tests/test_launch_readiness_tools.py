"""The deterministic tools, unit-tested against the seed data (§12 step 3).

These are the tools the specialists reason over. If they are wrong, every
finding above them is wrong in a way that looks like a model problem, so they
are tested directly and without a model in the loop.
"""

from __future__ import annotations

import duckdb
import pytest

from elfagent.usecases.launch_readiness import signal
from elfagent.usecases.launch_readiness import tools as T
from elfagent.usecases.launch_readiness.contracts import (
    Lean,
    MarketReadiness,
    RegulatoryFinding,
)
from elfagent.usecases.launch_readiness.toolbox import ToolBox
from elfagent.usecases.launch_readiness.warehouse import connect

VITC = "SKU-VITC"
GLOW = "SKU-GLOW"


@pytest.fixture(scope="module")
def con():
    connection = connect()
    yield connection
    connection.close()


# ------------------------------------------------------------------- signal


def test_signal_is_a_date_comparison_not_a_judgement(con):
    at_gate = {r.launch_id for r in T.launches_at_gate(con)}
    assert at_gate == {"LAUNCH-1001", "LAUNCH-1002", "LAUNCH-1003"}
    assert "LAUNCH-1004" not in at_gate, "1004 is 11 weeks out and must not fire"


def test_signal_queue_is_serialisable_for_the_front_end():
    queue = signal.queue()
    assert {q["launch_id"] for q in queue} == {
        "LAUNCH-1001",
        "LAUNCH-1002",
        "LAUNCH-1003",
    }
    star = next(q for q in queue if q["launch_id"] == "LAUNCH-1001")
    assert star["target_markets"] == ["US", "DE", "UK"]
    assert star["readiness_shape"] == "mixed"
    assert star["semantic_version"] == "launch_ready@v3"


def test_get_launch_reads_the_governed_mart(con):
    launch = T.get_launch(con, "LAUNCH-1001")
    assert launch is not None
    assert launch.sku_name == "Bright Reset Vitamin-C Serum"
    assert launch.ready_markets == ["UK", "US"]
    assert launch.blocked_markets == ["DE"]
    assert T.get_launch(con, "LAUNCH-9999") is None


# --------------------------------------------------------------- regulatory


def test_the_same_concentration_is_compliant_in_one_market_and_not_another(con):
    """The heart of the demo, asserted at the tool layer."""
    de = {r.inci_name: r for r in T.get_ingredient_restrictions(con, VITC, "DE")}
    uk = {r.inci_name: r for r in T.get_ingredient_restrictions(con, VITC, "UK")}

    assert de["Ascorbic Acid"].concentration_pct == 22.0
    assert de["Ascorbic Acid"].max_limit_pct == 20.0
    assert de["Ascorbic Acid"].exceeds_limit is True

    assert uk["Ascorbic Acid"].concentration_pct == 22.0
    assert uk["Ascorbic Acid"].max_limit_pct == 25.0
    assert uk["Ascorbic Acid"].exceeds_limit is False


def test_restricted_and_prohibited_are_distinguishable_by_the_tool(con):
    """A conditional restriction and an outright ban must not look alike.

    Collapsing them into one 'non-compliant' flag would take the judgment away
    from the agent and hand it to whoever wrote the query.
    """
    vitc_de = {r.inci_name: r for r in T.get_ingredient_restrictions(con, VITC, "DE")}
    glow_de = {r.inci_name: r for r in T.get_ingredient_restrictions(con, GLOW, "DE")}

    assert vitc_de["Ascorbic Acid"].annex_status is T.AnnexStatus.ANNEX_III_RESTRICTED
    assert glow_de["Triclocarban"].annex_status is T.AnnexStatus.ANNEX_II_PROHIBITED
    # Prohibited at any concentration — 0.1% is still a breach.
    assert glow_de["Triclocarban"].concentration_pct == 0.1
    assert glow_de["Triclocarban"].exceeds_limit is True


def test_us_has_no_concentration_restriction_on_record(con):
    us = {r.inci_name: r for r in T.get_ingredient_restrictions(con, VITC, "US")}
    assert us["Ascorbic Acid"].annex_status is T.AnnexStatus.NONE
    assert us["Ascorbic Acid"].max_limit_pct is None
    assert us["Ascorbic Acid"].exceeds_limit is False


def test_eu_and_gb_are_separate_filings_on_separate_portals(con):
    de = T.get_notification_status(con, VITC, "DE")
    uk = T.get_notification_status(con, VITC, "UK")
    us = T.get_notification_status(con, VITC, "US")

    assert (de.portal, de.status) == ("CPNP", "in_progress")
    assert (uk.portal, uk.status) == ("SCPN", "complete")
    assert (us.portal, us.status) == ("none", "not_required")


def test_absent_records_return_an_explicit_sentinel_never_null(con):
    """Silence must never be mistakable for permission."""
    missing = T.get_notification_status(con, VITC, "FR")
    assert missing.status == T.NO_RECORD
    assert missing.portal == T.NO_RECORD
    assert "no notification record" in missing.note

    artwork = T.get_artwork_status(con, VITC, "FR")
    assert artwork.status == T.NO_RECORD

    labelling = T.get_labelling_requirements(con, VITC, "FR")
    assert [r.status for r in labelling] == [T.NO_RECORD]


# ------------------------------------------------------------------- supply


def test_inventory_position_reports_position_not_verdict(con):
    de = T.get_inventory_position(con, VITC, "DE")
    assert de.units_available == 26000
    assert de.covers_demand is True
    assert de.units_short == 0

    glow_us = T.get_inventory_position(con, GLOW, "US")
    assert glow_us.covers_demand is False
    assert glow_us.units_short == 31000


def test_lead_times_are_per_market_not_per_sku(con):
    by_market = {lt.market: lt.lead_time_weeks for lt in T.get_lead_times(con, VITC)}
    assert by_market == {"US": 2, "DE": 10, "UK": 2}, (
        "the DE lead time is the reformulation, and collapsing it into one "
        "SKU-level number would hide why a partial is on the table"
    )


def test_trend_window(con):
    vitc = T.get_trend_window(con, VITC)
    assert (vitc.window_status, vitc.velocity_index) == ("open", 87)
    assert T.get_trend_window(con, GLOW).window_status == "cooling"


# ----------------------------------------------------------------- retailer


def test_germany_is_fully_set_up_yet_cannot_receive_stock(con):
    """The Retailer agent's own grounding, from its own data.

    Under star topology it never sees the Regulatory finding. If item setup were
    the only signal it had, it could only conclude that every market is ready —
    and its partial lean would be borrowed from a specialist it cannot read.
    """
    de = T.get_channel_readiness(con, VITC, "DE")
    assert de.all_setup_complete is True
    assert de.accounts_awaiting_dossier == ["DTC", "Rossmann"]

    uk = T.get_channel_readiness(con, VITC, "UK")
    assert uk.all_setup_complete is True
    assert uk.accounts_awaiting_dossier == []

    us = T.get_channel_readiness(con, VITC, "US")
    assert us.all_setup_complete is True
    assert us.accounts_awaiting_dossier == []


def test_item_setup_covers_dtc_as_well_as_retail_accounts(con):
    setups = T.get_item_setup_status(con, VITC)
    channels = {(s.market, s.retailer) for s in setups}
    assert ("US", "Target") in channels
    assert ("DE", "DTC") in channels, "DTC is a target channel in every market"
    assert {s.channel for s in setups} == {"retail", "dtc"}


# ---------------------------------------------------------------- packaging


def test_artwork_and_labelling_expose_the_long_pole(con):
    assert T.get_artwork_status(con, VITC, "DE").status == "blocked"
    assert T.get_artwork_status(con, VITC, "UK").status == "approved"

    de = T.get_labelling_requirements(con, VITC, "DE")
    unmet = [r for r in de if r.status != "met"]
    assert len(unmet) == 2, "more than one gap, so 'which drives the date' is real"

    uk = T.get_labelling_requirements(con, VITC, "UK")
    assert all(r.status == "met" for r in uk)


# ------------------------------------------------------------------ toolbox


def test_toolbox_emits_every_call_as_a_tool_not_an_agent(con):
    emitted: list[dict] = []
    box = ToolBox(con, sku_id=VITC, agent="regulatory", emit=lambda **kw: emitted.append(kw))

    box.ingredient_restrictions("DE")
    box.notification_status("DE")

    assert len(emitted) == 2
    assert {e["actor_kind"] for e in emitted} == {"tool"}
    assert [e["tool"] for e in emitted] == [
        "get_ingredient_restrictions",
        "get_notification_status",
    ]
    assert all(e["duration_ms"] >= 0 for e in emitted)
    assert "exceeds limit 20%" in emitted[0]["summary"]
    assert emitted[1]["summary"] == "CPNP · in_progress"
    assert box.calls == [
        {k: v for k, v in e.items() if k in {"tool", "args", "summary", "duration_ms"}}
        for e in emitted
    ]


def test_tool_catalogue_records_why_each_is_a_tool():
    assert len(T.TOOL_CATALOGUE) == 10
    assert all(spec.why_tool for spec in T.TOOL_CATALOGUE)
    assert all(spec.kind.value == "tool" for spec in T.TOOL_CATALOGUE)


# ------------------------------------------------------------ cannot act


def test_the_warehouse_connection_cannot_write(con):
    """The system recommends; it cannot act (BUILD_SPEC §1.4, §10).

    Enforced by the connection, so it does not depend on every tool author
    remembering. No tool anywhere can write a launch decision because the
    handle they all share refuses writes.
    """
    with pytest.raises(duckdb.Error):
        con.execute("create table should_not_exist (i integer)")
    with pytest.raises(duckdb.Error):
        con.execute("update stg_launches set countdown_weeks = 0")


# ---------------------------------------------------------------- contracts


def test_finding_serialises_to_the_shape_the_ui_expects():
    finding = RegulatoryFinding(
        agent="regulatory",
        lean=Lean.SLIP,
        confidence=0.8,
        rationale="…",
        evidence=["DE: Ascorbic Acid 22% > Annex III limit 20%"],
        segments=[
            MarketReadiness(market="US", ready=True, detail="clear"),
            MarketReadiness(market="DE", ready=False, gate_type="hard", detail="gate"),
        ],
        hard_gate_markets=["DE"],
        semantic_version="launch_ready@v3",
    )
    payload = finding.model_dump(mode="json")

    assert payload["lean"] == "slip"
    assert payload["hard_gate_markets"] == ["DE"]
    assert [m["market"] for m in payload["per_market"]] == ["US", "DE"]
    assert payload["per_market"][1]["gate_type"] == "hard"
    assert "segments" not in payload and "segment" not in payload["per_market"][0]

    # and round-trips back through the same contract
    assert RegulatoryFinding.model_validate(payload).hard_gated_segments() == ["DE"]
