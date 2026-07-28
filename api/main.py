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

Three things exist only because this is reachable over the internet, and each
is a real failure mode rather than ceremony:

* **A shared access key.** Every run costs real model credit. An unauthenticated
  public URL is a button that spends money on behalf of whoever finds it.
* **A process-wide spend ceiling.** The per-run cap bounds one run; it does
  nothing about a hundred of them. This bounds the deployment.
* **A thread per run, not per launch.** Deriving the graph thread from the
  launch id alone means two viewers opening the same launch share one run and
  overwrite each other — invisible with one user, immediate with two.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, HTTPException, Request, Response
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

CHECKPOINTS = os.environ.get("ELFAGENT_CHECKPOINTS", "data/checkpoints.sqlite")
COOKIE = "elfagent_access"

# Captured events per run thread. The trace drawer renders these — the same
# events the live view animated against, so the in-product trace is never
# reconstructed from a different source than the thing it depicts (§4.1).
TRACE: dict[str, list[dict[str, Any]]] = {}
LAUNCH_OF: dict[str, str] = {}


class Decision(BaseModel):
    decided_action: str
    decided_by: str = "Director of Commercialization"
    note: str = ""
    per_market: list[dict[str, Any]] = Field(default_factory=list)


class Budget:
    """A ceiling for the whole deployment, not just one run.

    `RunLimits.max_usd_per_run` stops a single runaway loop. It says nothing
    about volume, and volume is what a public URL produces.
    """

    def __init__(self) -> None:
        self.max_usd = float(os.environ.get("ELFAGENT_MAX_USD_TOTAL", "25.0"))
        self.max_concurrent = int(os.environ.get("ELFAGENT_MAX_CONCURRENT_RUNS", "3"))
        self.spent = 0.0
        self.active = 0

    def admit(self) -> None:
        if self.spent >= self.max_usd:
            raise HTTPException(
                429,
                f"deployment spend ceiling reached (${self.spent:.2f} of "
                f"${self.max_usd:.2f}). Raise ELFAGENT_MAX_USD_TOTAL to continue.",
            )
        if self.active >= self.max_concurrent:
            raise HTTPException(
                429,
                f"{self.active} runs already in flight (limit "
                f"{self.max_concurrent}). Try again shortly.",
            )
        self.active += 1

    def release(self, usd: float) -> None:
        self.active = max(0, self.active - 1)
        self.spent += usd


def _authorise(supplied: str | None) -> None:
    """Check the shared access key.

    An unset key means the deployment is open — correct for local development,
    wrong for anything with a public URL, so it is logged loudly at startup
    rather than passing silently.
    """
    expected = os.environ.get("ELFAGENT_ACCESS_KEY", "")
    if not expected:
        return
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "not authorised")


def _register(api: FastAPI) -> None:
    # -------------------------------------------------------------- auth

    @api.post("/api/auth")
    async def authenticate(
        body: dict, request: Request, response: Response
    ) -> dict[str, bool]:
        """Exchange the shared key for a cookie.

        A cookie rather than a header because EventSource cannot set headers,
        and rather than a query parameter because a key in a URL ends up in
        logs, history and referrers.

        The flags follow the scheme rather than being hardcoded. Deployed, the
        front end and API are different origins, so the cookie must be
        SameSite=None — which browsers only accept alongside Secure. Over plain
        HTTP locally that same pair is rejected and the cookie is silently
        never sent, so dev gets Lax instead.
        """
        expected = os.environ.get("ELFAGENT_ACCESS_KEY", "")
        supplied = str(body.get("key", ""))
        if expected and not secrets.compare_digest(supplied, expected):
            raise HTTPException(401, "incorrect key")

        cross_site = request.url.scheme == "https"
        response.set_cookie(
            COOKIE,
            supplied,
            httponly=True,
            samesite="none" if cross_site else "lax",
            secure=cross_site,
            max_age=60 * 60 * 8,
        )
        return {"ok": True}

    @api.get("/api/health")
    async def health(request: Request) -> dict[str, Any]:
        """Unauthenticated on purpose — hosting platforms probe it.

        Reports degraded rather than failing. A health check that dies on a
        missing key gets the container killed and replaced, over and over,
        with the reason never surfacing.
        """
        state = request.app.state
        budget: Budget = state.budget
        problems = []
        if getattr(state, "model_error", None):
            problems.append(f"model client: {state.model_error}")
        if not getattr(state, "warehouse_ok", True):
            problems.append(
                "warehouse missing. Set ELFAGENT_WAREHOUSE, or check that a "
                "mounted volume has not replaced the directory the image "
                "built it into."
            )

        return {
            "ok": not problems,
            "problems": problems,
            "use_case": state.use_case.key,
            "agents": [s.name for s in state.use_case.specialists],
            "auth_required": bool(os.environ.get("ELFAGENT_ACCESS_KEY", "")),
            "budget": {
                "spent_usd": round(budget.spent, 4),
                "ceiling_usd": budget.max_usd,
                "active_runs": budget.active,
            },
        }

    # ------------------------------------------------------------- queue

    @api.get("/api/launches")
    async def launches(
        elfagent_access: str | None = Cookie(default=None),
    ) -> list[dict[str, Any]]:
        """The launch queue — output of the deterministic countdown detector.

        No model is involved in producing this list. A scheduled check compares
        each launch's countdown against a threshold; that is the whole of it.
        """
        _authorise(elfagent_access)
        return signal.queue()

    @api.get("/api/usecase")
    async def usecase(
        request: Request, elfagent_access: str | None = Cookie(default=None)
    ) -> dict[str, Any]:
        """Which components are agents and which are tools, with the reason.

        The UI renders the tool-vs-agent distinction from this rather than from
        a hardcoded list, so the demo's thesis reads data the codebase holds.
        """
        _authorise(elfagent_access)
        return request.app.state.use_case.anatomy()

    # ------------------------------------------------------------ stream

    @api.get("/api/runs/{launch_id}/stream")
    async def stream(
        launch_id: str,
        request: Request,
        elfagent_access: str | None = Cookie(default=None),
    ):
        """Run the flow, streaming events as they happen.

        This is surface 1 of §4.1. Each event goes out the moment the graph
        emits it, which is what lets the front end animate a fan-out that is
        genuinely concurrent rather than replaying a finished run.

        Each call gets its own thread. Two people opening the same launch get
        two independent runs.
        """
        _authorise(elfagent_access)
        if getattr(request.app.state, "model_error", None):
            raise HTTPException(
                503,
                f"no model client: {request.app.state.model_error}. "
                "Check ANTHROPIC_API_KEY on the API service.",
            )
        subject = next(
            (q for q in signal.queue() if q["launch_id"] == launch_id), None
        )
        if subject is None:
            raise HTTPException(404, f"{launch_id} is not at the gate")

        budget: Budget = request.app.state.budget
        budget.admit()

        thread = f"run-{launch_id.lower()}-{uuid.uuid4().hex[:8]}"
        TRACE[thread] = []
        LAUNCH_OF[thread] = launch_id
        orchestrator = request.app.state.orchestrator

        async def publish():
            spent = 0.0
            try:
                async for event in orchestrator.astream(
                    launch_id, subject=subject, thread_id=thread
                ):
                    payload = event.model_dump(mode="json")
                    TRACE[thread].append(payload)
                    spend = payload["payload"].get("spend")
                    if isinstance(spend, dict):
                        spent = spend.get("total_usd", spent)
                    yield {"event": event.type.value, "data": json.dumps(payload)}
            except asyncio.CancelledError:
                # Browser went away mid-run. The work is checkpointed, so the
                # run is resumable rather than lost.
                raise
            finally:
                budget.release(spent)

        return EventSourceResponse(publish())

    # ---------------------------------------------- state / trace / gate

    @api.get("/api/runs/thread/{thread_id}")
    async def run_state(
        thread_id: str,
        request: Request,
        elfagent_access: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _authorise(elfagent_access)
        state = await request.app.state.orchestrator.state(thread_id)
        if not state["values"]:
            raise HTTPException(404, f"no run on record for {thread_id}")
        return {**state, "launch_id": LAUNCH_OF.get(thread_id)}

    @api.get("/api/runs/thread/{thread_id}/trace")
    async def trace(
        thread_id: str, elfagent_access: str | None = Cookie(default=None)
    ) -> list[dict[str, Any]]:
        """The captured event stream, for the trace drawer."""
        _authorise(elfagent_access)
        if thread_id not in TRACE:
            raise HTTPException(404, f"no captured trace for {thread_id}")
        return TRACE[thread_id]

    @api.post("/api/runs/thread/{thread_id}/decision")
    async def decide(
        thread_id: str,
        decision: Decision,
        request: Request,
        elfagent_access: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        """Record the human's decision and resume the graph.

        This endpoint is the only way a decision enters the system. No tool
        anywhere writes one and nothing upstream of the gate can supply it —
        which is what "the system recommends, it cannot act" means in practice.
        """
        _authorise(elfagent_access)
        orchestrator = request.app.state.orchestrator
        state = await orchestrator.state(thread_id)
        if not state["values"]:
            raise HTTPException(404, f"no run on record for {thread_id}")
        if not state["awaiting_human"]:
            raise HTTPException(409, f"{thread_id} is not waiting on a decision")

        recommended = (state["values"].get("recommendation") or {}).get(
            "recommended_action"
        )
        payload = {
            "subject_id": LAUNCH_OF.get(thread_id, thread_id),
            "decided_action": decision.decided_action,
            "decided_by": decision.decided_by,
            "followed_recommendation": decision.decided_action == recommended,
            "note": decision.note,
            "per_market": decision.per_market,
        }

        captured = TRACE.setdefault(thread_id, [])
        last_seq = captured[-1]["seq"] if captured else 0
        async for event in orchestrator.submit_decision(
            thread_id, payload, start_seq=last_seq
        ):
            captured.append(event.model_dump(mode="json"))

        after = await orchestrator.state(thread_id)
        return {"decision": after["values"].get("decision"), "state": after}


def create_app(client: Any = None, *, checkpoints: str | None = None) -> FastAPI:
    """Build the app around a model client.

    Parameterised so the test suite can pass a scripted client and exercise
    every endpoint — including the stream — without a key, a network call, or
    a real model run.
    """
    checkpoint_path = checkpoints or CHECKPOINTS

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Hold one checkpointer and one orchestrator open for the process.

        The checkpointer is a file so a run survives this process dying — that
        is the point of it, and the reason the decision endpoint can resume a
        run this process never started. On a host with an ephemeral filesystem
        that guarantee ends at redeploy; mount a disk if it has to hold.
        """
        # Logged step by step because a container that fails to start says
        # nothing useful: the platform reports a health-check timeout, and the
        # actual cause is whichever line below did not print.
        print("[boot] starting elfagent api", flush=True)
        print(f"[boot] {configure_tracing().describe()}", flush=True)

        if not os.environ.get("ELFAGENT_ACCESS_KEY"):
            print(
                "[boot] WARNING: ELFAGENT_ACCESS_KEY unset — every endpoint is "
                "open, and each run spends real model credit.",
                flush=True,
            )

        # A mounted volume replaces whatever the image baked into this path,
        # so the directory may legitimately not exist on first boot.
        Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        print(f"[boot] checkpoints at {checkpoint_path}", flush=True)

        from elfagent.usecases.launch_readiness.warehouse import DEFAULT_DB

        print(
            f"[boot] warehouse {'found' if DEFAULT_DB.exists() else 'MISSING'} "
            f"at {DEFAULT_DB}",
            flush=True,
        )

        async with sqlite_checkpointer(checkpoint_path) as checkpointer:
            # Constructing the model client can fail on a bad or absent key.
            # That must not stop the process from serving /api/health, or the
            # platform kills the container and the reason is never visible.
            model, model_error = client, None
            if model is None:
                try:
                    model = AnthropicClient(
                        model=os.environ.get("ELFAGENT_MODEL", "claude-opus-5")
                    )
                except Exception as failure:
                    model_error = f"{type(failure).__name__}: {failure}"
                    print(f"[boot] MODEL CLIENT FAILED — {model_error}", flush=True)

            use_case = build_use_case(
                model, effort=os.environ.get("ELFAGENT_EFFORT", "high")
            )
            app.state.use_case = use_case
            app.state.budget = Budget()
            app.state.model_error = model_error
            app.state.warehouse_ok = DEFAULT_DB.exists()
            app.state.orchestrator = Orchestrator(
                use_case,
                checkpointer=checkpointer,
                limits=RunLimits.from_env(dict(os.environ)),
            )
            print("[boot] ready", flush=True)
            yield

    # Dev origins plus whatever the deployed front end is served from.
    # Credentialed requests cannot use a wildcard origin, so the deployed
    # origin must be named explicitly or the browser blocks every call.
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    extra = os.environ.get("ELFAGENT_ALLOWED_ORIGINS", "").strip()
    if extra:
        origins += [o.strip() for o in extra.split(",") if o.strip()]

    api = FastAPI(title="elfagent", version="0.1.0", lifespan=lifespan)
    api.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _register(api)
    return api


app = create_app()
