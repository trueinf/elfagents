"""Run one launch through the graph against the real model.

Development harness for BUILD_SPEC §12 step 3 — the API layer (step 6) will do
this over SSE. Here it just prints the event stream as it arrives, which is the
same data the live orchestration view will animate against.

    ./.venv/Scripts/python.exe scripts/run_once.py [LAUNCH-1001]
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
from elfagent.platform.events import EventType  # noqa: E402
from elfagent.platform.llm import AnthropicClient  # noqa: E402
from elfagent.platform.orchestrator import Orchestrator  # noqa: E402
from elfagent.platform.tracing import configure_tracing  # noqa: E402
from elfagent.usecases.launch_readiness import signal  # noqa: E402
from elfagent.usecases.launch_readiness.usecase import build_use_case  # noqa: E402


async def main(launch_id: str) -> int:
    tracing = configure_tracing()
    print(f"  {tracing.describe()}")

    queue = signal.queue()
    subject = next((q for q in queue if q["launch_id"] == launch_id), None)
    if subject is None:
        print(f"  {launch_id} is not at the gate. Queue: "
              f"{[q['launch_id'] for q in queue]}")
        return 1

    print(f"  signal fired: {launch_id} — {subject['sku_name']} "
          f"— markets {', '.join(subject['target_markets'])} "
          f"— T-minus {subject['countdown_weeks']} weeks\n")

    client = AnthropicClient(model=os.environ.get("ELFAGENT_MODEL", "claude-opus-5"))
    use_case = build_use_case(client, effort=os.environ.get("ELFAGENT_EFFORT", "high"))
    limits = RunLimits.from_env(dict(os.environ))

    async with sqlite_checkpointer("data/checkpoints.sqlite") as checkpointer:
        orch = Orchestrator(use_case, checkpointer=checkpointer, limits=limits)
        thread = f"run-{launch_id.lower()}"

        async for event in orch.astream(launch_id, subject=subject, thread_id=thread):
            kind = event.actor_kind or "-"
            head = f"  [{event.seq:>2}] {event.type.value:<18} {kind:<6}"

            if event.type is EventType.AGENT_TOOL_CALL:
                print(f"{head} {event.payload.get('tool')}"
                      f"({event.payload.get('args', {}).get('market', '')}) "
                      f"-> {event.payload.get('summary')} "
                      f"[{event.payload.get('duration_ms')}ms]")
            elif event.type is EventType.AGENT_RETURNED:
                finding = event.payload["finding"]
                print(f"{head} {event.agent} -> lean={finding['lean']} "
                      f"confidence={finding['confidence']}")
                print(f"\n       rationale: {finding['rationale']}\n")
                for market in finding["per_market"]:
                    print(f"       {market['market']}: ready={market['ready']} "
                          f"gate={market['gate_type']} — {market['detail']}")
                for item in finding["evidence"]:
                    print(f"       evidence: {item}")
                print()
            elif event.type is EventType.JUDGMENT_STARTED:
                print(f"{head} reconciling {event.payload['finding_count']} findings "
                      f"— leans {event.payload['leans']}")
            elif event.type is EventType.JUDGMENT_RETURNED:
                rec = event.payload["recommendation"]
                print(f"{head} -> {rec['recommended_action'].upper()} "
                      f"(confidence {rec['confidence']})")
                print(f"\n       {rec['reconciliation']}\n")
                for market in rec["per_market_action"]:
                    verdict = "GO" if market["ready"] else "HOLD"
                    print(f"       {market['market']}: {verdict} — {market['detail']}")
                print()
                for item in rec["dissent"]:
                    print(f"       DISSENT: {item}")
                print()
            elif event.type is EventType.AWAITING_HUMAN:
                print(f"{head} graph paused — a human must decide")
            elif event.type is EventType.RUN_FAILED:
                print(f"{head} {event.payload}")
            else:
                print(f"{head} {event.agent or ''}")

        state = await orch.state(thread)

    spend = state["values"].get("spend", {})
    print(f"\n  spend: ${spend.get('total_usd', 0):.4f} of "
          f"${limits.max_usd_per_run:.2f} cap · "
          f"{spend.get('total_tokens', 0)} tokens · "
          f"{spend.get('elapsed_seconds', 0)}s")
    print(f"  awaiting_human: {state['awaiting_human']}  "
          f"(nothing wrote a decision: {state['values'].get('decision')})")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "LAUNCH-1001"
    raise SystemExit(asyncio.run(main(target)))
