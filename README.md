# elfagent

Multi-agent orchestration platform. Flagship use case: **Launch Readiness Council**.

The brief is [BUILD_SPEC.md](BUILD_SPEC.md) — read it before changing anything here.
Build order is §12; this repo is at **step 1 (data layer) complete**.

## Status

| Step | What | State |
|---|---|---|
| 1 | Data layer — seeds, DuckDB, dbt, governed `launch_ready` metric | ✅ green |
| 2 | Platform shell — contracts, orchestrator, registry, limits, tracing | ✅ green |
| 3 | Tools + Regulatory agent end-to-end, both trace surfaces confirmed | ✅ green |
| 4 | Fan out to four specialists (parallel, 3.6× vs sequential) | ✅ green |
| 5 | Judgment node — reconciles to partial, dissent preserved | ✅ green |
| 6 | API layer — SSE stream, trace, human gate | ✅ green |
| 7 | Front end — queue, live view, gate, trace drawer | ✅ green |
| 8 | Demo moments | not started |

## Layout

```
data/seed/            raw_*.csv — the source of truth. The .duckdb file is a build artefact.
dbt/                  staging (neutral) -> marts (governed). profiles.yml lives here.
elfagent/platform/    domain-agnostic shell. No launch-readiness specifics ever.
elfagent/usecases/    launch_readiness/ as configuration on that shell.
api/                  thin FastAPI.
web/                  React + TypeScript.
tests/                shell + use-case tests.
design/               approved HTML mockups + the research decks. Reference, not source.
```

The platform/usecases split is what makes the "one platform, four use cases"
claim true rather than aspirational. Nothing domain-specific goes in
`elfagent/platform/`.

> **One deviation from BUILD_SPEC §7.** The spec puts `platform/` at the repo
> root. A top-level `platform` package shadows Python's stdlib `platform`
> module, which breaks langgraph's imports outright (verified, not theoretical).
> It is namespaced under `elfagent.` instead. The split the spec cares about is
> unchanged; only the import prefix differs.

## The platform shell

Domain-agnostic by construction. It knows about specialists, judgment and a
human gate; it does not know what a launch, a market or an annex is.

| Module | Responsibility |
|---|---|
| `contracts.py` | `Finding[LeanT]`, `Recommendation[LeanT]`, `SegmentAssessment`, `HumanDecision` |
| `registry.py` | `UseCase`, `AgentSpec`, `ToolSpec`, `SpecialistContext` |
| `orchestrator.py` | LangGraph star graph, parallel fan-out, human gate, checkpointing |
| `limits.py` | hard stop conditions and the shared spend ledger |
| `events.py` | the normalised real-time event stream |
| `tracing.py` | LangSmith wiring |

The lean vocabulary is supplied by the use case, not fixed by the shell —
launch readiness plugs in go/slip/partial/hold, deductions would plug in
accept/dispute/investigate. The shell's own test suite runs a stub use case
with a *third* vocabulary (keep/drop/defer) precisely to prove the shell has no
opinion about it.

Three things worth knowing about the design:

- **Star topology is enforced by the shape of `SpecialistContext`**, which does
  not contain the other findings. A specialist cannot read its peers because it
  is never handed them — not because a convention says not to.
- **Graph state is plain JSON, and the typed contract is re-established at each
  boundary.** State crosses a serialisation boundary at every checkpoint, so a
  run resumed in a fresh process gets dicts back. Holding validated models in
  state works right up until the kill-and-resume demo, then fails. Instead a
  specialist must return its declared `finding_model`, and judgment
  re-validates every finding before reasoning over it — checked twice rather
  than assumed once.
- **Empty dissent with conflicting leans raises.** `Recommendation` refuses to
  construct. False consensus fails loudly in code rather than being trusted to
  a prompt (§10).

## Tools vs agents

The distinction is data in the registry, not a line someone remembers in the
demo. Every deterministic component is a `ToolSpec` carrying the reason it is
one; see `TOOL_CATALOGUE` in
[elfagent/usecases/launch_readiness/tools/](elfagent/usecases/launch_readiness/tools/__init__.py).
Ten tools are registered, including the signal.

Two properties worth knowing:

- **The warehouse connection is read-only.** BUILD_SPEC §1.4 requires that the
  system cannot act. That is enforced at the connection, so it does not depend
  on every tool author remembering — DuckDB refuses the write regardless. There
  is a test that tries.
- **No tool returns null for "nothing on file".** An absent row and a row saying
  "no restriction applies" mean different things, and silence-means-permitted is
  the one inference a regulatory agent must never make. Tools return an explicit
  `no_record` status instead, so the agent weighs it as its own state and the
  trace shows that it did.

The specialists read staging tables — the underlying facts — while the signal
and launch queue read the governed `launches` mart. The agents reason over the
evidence, with the governed metric available as the baseline they can agree or
disagree with.

## The Regulatory agent

`claude-opus-5` by default. Three things about the request shape that would be
silent mistakes rather than obvious ones:

- **No `temperature`, `top_p`, or `top_k`** — removed on this model; sending any
  of them is a 400. Behaviour is steered by prompting.
- **No `thinking` config** — thinking is on by default and `budget_tokens` is a
  400. Depth is set by `output_config.effort`. Thinking shares the `max_tokens`
  ceiling with the response, so that ceiling is set generously.
- **`fallbacks: "default"` is enabled.** This model's safety classifiers can
  decline a request, and regulatory wording is the kind of thing that can trip
  them. With fallbacks on, a declined request is re-run server-side instead of
  coming back as a refusal — and `stop_reason` is checked before `content` is
  ever read, so a refusal raises rather than being parsed as a finding.

**The model chooses its own tool calls.** It is handed the lookups, not a
pre-fetched brief. An agent that is given the facts and asked only for a verdict
is a formatter with extra steps.

**`agent` and `semantic_version` are not in the submission schema.** They are
facts we own, so the model cannot assert them — it fills in only the judgment.

A malformed submission comes back to the model as a tool error carrying the
validation message, inside the same step budget. Prose never crosses the
boundary; a prose-only reply is refused rather than parsed.

## Reconciliation

Two things are enforced in code rather than asked for in the prompt:

- **Dissent must survive.** `Recommendation` refuses to construct when the
  specialists' leans differ and the dissent list is empty.
- **A hard gate cannot be traded away.** No market any specialist marked
  hard-gated may come back marked ready. A recommendation that does is rejected
  and handed back for correction. This is the difference between a constraint
  and a preference, and it is the one thing a persuasive-sounding paragraph
  must not be able to talk its way around.

Everything else — weighing an open window against a slipped market, whether a
partial is coherent, how much confidence to express — is genuinely the model's
judgment.

> **A note on the seed data.** The first live four-agent run produced no
> disagreement at all: every specialist returned `partial`. The cause was a
> domain leak — `inventory.csv` carried the note *"Units exist but the EU
> reformulation is not in production"*, a product/regulatory fact sitting in a
> supply table. Supply could therefore see another specialist's constraint and
> reached the same conclusion by a different route, leaving nothing to
> reconcile. The note now describes only the replenishment cycle. Star topology
> assumes each specialist sees its own domain and no other; that assumption has
> to hold in the data, not just in the code.

## Running it

```bash
./.venv/Scripts/python.exe scripts/run_once.py LAUNCH-1001
```

Fires the signal, runs the graph against the real model, prints the event
stream as it arrives, and stops at the human gate. ~$0.06 and ~25s for one
specialist.

```bash
./.venv/Scripts/python.exe scripts/decide.py LAUNCH-1001 partial
```

A **separate process** opens the same checkpoint file, recovers the paused
graph, and supplies the decision. That is the kill-and-resume demo and the
human gate closing the loop, in one command — and the reason the checkpointer
is a file rather than memory.

## API

```bash
./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8077
```

| Endpoint | Purpose |
|---|---|
| `GET /api/launches` | the queue — deterministic signal output |
| `GET /api/usecase` | which components are agents, which are tools, and why |
| `GET /api/runs/{id}/stream` | **SSE** — the run, as it happens |
| `GET /api/runs/{id}` | checkpointed state |
| `GET /api/runs/{id}/trace` | captured events for the trace drawer |
| `POST /api/runs/{id}/decision` | the human gate |

There is deliberately **no synchronous run-and-return endpoint**. The live view
exists to show four agents returning in parallel in real time, and a
poll-when-done call would satisfy every other requirement while quietly killing
that. One test asserts the first event arrives *while the connection is still
open* — the assertion that separates a stream from a poll.

`/api/usecase` is what the UI renders the tool-vs-agent distinction from, so
that claim reads data the codebase already holds rather than a hardcoded list.

## Front end

```bash
cd web && npm install && npm run dev
```

Needs the API on `:8077`; Vite proxies `/api` to it so the SSE endpoint is
same-origin (EventSource is stricter about CORS than fetch). Vite binds
IPv6-only here — use `http://localhost:5173`, not `127.0.0.1`.

React + TypeScript, with the approved mockup's design tokens kept as plain CSS
rather than ported to a utility framework, so the visual language stays what
was signed off. **The mockup's `setTimeout` choreography is deliberately not
ported** — every lane state comes from an event the graph emitted. If the
fan-out looks concurrent on screen it is because it was concurrent on the
server.

**Market grid toggle.** *Targeted* shows only the markets a launch actually
targets. *All markets* pins US/DE/UK and marks the rest out of scope — which
makes absence legible, since "this launch does not target Germany" is a
different fact from "Germany is blocked" and a grid that drops the column
cannot distinguish them.

## Tests

```bash
./.venv/Scripts/python.exe -m pytest -q
```

`tests/test_platform_shell.py` asserts the §10 non-negotiables the shell owns,
with stub specialists and no LLM key: four 0.25s specialists complete in ~0.25s
(genuinely parallel, not sequenced), typed contracts are validated in both
directions, a specialist is never handed its peers' findings, dissent survives
reconciliation, the graph really pauses at the human gate, a run resumed by a
*separate orchestrator over the same checkpoint file* recovers all four findings
and records the decision, and the spend/step caps abort a run.

## Setup

```bash
python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

This machine runs Avast, which intercepts HTTPS. Python needs its CA bundle or
every install and API call fails certificate verification:

```bash
export PIP_CERT="C:\ProgramData\Avast Software\Avast\wscert.pem"
```

`.env.example` carries the same path as `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE`
for runtime calls.

## Build the warehouse

Always run dbt from `dbt/` — the DuckDB path in `profiles.yml` is relative.

```bash
cd dbt && ../.venv/Scripts/dbt.exe build --profiles-dir .
```

72 nodes, all passing. Rebuild is idempotent; the warehouse is disposable.

## The governed metric

`launch_market_readiness.launch_ready` — one row per launch per market.
Owner: Director of Commercialization. Version: `launch_ready@v3`, stamped onto
every row and carried through to `Finding.semantic_version` on every agent
contract, so a run can always be tied to the definition that produced it.

Ready = ingredient-compliant **AND** notification complete/not-required **AND**
item setup complete **AND** artwork approved.

It is deliberately narrower than what the agents reason over.
`retailer_dossier_clear` and `unmet_labelling_requirements` are published beside
it as evidence but are *not* part of it — a specialist may call a market unready
for a reason the governed definition does not encode, and reconciliation should
say so rather than quietly widen the metric.

Null handling is fail-**closed** on notification, item setup and artwork (an
absent row means unproven, not fine) and fail-**open** on ingredients only,
where no restriction row genuinely means no restriction is on record. The
use-case tools return an explicit `no_record` rather than null, so no agent ever
has to infer meaning from silence.

## The three scenarios

| Launch | SKU | Shape | Point |
|---|---|---|---|
| LAUNCH-1001 | Bright Reset Vitamin-C Serum | mixed — US+UK ready, DE blocked | the four-way disagreement |
| LAUNCH-1002 | Holy Hydration Refill Cream | all_ready | clean GO |
| LAUNCH-1003 | Glow Reviver Lip Oil | none_ready | clear SLIP |
| LAUNCH-1004 | Velvet Set Priming Balm | below threshold | queue realism; never runs |

Two singular dbt tests lock the demo's premise into `dbt build`:

- `assert_scenario_readiness` — the three scenarios must produce exactly those shapes.
- `assert_annex_nuance` — LAUNCH-1001/DE must be a *conditional restriction exceeded*
  (fixable by reformulation) with **zero** prohibitions, while LAUNCH-1003/DE must be
  an outright prohibition. If those two collapse into the same shape, the
  "restricted is not banned" moment in the demo has nothing behind it.

## Demo data disclaimer

Ingredient names, annex classifications and concentration limits are
illustrative as of mid-2026 and simplified for demonstration. EU Omnibus updates
move these regularly. The structurally true part — that Great Britain files on
SCPN while the EU files on CPNP, so one market can clear while the other cannot —
is what the narration should lead with. This is a demonstration of an
orchestration pattern, not regulatory advice.

DuckDB stands in for Snowflake (e.l.f.'s actual warehouse, confirmed). The dbt
code is warehouse-portable. Say "stand-in" if asked; do not call the file
Snowflake.
