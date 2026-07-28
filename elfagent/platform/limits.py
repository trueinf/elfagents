"""Hard stop conditions (BUILD_SPEC §10).

Caps live in code, not in a prompt. A prompt asking a model to be frugal is a
request; this is a ceiling. A loop bug cannot run up a bill because the ledger
raises before the next call is made, not after the invoice arrives.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class HardStop(Exception):
    """Raised when a run hits a ceiling. Terminates the run; never retried."""

    def __init__(self, limit: str, detail: str) -> None:
        self.limit = limit
        self.detail = detail
        super().__init__(f"hard stop [{limit}]: {detail}")


@dataclass(frozen=True)
class RunLimits:
    """Ceilings for a single orchestration run."""

    max_steps_per_agent: int = 8
    max_usd_per_run: float = 1.00
    max_wall_seconds: float = 180.0

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "RunLimits":
        return cls(
            max_steps_per_agent=int(env.get("ELFAGENT_MAX_STEPS_PER_AGENT", 8)),
            max_usd_per_run=float(env.get("ELFAGENT_MAX_USD_PER_RUN", 1.00)),
            max_wall_seconds=float(env.get("ELFAGENT_MAX_WALL_SECONDS", 180.0)),
        )


@dataclass
class AgentSpend:
    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0


@dataclass
class SpendLedger:
    """Tracks spend across a run and refuses to let it exceed the ceiling.

    Shared by every specialist in the run, so four agents cannot each stay under
    an individual cap while collectively blowing through the total.
    """

    limits: RunLimits
    started_at: float = field(default_factory=time.monotonic)
    by_agent: dict[str, AgentSpend] = field(default_factory=dict)

    def _slot(self, agent: str) -> AgentSpend:
        return self.by_agent.setdefault(agent, AgentSpend())

    def check_wall_clock(self) -> None:
        elapsed = time.monotonic() - self.started_at
        if elapsed > self.limits.max_wall_seconds:
            raise HardStop(
                "max_wall_seconds",
                f"run exceeded {self.limits.max_wall_seconds}s (at {elapsed:.1f}s)",
            )

    def begin_step(self, agent: str) -> int:
        """Call before every model invocation. Raises rather than making the call."""
        self.check_wall_clock()
        slot = self._slot(agent)
        if slot.steps >= self.limits.max_steps_per_agent:
            raise HardStop(
                "max_steps_per_agent",
                f"{agent} reached {self.limits.max_steps_per_agent} steps",
            )
        slot.steps += 1
        return slot.steps

    def charge(
        self, agent: str, *, input_tokens: int, output_tokens: int, usd: float
    ) -> None:
        """Record what a call actually cost, then check the ceiling."""
        slot = self._slot(agent)
        slot.input_tokens += input_tokens
        slot.output_tokens += output_tokens
        slot.usd += usd
        if self.total_usd > self.limits.max_usd_per_run:
            raise HardStop(
                "max_usd_per_run",
                f"run spend ${self.total_usd:.4f} exceeded "
                f"${self.limits.max_usd_per_run:.2f}",
            )

    @property
    def total_usd(self) -> float:
        return sum(s.usd for s in self.by_agent.values())

    @property
    def total_tokens(self) -> int:
        return sum(s.input_tokens + s.output_tokens for s in self.by_agent.values())

    def snapshot(self) -> dict:
        return {
            "total_usd": round(self.total_usd, 6),
            "total_tokens": self.total_tokens,
            "elapsed_seconds": round(time.monotonic() - self.started_at, 3),
            "limits": {
                "max_steps_per_agent": self.limits.max_steps_per_agent,
                "max_usd_per_run": self.limits.max_usd_per_run,
                "max_wall_seconds": self.limits.max_wall_seconds,
            },
            "by_agent": {
                name: {
                    "steps": s.steps,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "usd": round(s.usd, 6),
                }
                for name, s in self.by_agent.items()
            },
        }
