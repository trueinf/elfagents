"""Thin FastAPI over the orchestrator (BUILD_SPEC §12 step 6).

The one rule that shapes this module: **the run endpoint streams**. The live
orchestration view exists to show four agents lighting up and returning in
parallel, in real time, and it can only do that if events reach the browser as
they happen. A poll-when-done endpoint would be easier to write and would
quietly kill the demo's most compelling moment — so `/runs/{id}/stream` is
Server-Sent Events over the LangGraph event stream, and there is deliberately
no synchronous "run and return the result" alternative to reach for.

The API adds no reasoning of its own. It exposes the queue, the stream, the
recorded trace, and the human decision. Nothing here can decide anything.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

load_dotenv()

from elfagent.platform import RunLimits  # noqa: E402
from elfagent.platform.llm import AnthropicClient  # noqa: E402
from elfagent.platform.orchestrator import (  # noqa: E402
    Orchestrator,
    sqlite_checkpointer,
)
from elfagent.platform.tracing import configure_tracing  # noqa: E402
from elfagent.usecases.launch_readiness import signal  # noqa: E402
from elfagent.usecases.launch_readiness.usecase import build_use_case  # noqa: E402

CHECKPOINTS = "data/checkpoints.sqlite"

# Captured events per run, in order. The trace drawer renders these — the same
# events the live view animated against, so the in-product trace is never
# reconstructed from a different source than the thing it depicts (§4.1).
TRACE: dict[str, list[dict[str, Any]]] = {}


class Decision(BaseModel):
    decided_action: str
    decided_by: str = "Director of Commercialization"
    note: str = ""
    per_market: list[dict[str, Any]] = Field(default_factory=list)


def _thread(launch_id: str) -> str:
    return f"run-{launch_id.lower()}"


def _register(api: FastAPI) -> None:
    # ------------------------------------------------------------- queue

    @api.get("/api/launches")
    async def launches() -> list[dict[str, Any]]:
        """The launch queue — output of the deterministic countdown detector.

        No model is involved in producing this list. A scheduled check compares
        each launch's countdown against a threshold; that is the whole of it.
        """
        return signal.queue()

    @api.get("/api/usecase")
    async def usecase(request: Request) -> dict[str, Any]:
        """What this use case is made of — which components are agents and
        which are tools, with the reason recorded for each.

        The UI renders the tool-vs-agent distinction from this rather than from
        a hardcoded list, so the demo's thesis reads data the codebase holds.
        """
        return request.app.state.use_case.anatomy()

    # ------------------------------------------------------------ stream

    @api.get("/api/runs/{launch_id}/stream")
    async def stream(launch_id: str, request: Request):
        """Run the flow, streaming events as they happen.

        This is surface 1 of §4.1. Each event goes out the moment the graph
        emits it, which is what lets the front end animate a fan-out that is
        genuinely concurrent rather than replaying a finished run.
        """
        subject = next(
            (q for q in signal.queue() if q["launch_id"] == launch_id), None
        )
        if subject is None:
            raise HTTPException(404, f"{launch_id} is not at the gate")

        thread = _thread(launch_id)
        TRACE[thread] = []
        orchestrator = request.app.state.orchestrator

        async def publish():
            async for event in orchestrator.astream(
                launch_id, subject=subject, thread_id=thread
            ):
                payload = event.model_dump(mode="json")
                TRACE[thread].append(payload)
                yield {"event": event.type.value, "data": json.dumps(payload)}

        return EventSourceResponse(publish())

    # ------------------------------------------------------------- state

    @api.get("/api/runs/{launch_id}")
    async def run_state(launch_id: str, request: Request) -> dict[str, Any]:
        state = await request.app.state.orchestrator.state(_thread(launch_id))
        if not state["values"]:
            raise HTTPException(404, f"no run on record for {launch_id}")
        return state

    @api.get("/api/runs/{launch_id}/trace")
    async def trace(launch_id: str) -> list[dict[str, Any]]:
        """The captured event stream, for the trace drawer."""
        thread = _thread(launch_id)
        if thread not in TRACE:
            raise HTTPException(404, f"no captured trace for {launch_id}")
        return TRACE[thread]

    # -------------------------------------------------------- human gate

    @api.post("/api/runs/{launch_id}/decision")
    async def decide(
        launch_id: str, decision: Decision, request: Request
    ) -> dict[str, Any]:
        """Record the human's decision and resume the graph.

        This endpoint is the only way a decision enters the system. No tool
        anywhere writes one and nothing upstream of the gate can supply it —
        which is what "the system recommends, it cannot act" means in practice.
        """
        thread = _thread(launch_id)
        orchestrator = request.app.state.orchestrator
        state = await orchestrator.state(thread)
        if not state["awaiting_human"]:
            raise HTTPException(409, f"{launch_id} is not waiting on a decision")

        recommended = (state["values"].get("recommendation") or {}).get(
            "recommended_action"
        )
        payload = {
            "subject_id": launch_id,
            "decided_action": decision.decided_action,
            "decided_by": decision.decided_by,
            "followed_recommendation": decision.decided_action == recommended,
            "note": decision.note,
            "per_market": decision.per_market,
        }

        captured = TRACE.setdefault(thread, [])
        last_seq = captured[-1]["seq"] if captured else 0
        async for event in orchestrator.submit_decision(
            thread, payload, start_seq=last_seq
        ):
            captured.append(event.model_dump(mode="json"))

        after = await orchestrator.state(thread)
        return {"decision": after["values"].get("decision"), "state": after}

    @api.get("/api/health")
    async def health(request: Request) -> dict[str, Any]:
        return {
            "ok": True,
            "use_case": request.app.state.use_case.key,
            "agents": [s.name for s in request.app.state.use_case.specialists],
        }


def create_app(client: Any = None, *, checkpoints: str = CHECKPOINTS) -> FastAPI:
    """Build the app around a model client.

    Parameterised so the test suite can pass a scripted client and exercise
    every endpoint — including the stream — without a key, a network call, or
    a real model run.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Hold one checkpointer and one orchestrator open for the process.

        The checkpointer is a file so a run survives this process dying — that
        is the point of it, and the reason the decision endpoint can resume a
        run this process never started.
        """
        print(f"  {configure_tracing().describe()}")
        async with sqlite_checkpointer(checkpoints) as checkpointer:
            model = client or AnthropicClient(
                model=os.environ.get("ELFAGENT_MODEL", "claude-opus-5")
            )
            use_case = build_use_case(
                model, effort=os.environ.get("ELFAGENT_EFFORT", "high")
            )
            app.state.use_case = use_case
            app.state.orchestrator = Orchestrator(
                use_case,
                checkpointer=checkpointer,
                limits=RunLimits.from_env(dict(os.environ)),
            )
            yield

    # Dev origins plus whatever the deployed front end is served from.
    # ELFAGENT_ALLOWED_ORIGINS is a comma-separated list; without it a
    # Netlify-hosted UI is blocked by the browser before it reaches an endpoint.
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    extra = os.environ.get("ELFAGENT_ALLOWED_ORIGINS", "").strip()
    if extra:
        origins += [o.strip() for o in extra.split(",") if o.strip()]

    api = FastAPI(title="elfagent", version="0.1.0", lifespan=lifespan)
    api.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _register(api)
    return api


app = create_app()
