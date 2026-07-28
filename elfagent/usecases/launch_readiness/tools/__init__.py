"""The TOOLS of the launch-readiness use case.

Every component in here is a tool, not an agent, and the catalogue below records
why for each one. The test applied (BUILD_SPEC §5): write the question the
orchestrator asks it — if the answer is deterministic, it is a tool.

This catalogue is what the registry publishes and the UI renders, so the demo's
"this is a tool, not an agent, and here's why" moment is reading data the
codebase already holds rather than reciting a line someone remembered.
"""

from __future__ import annotations

from elfagent.platform.registry import ToolSpec

from .launches import LaunchRecord, all_launches, get_launch, launches_at_gate
from .packaging import (
    ArtworkState,
    LabellingRequirement,
    get_artwork_status,
    get_labelling_requirements,
)
from .regulatory import (
    AnnexStatus,
    IngredientRestriction,
    NotificationState,
    get_ingredient_restrictions,
    get_notification_status,
)
from .retailer import (
    ChannelReadiness,
    ItemSetup,
    get_channel_readiness,
    get_item_setup_status,
)
from .sentinels import NO_RECORD
from .supply import (
    InventoryPosition,
    LeadTime,
    TrendWindow,
    get_inventory_position,
    get_lead_times,
    get_trend_window,
)

TOOL_CATALOGUE: tuple[ToolSpec, ...] = (
    ToolSpec(
        "launches_at_gate",
        "Launches that have reached the countdown threshold.",
        "A date comparison. Nothing is being interpreted — this is what fires "
        "the flow, and no LLM decides that a launch is due for review.",
    ),
    ToolSpec(
        "get_ingredient_restrictions",
        "Formula ingredients with the restriction applying in a market, and "
        "whether the concentration exceeds it.",
        "A join and a numeric comparison. Whether an exceedance is fatal or "
        "fixable is judgment and stays with the agent.",
    ),
    ToolSpec(
        "get_notification_status",
        "Pre-market notification portal and filing status for a market.",
        "A row lookup. Which portal applies is a fact; what an in-progress "
        "filing means for a ship date is not.",
    ),
    ToolSpec(
        "get_inventory_position",
        "Units available against units required in a market.",
        "Subtraction. What a shortfall costs against an open window is the "
        "agent's call.",
    ),
    ToolSpec(
        "get_lead_times",
        "Replenishment lead time per market.",
        "A stored value. Whether the lead time can be absorbed is judgment.",
    ),
    ToolSpec(
        "get_trend_window",
        "Social trend window state and velocity index for a SKU.",
        "A row lookup. Pricing the cost of delay against it is not.",
    ),
    ToolSpec(
        "get_item_setup_status",
        "Item setup state per retail account and owned channel.",
        "A status column. Whether an incomplete market blocks the others is "
        "the agent's question.",
    ),
    ToolSpec(
        "get_channel_readiness",
        "Channel counts and accounts still awaiting a compliance dossier.",
        "Counting rows. Whether a partial launch is coherent or merely "
        "fragmented is judgment.",
    ),
    ToolSpec(
        "get_artwork_status",
        "Packaging artwork state for a market.",
        "A status column, one row.",
    ),
    ToolSpec(
        "get_labelling_requirements",
        "Labelling requirements and their state for a market.",
        "A row set. Which unmet requirement actually drives the timeline is "
        "the agent's judgment.",
    ),
)

__all__ = [
    "NO_RECORD",
    "TOOL_CATALOGUE",
    "AnnexStatus",
    "ArtworkState",
    "ChannelReadiness",
    "IngredientRestriction",
    "InventoryPosition",
    "ItemSetup",
    "LabellingRequirement",
    "LaunchRecord",
    "LeadTime",
    "NotificationState",
    "TrendWindow",
    "all_launches",
    "get_artwork_status",
    "get_channel_readiness",
    "get_ingredient_restrictions",
    "get_inventory_position",
    "get_item_setup_status",
    "get_labelling_requirements",
    "get_lead_times",
    "get_notification_status",
    "get_trend_window",
    "launches_at_gate",
    "get_launch",
]
