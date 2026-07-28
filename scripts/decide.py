"""Resume a paused run with the human's decision, from a fresh process.

This is the kill-and-resume demo (BUILD_SPEC §10) and the human gate closing
the loop (§14 item 5), in one command. The process that started the run is
gone; this one opens the same checkpoint file, finds the paused graph, and
supplies the decision from outside the system.

No tool anywhere writes the decision. It arrives here or not at all.

    ./.venv/Scripts/python.exe scripts/decide.py LAUNCH-1001 partial
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv()

from elfagent.platform import RunLimits, sqlite_checkpointer  # noqa: E402
from elfagent.platform.llm import AnthropicClient  # noqa: E402
from elfagent.platform.orchestrator import Orchestrator  # noqa: E402
from elfagent.usecases.launch_readiness.usecase import build_use_case  # noqa: E402

DECIDER = "Director of Commercialization"


async def main(launch_id: str, action: str, note: str) -> int:
    client = AnthropicClient(model=os.environ.get("ELFAGENT_MODEL", "claude-opus-5"))
    use_case = build_use_case(client)
    thread = f"run-{launch_id.lower()}"

    async with sqlite_checkpointer("data/checkpoints.sqlite") as checkpointer:
        orch = Orchestrator(
            use_case, checkpointer=checkpointer, limits=RunLimits.from_env(dict(os.environ))
        )

        before = await orch.state(thread)
        if not before["awaiting_human"]:
            print(f"  {thread} is not waiting on a human (next: {before['next']})")
            return 1

        recommended = before["values"]["recommendation"]["recommended_action"]
        findings = before["values"]["findings"]
        print(f"  recovered from checkpoint: {len(findings)} finding(s), "
              f"recommendation '{recommended}'")
        print(f"  the process that produced them is gone; this one resumes it\n")

        decision = {
            "subject_id": launch_id,
            "decided_action": action,
            "decided_by": DECIDER,
            "followed_recommendation": action == recommended,
            "note": note,
        }

        async for event in orch.submit_decision(thread, decision):
            print(f"  [{event.seq}] {event.type.value}")

        after = await orch.state(thread)

    recorded = after["values"]["decision"]
    print(f"\n  decided: {recorded['decided_action']} by {recorded['decided_by']}")
    print(f"  followed recommendation: {recorded['followed_recommendation']}")
    print(f"  awaiting_human now: {after['awaiting_human']}")
    return 0


if __name__ == "__main__":
    launch = sys.argv[1] if len(sys.argv) > 1 else "LAUNCH-1001"
    act = sys.argv[2] if len(sys.argv) > 2 else "partial"
    reason = sys.argv[3] if len(sys.argv) > 3 else ""
    raise SystemExit(asyncio.run(main(launch, act, reason)))
