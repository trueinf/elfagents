"""Agent registry — where use cases plug into the shell (BUILD_SPEC §4, §7).

The registry is also where the tool-vs-agent distinction becomes STRUCTURAL
rather than narrated. Every component is registered as one or the other, with
the reason recorded, and the UI renders that classification from the registry.
The demo can point at a tool and say "this is a tool, not an agent, and here's
why" because the codebase already says so — not because someone remembered the
line (BUILD_SPEC §1.1, §5.5).

The test applied to every component: write the question the orchestrator asks
it. If the answer is deterministic, it is a TOOL. If it requires interpretation,
weighing, or judgment under ambiguity, it is an AGENT.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol

from .limits import SpendLedger


class ActorKind(str, Enum):
    AGENT = "agent"
    TOOL = "tool"


@dataclass(frozen=True)
class ToolSpec:
    """A deterministic lookup. Same inputs, same answer, no interpretation."""

    name: str
    description: str
    why_tool: str
    kind: ActorKind = ActorKind.TOOL


@dataclass(frozen=True)
class SpecialistContext:
    """Everything a specialist is given.

    Note what is NOT here: the other specialists' findings. A specialist cannot
    read them because it is never handed them. Star topology is enforced by the
    shape of this object rather than by a convention someone has to remember —
    which is the point of choosing a star over peer-to-peer in the first place
    (BUILD_SPEC §4: Berkeley MAST, 41-86.7% failure rates concentrated in
    inter-agent hand-offs).
    """

    subject_id: str
    subject: dict[str, Any]
    ledger: SpendLedger
    semantic_version: str
    emit: Callable[..., None]


class SpecialistFn(Protocol):
    def __call__(self, ctx: SpecialistContext) -> Awaitable[Any]: ...


class JudgmentFn(Protocol):
    def __call__(
        self, ctx: SpecialistContext, findings: list[Any]
    ) -> Awaitable[Any]: ...


class SignalFn(Protocol):
    """Deterministic. Decides WHETHER to fire, never WHAT it means."""

    def __call__(self) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class AgentSpec:
    """A specialist. Registered as an agent because its question has no single
    deterministic answer.

    `finding_model` is the concrete contract this specialist is required to
    return. It is declared rather than inferred because graph state crosses a
    serialisation boundary at every checkpoint — a restored run comes back as
    plain JSON, and the type has to be re-established from somewhere. Declaring
    it here means the contract is re-validated on the way out of a specialist
    AND on the way in to judgment, including after a process restart.
    """

    name: str
    question: str
    why_agent: str
    run: SpecialistFn
    tools: tuple[str, ...] = ()
    finding_model: type | None = None
    kind: ActorKind = ActorKind.AGENT


@dataclass(frozen=True)
class UseCase:
    """One use case as configuration on the shell.

    Adding campaign-to-shelf, GEO or deductions means constructing one of these
    — a lean enum, a signal, some specialists, a judgment function — not
    modifying anything in elfagent/platform/.
    """

    key: str
    title: str
    subject_label: str
    signal: SignalFn
    specialists: tuple[AgentSpec, ...]
    judgment: JudgmentFn
    recommendation_model: type | None = None
    tools: tuple[ToolSpec, ...] = ()
    semantic_version: str = "unversioned"

    def __post_init__(self) -> None:
        names = [s.name for s in self.specialists]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate specialist names in use case {self.key!r}")
        if not self.specialists:
            raise ValueError(f"use case {self.key!r} registers no specialists")

        # Typed contracts are non-negotiable (BUILD_SPEC §6, §10), so a use
        # case that has not declared them is rejected at registration rather
        # than discovered mid-run.
        undeclared = [s.name for s in self.specialists if s.finding_model is None]
        if undeclared:
            raise ValueError(
                f"use case {self.key!r}: specialists {undeclared} declare no "
                "finding_model; every hand-off must carry a typed contract"
            )
        if self.recommendation_model is None:
            raise ValueError(
                f"use case {self.key!r} declares no recommendation_model"
            )

    def finding_model_for(self, agent: str) -> type:
        spec = next((s for s in self.specialists if s.name == agent), None)
        if spec is None or spec.finding_model is None:
            raise KeyError(f"no finding contract registered for agent {agent!r}")
        return spec.finding_model

    def anatomy(self) -> dict[str, Any]:
        """What this use case is made of, for the UI and the demo narration."""
        return {
            "key": self.key,
            "title": self.title,
            "subject_label": self.subject_label,
            "semantic_version": self.semantic_version,
            "agents": [
                {
                    "name": a.name,
                    "kind": a.kind.value,
                    "question": a.question,
                    "why_agent": a.why_agent,
                    "tools": list(a.tools),
                }
                for a in self.specialists
            ],
            "tools": [
                {
                    "name": t.name,
                    "kind": t.kind.value,
                    "description": t.description,
                    "why_tool": t.why_tool,
                }
                for t in self.tools
            ],
        }


@dataclass
class Registry:
    """Use cases available to the platform."""

    _use_cases: dict[str, UseCase] = field(default_factory=dict)

    def register(self, use_case: UseCase) -> UseCase:
        if use_case.key in self._use_cases:
            raise ValueError(f"use case {use_case.key!r} already registered")
        self._use_cases[use_case.key] = use_case
        return use_case

    def get(self, key: str) -> UseCase:
        if key not in self._use_cases:
            known = ", ".join(sorted(self._use_cases)) or "(none)"
            raise KeyError(f"unknown use case {key!r}; registered: {known}")
        return self._use_cases[key]

    def keys(self) -> list[str]:
        return sorted(self._use_cases)

    def anatomy(self) -> list[dict[str, Any]]:
        return [self._use_cases[k].anatomy() for k in self.keys()]


registry = Registry()
