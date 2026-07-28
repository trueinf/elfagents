"""LangSmith wiring (BUILD_SPEC §4.1 surface 3, §10).

Wired as the graph is built, not retrofitted.

LangSmith's job here is twofold: it is the recording backend, and it is the
"is this real?" proof surface. When a technical viewer asks whether the in-app
trace is genuine, we flip to the actual LangSmith run and show the same
execution in raw tooling.

What LangSmith is NOT is the data source for the live orchestration view. It is
after-the-fact and cannot show execution as it happens. That view is fed by the
LangGraph event stream — see elfagent/platform/events.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TracingConfig:
    enabled: bool
    project: str
    reason: str = ""

    def describe(self) -> str:
        if self.enabled:
            return f"LangSmith tracing ON -> project {self.project!r}"
        return f"LangSmith tracing OFF ({self.reason})"


def configure_tracing(env: dict[str, str] | None = None) -> TracingConfig:
    """Read tracing config from the environment and apply it.

    Degrades honestly: with no API key, tracing is off and says so rather than
    silently pretending to record. Surfaces 1 and 2 still work — they are fed by
    the LangGraph stream, not by LangSmith.
    """
    env = dict(os.environ if env is None else env)

    project = env.get("LANGSMITH_PROJECT", "elfagent-launch-readiness")
    requested = env.get("LANGSMITH_TRACING", "").lower() in {"1", "true", "yes"}
    api_key = env.get("LANGSMITH_API_KEY", "").strip()

    if not requested:
        return TracingConfig(False, project, "LANGSMITH_TRACING not enabled")
    if not api_key:
        return TracingConfig(False, project, "LANGSMITH_API_KEY not set")

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_PROJECT"] = project
    os.environ["LANGSMITH_API_KEY"] = api_key
    return TracingConfig(True, project)


def run_url(run_id: str) -> str | None:
    """Deep link to a run in the LangSmith console — the proof surface.

    Returns None when tracing is off, so callers surface "not recorded" instead
    of a link that goes nowhere.
    """
    try:
        from langsmith import Client
    except ImportError:
        return None

    if os.environ.get("LANGSMITH_TRACING", "").lower() not in {"1", "true", "yes"}:
        return None

    try:
        return Client().get_run_url(run_id=run_id)
    except Exception:
        return None
