"""Launch readiness, assembled as configuration on the platform shell.

This module is the whole of the plug-in surface: it names the specialists,
points at the deterministic signal, declares the tool catalogue, and supplies a
judgment function. Nothing in elfagent/platform/ changes to accommodate it.

Adding the other three use cases means writing a module like this one — a lean
vocabulary, a signal, some specialists, a judgment function — not editing the
shell.
"""

from __future__ import annotations

from elfagent.platform.registry import AgentSpec, UseCase

from . import judgment as judgment_module
from .contracts import (
    LaunchRecommendation,
    PackagingFinding,
    RegulatoryFinding,
    RetailerFinding,
    SupplyFinding,
)
from .signal import detect
from .specialists import packaging, regulatory, retailer, supply
from .tools import TOOL_CATALOGUE

SEMANTIC_VERSION = "launch_ready@v3"

# Each specialist paired with the contract it is required to return. The
# contract is declared here rather than inferred, so a specialist that returns
# the wrong shape fails at the boundary instead of downstream.
_SPECIALISTS = (
    (regulatory, RegulatoryFinding),
    (supply, SupplyFinding),
    (retailer, RetailerFinding),
    (packaging, PackagingFinding),
)


def build_use_case(
    client, *, db_path: str | None = None, effort: str = "high"
) -> UseCase:
    """Assemble the use case around a model client."""
    return UseCase(
        key="launch_readiness",
        title="Launch Readiness Council",
        subject_label="launch",
        signal=lambda: [record.as_subject() for record in detect(db_path)],
        specialists=tuple(
            AgentSpec(
                name=module.AGENT,
                question=module.QUESTION,
                why_agent=module.WHY_AGENT,
                run=module.build(client, db_path=db_path, effort=effort),
                tools=module.TOOL_NAMES,
                finding_model=contract,
            )
            for module, contract in _SPECIALISTS
        ),
        judgment=judgment_module.build(client, effort=effort),
        recommendation_model=LaunchRecommendation,
        tools=TOOL_CATALOGUE,
        semantic_version=SEMANTIC_VERSION,
    )
