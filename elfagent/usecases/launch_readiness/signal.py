"""The signal — DETERMINISTIC, and not an agent (BUILD_SPEC §2, §5.5).

A scheduled check compares each launch's countdown against a threshold and fires
the flow with a launch_id. There is no model in this path and no interpretation:
statistics decide what fires, agents decide what it means.

This is the first thing to point at in the demo. It would have been easy to
call it a "monitoring agent" — it is a date comparison, and calling it what it
is costs nothing and buys the credibility everything else rests on.
"""

from __future__ import annotations

from .tools.launches import LaunchRecord, launches_at_gate
from .warehouse import warehouse


def detect(db_path: str | None = None) -> list[LaunchRecord]:
    """Launches that have reached T-minus-4-weeks. Fires the flow."""
    with warehouse(db_path) as con:
        return launches_at_gate(con)


def queue(db_path: str | None = None) -> list[dict]:
    """The launch queue as the front end consumes it."""
    return [record.as_subject() for record in detect(db_path)]
