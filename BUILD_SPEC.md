# Build Spec — elfagent: Multi-Agent Orchestration Platform
## Flagship use case: "Launch Readiness Council" (candidate name: **Launch e.l.f.gible**)

> **This document is the top-level brief for Claude Code.**
> Read it fully before writing any code. Build in the order in §12 — the
> platform shell and ONE agent end-to-end first, then fan out. Do NOT generate
> all four agents in a single pass.

---

## 0. The one-sentence goal

Demonstrate **multi-agent orchestration**: one orchestrator agent coordinating
four specialist agents that each reason independently, run in parallel, **genuinely
disagree**, and hand a single reconciled go / slip / partial recommendation —
with the dissent preserved — to a human who decides. Everything else serves that
demonstration.

**This is a demo, not a product.** When a choice trades domain realism for
clarity of orchestration, choose clarity. The launch-readiness domain is the
vehicle; the orchestration is the payload.

**Audience:** e.l.f. Beauty's Chief Technology & AI Officer Ekta Chopra and her
tech/data/AI org — a team already running ~85 agentic pilots. They do not need
convincing that an agent can be built. They need to see that we understand the
*pattern* deeply: genuine multi-agent disagreement and reconciliation, which no
beauty/CPG competitor has publicly shipped.

---

## 1. What we are proving (the four credibility signals)

Every one of these must have a concrete, visible moment in the finished demo:

1. **We call tools "tools" and agents "agents" — correctly.** Some components are
   deterministic lookups. We label them tools and say so out loud. We never
   inflate a lookup into an "agent." (Strongest credibility signal.)
2. **The agents genuinely disagree, and reconciliation is the hard part.** The
   centerpiece is a launch where four specialists reach conflicting conclusions —
   each correct within its own domain — and the judgment layer reconciles into
   go/slip/partial *while explicitly surfacing the minority view*, never
   collapsing to false consensus.
3. **We designed against known failure modes.** Star topology (not peer-to-peer),
   typed contracts on every hand-off, durable checkpointing, hard stop
   conditions. We can name why each choice was made.
4. **The human stays in control by design.** The system recommends; it cannot act.
   No tool anywhere writes a launch decision. A human (the Director of
   Commercialization persona) decides; the decision is recorded.

This matches Chopra's stated philosophy precisely: "the human will always be the
conductor," AI is "not an IT project," and the community will "call us out" if AI
shows up in creative/consumer work — so this demo is deliberately **internal /
operational**, not consumer-creative.

---

## 2. The use case

**Launch Readiness Go/No-Go.** e.l.f. brings products to market in ~13–20 weeks
vs. an industry norm of 12–18 months — speed is the company's defining moat. But
launching that fast, into multiple retailers and multiple countries at once,
means readiness is often uneven across domains and markets. Someone has to make
the call: ship now, slip the date, or launch partially where ready.

**Trigger (deterministic — NOT an agent):** a launch record reaches a countdown
threshold (T-minus-4-weeks-to-first-ship) in the launch calendar. A scheduled
check fires the flow with a `launch_id`. No LLM decides to start.

**Flow:** signal → orchestrator fans out to 4 specialist agents in parallel →
each returns a typed readiness finding → judgment node reconciles into one
recommendation (go / slip / partial) with confidence + preserved dissent → human
decides → decision recorded (closes the loop).

**Human decision + owner:** go / slip / partial-launch, owned by the **Director
of Commercialization** (a real e.l.f. role that owns the Stage-Gate/PMO process
across Product Dev, Supply Chain, Packaging, Regulatory, and Commercial). This is
the demo's human-in-the-loop persona.

**Why this use case (vs. alternatives considered):** it is the most e.l.f.-native
(protects the speed moat; de-risks the live Rhode integration and EU expansion),
the human decision has a real named owner, and — critically — the four domains
*genuinely conflict* rather than merely contributing non-overlapping facts.
Deductions, campaign-to-shelf, and GEO were considered; launch readiness wins on
combined resonance + orchestration strength + low vendor-overlap.

---

## 3. The verified conflict scenario (the heart of the demo)

**This scenario is regulatory-accurate as of mid-2026 and must be baked into the
seed data, not narrated on top of it.** The disagreement must arise from the
actual data each agent reads.

**The launch:** a fictional **e.l.f. SKIN** SKU — "Bright Reset Vitamin-C Serum"
(fictional; do not use a real e.l.f. product) — already selling in the **US**,
now being pushed into **Germany** and the **UK** to catch an open social trend
window. Target channels: Target + Ulta + DTC (US), Rossmann + DTC (Germany),
Superdrug + DTC (UK).

**The verified regulatory reality driving the conflict:**
- The EU prohibits 1,700+ cosmetic substances vs. ~11 US federal prohibitions, so
  US-compliant formulas often need reformulation for the EU.
- EU ingredient rules split into **Annex II (prohibited — banned at any
  concentration)** and **Annex III (restricted — allowed only under conditions,
  e.g. a max concentration)**. The "restricted, not banned" nuance is deliberate:
  it creates a judgment call, not a binary.
- The EU requires **CPNP notification** (Cosmetic Products Notification Portal)
  *before* market entry, which depends on a completed **CPSR** (safety
  assessment) first — a built-in critical path the US doesn't gate the same way.
- **Great Britain is NOT covered by CPNP** — it uses a separate **SCPN** system.
  So UK and Germany are two different filings on two different portals: "ready for
  one EU-adjacent market, not the other" is structurally guaranteed, not
  contrived.

**The seed-data state that produces genuine four-way disagreement:**
- **US:** fully ready — item setup complete, inventory positioned, no regulatory
  gate.
- **Germany:** the US formula contains an ingredient that is **Annex III
  restricted** at a concentration the current formula **exceeds**. A compliant
  reformulation exists but isn't in production. **CPNP notification is in
  progress but not complete** (CPSR done, portal submission pending).
- **UK:** **SCPN** filing complete and ingredient compliant at UK limits — UK is
  actually ready, but on a *different* filing than Germany.
- **Social signal:** trend window is open NOW; every week of delay forfeits
  measurable velocity.

**How the four agents genuinely disagree (each correct in its own domain):**
| Agent | Reads | Concludes | Leans |
|---|---|---|---|
| Regulatory | Annex III limit exceeded (DE); CPNP incomplete (DE); SCPN done (UK) | Germany is a hard hold; UK is clear | **slip (DE) / go (UK)** |
| Supply | Inventory positioned; trend window open; reformulation not in production | Ship now or forfeit the window | **go** |
| Retailer | US item-setup complete; Rossmann not gated on us; UK ready | Partial-launch US+UK now, DE later | **partial** |
| Packaging | EU reformulation needs new INCI labelling + artwork; long pole | The DE artwork is the real timeline driver | **slip (DE)** |

**Reconciled recommendation (what judgment should produce):** **Partial launch —
US + UK now, Germany slips to the reformulated version** — confidence moderate,
with dissent explicitly preserved: *"Supply argues for shipping all markets now to
catch the window; overridden because the German Annex III exceedance and
incomplete CPNP notification are hard legal gates, not schedule preferences. UK
proceeds because it clears on a separate SCPN filing."*

**Also seed a clean case and a clear case** so the demo shows range:
- **A clean GO:** a US-only replenishment launch, everything ready.
- **A clear SLIP:** a launch where supply genuinely can't deliver units in time
  and no partial is sensible — everything points one way.
- **The partial (above):** the star of the demo, the four-way conflict.

> **Regulatory disclaimer (put in demo notes):** ingredient/annex specifics are
> illustrative as of mid-2026 and move with EU Omnibus updates; this is a
> demonstration of an orchestration pattern, not regulatory advice.

---

## 4. Architecture (the shape)

```
   ┌─────────────┐
   │   SIGNAL    │  deterministic — scheduled check on the launch calendar.
   │ (not agent) │  Fires at T-minus-4-weeks with a launch_id.
   └──────┬──────┘
          ▼
   ┌─────────────────────────────────────────────┐
   │            ORCHESTRATOR AGENT                │  star topology.
   │  invokes specialists, fans out in PARALLEL,  │  holds shared state.
   │  collects typed findings, hands to judgment. │  specialists NEVER
   │                                              │  talk to each other.
   └───┬───────┬───────┬───────┬──────────────────┘
       ▼       ▼       ▼       ▼   (parallel fan-out)
   ┌──────┐┌──────┐┌──────┐┌──────┐
   │REGUL.││SUPPLY││RETAIL││PACKAG│   4 specialist agents (§5)
   │agent ││agent ││agent ││agent │   each: LLM reasoning + its own tools
   └──┬───┘└──┬───┘└──┬───┘└──┬───┘   each returns a typed finding
      └───────┴───┬───┴───────┘
                  ▼
           ┌──────────────┐
           │  JUDGMENT    │  single agent. reconciles four findings →
           │    node      │  go/slip/partial + confidence + PRESERVED
           │              │  dissent (never false consensus).
           └──────┬───────┘
                  ▼
           ┌──────────────┐
           │ HUMAN GATE   │  first-class state. graph pauses.
           │ (React UI)   │  Director of Commercialization persona
           │              │  decides go / slip / partial.
           └──────┬───────┘
                  ▼
           decision recorded → closes the loop
```

**Why star, not peer-to-peer:** peer-to-peer LLM multi-agent systems fail at high
rates (Berkeley MAST: 41–86.7% across frameworks), concentrated in inter-agent
handoffs where context degrades. A star with one coordinator holding state
structurally eliminates that class. Say this in the demo.

**Platform-shell discipline (this is the elfagent platform, not a one-off):**
build the orchestrator, agent registry, contract base classes, and trace view
**domain-agnostic from the first commit**, parameterized by use case. The other
three use cases (campaign-to-shelf, GEO, deductions) must be addable as
*configuration*, not rebuilds. This makes the "one platform, four use cases"
story true rather than aspirational. Do not hardcode launch-readiness specifics
into the shell.

### 4.1 Observability architecture (LangGraph runs; LangSmith proves) — DECIDE THIS UP FRONT

There are THREE distinct trace surfaces, fed by TWO different data sources. Getting
the data source right is cheap now and expensive to retrofit, so it is specified
here rather than left to build-time convenience.

- **LangGraph** runs the agents (the graph, the nodes, the star topology, the
  durable checkpointing). It also **emits a real-time event stream** as the graph
  executes (`graph.astream_events` / streaming mode).
- **LangSmith** wraps the run and records the full trace tree (inputs, outputs,
  tool calls, timing, token spend) to `smith.langchain.com` — a
  **developer-facing** console.

The three surfaces:

1. **Live orchestration view (in our React app) — fed by the LangGraph EVENT
   STREAM, not LangSmith.** This is the demo's most compelling moment: the four
   agents lighting up and returning *in parallel, in real time*. It MUST be driven
   by LangGraph's streaming events so the fan-out animates as it happens. Do NOT
   build this against LangSmith polling — LangSmith is after-the-fact and cannot
   show live execution. (This is the single easiest thing to get wrong by taking
   the convenient path.)
2. **Trace drawer (in our React app) — our own rendered view.** A clean,
   product-styled reasoning tree for a finished run. Data source: the captured
   LangGraph events (preferred, already in hand from the stream) or the LangSmith
   API. This is what we *show* as the in-product trace.
3. **LangSmith console (as-is) — our dev tooling and the "is this real?" proof.**
   Kept in its native form. When a technical viewer asks whether the in-app trace
   is real, flip to the actual LangSmith run and show the same execution in raw
   tooling. Product view for the narrative; raw console as evidence it isn't
   staged.

**Rule:** the API layer must expose the LangGraph event stream to the front end
(e.g. SSE/WebSocket) so the live view is genuinely real-time. LangSmith is the
recording/observability backend and the proof surface — it is NOT the data source
for the live fan-out.

---

## 5. The four specialist agents — and why each is an AGENT not a TOOL

Test applied to every component: **"write the question the orchestrator asks it.
If the answer is deterministic, it's a tool. If it requires interpretation,
weighing, or judgment under ambiguity, it's an agent."** Each specialist below
is an agent because its question has no single deterministic answer; each
*contains* tools (deterministic lookups) it reasons over.

### 5.1 REGULATORY agent
- **Question:** "Is this SKU legally clear to ship in each target market, and if
  not, is the gate hard or conditional?"
- **Why an agent:** it must interpret the *difference* between an Annex II hard
  ban and an Annex III conditional restriction (is the exceedance fatal or
  fixable?), and weigh notification state (CPNP in-progress vs. complete; the
  UK-SCPN-vs-EU-CPNP split). Not a flag lookup — a judgment about severity and
  path.
- **Tools:** `get_ingredient_restrictions(sku, market)`,
  `get_notification_status(sku, market)`.
- **Returns:** `RegulatoryFinding`.

### 5.2 SUPPLY agent
- **Question:** "Can we supply the demand in the open window, and what does
  waiting cost?"
- **Why an agent:** it weighs inventory position against an open trend window and
  reformulation lead time — a cost-of-delay judgment, not a stock lookup.
- **Tools:** `get_inventory_position(sku, market)`, `get_lead_times(sku)`,
  `get_trend_window(sku)`.
- **Returns:** `SupplyFinding`.

### 5.3 RETAILER agent
- **Question:** "Which markets/channels are commercially ready to receive this
  now, and is a partial launch viable?"
- **Why an agent:** it reasons about whether an incomplete market blocks the
  others — i.e., whether a partial (US+UK now, DE later) is coherent or fragmented.
- **Tools:** `get_item_setup_status(sku, retailer)`, `get_channel_readiness(sku,
  market)`.
- **Returns:** `RetailerFinding`.

### 5.4 PACKAGING agent
- **Question:** "Is packaging/artwork ready per market, and where is the long
  pole?"
- **Why an agent:** it judges which packaging gap actually drives the timeline
  (EU reformulation → new INCI labelling + artwork) vs. which are cosmetic.
- **Tools:** `get_artwork_status(sku, market)`, `get_labelling_requirements(sku,
  market)`.
- **Returns:** `PackagingFinding`.

### 5.5 Components that are TOOLS, not agents (say so explicitly)
- The **signal / countdown detector** — deterministic calendar check.
- Every `get_*` above — deterministic data access.
- Any pure formatting/aggregation helper.

The demo must, at one point, **point at a tool and say "this is a tool, not an
agent, and here's why."** That moment is the build's thesis in miniature.

---

## 6. Typed contracts (Pydantic) — non-negotiable

Every agent returns a validated typed object, never prose. Kills the
format-mismatch failure mode; makes the run inspectable. Define these first —
they are the spine, and (per §4) the base classes live in the domain-agnostic
platform layer.

```python
from enum import Enum
from pydantic import BaseModel, Field

class Lean(str, Enum):
    GO = "go"
    SLIP = "slip"
    PARTIAL = "partial"
    HOLD = "hold"

class MarketReadiness(BaseModel):
    market: str                       # "US" | "DE" | "UK"
    ready: bool | None                # None = conditional/ambiguous, deliberately
    gate_type: str | None             # "hard" (legal) | "conditional" | None
    detail: str

class Finding(BaseModel):
    """Base shape every specialist returns. Lives in the platform layer."""
    agent: str
    lean: Lean
    confidence: float = Field(ge=0, le=1)
    rationale: str                    # one-paragraph human-readable reasoning
    evidence: list[str] = []          # concrete facts the lean rests on
    per_market: list[MarketReadiness] = []
    semantic_version: str             # which dbt metric/definition set was used

class RegulatoryFinding(Finding):
    hard_gate_markets: list[str] = [] # markets with a hard legal block

class SupplyFinding(Finding):
    cost_of_delay_note: str

class RetailerFinding(Finding):
    partial_viable: bool

class PackagingFinding(Finding):
    long_pole_market: str | None

class Recommendation(BaseModel):
    launch_id: str
    recommended_action: Lean
    per_market_action: list[MarketReadiness]   # go/slip per market for a partial
    confidence: float = Field(ge=0, le=1)
    reconciliation: str               # how the four were combined
    dissent: list[str] = []           # findings pointing the other way — PRESERVED
    findings: list[Finding]           # the raw four, for the trace panel
```

`MarketReadiness.ready: bool | None` and `gate_type` carry the "conditional, not
binary" nuance. **`dissent` must never be empty when findings conflict** — false
consensus is a documented failure mode and its absence is the whole point.

---

## 7. Data layer — DuckDB + dbt

**Warehouse:** DuckDB (local file). dbt code is warehouse-portable; in the demo we
may *say* "Snowflake" (e.l.f.'s real warehouse) — call this out honestly as a
stand-in if asked; do not pretend the file is Snowflake.

**dbt carries a light semantic-layer story** (second credibility signal). Model a
governed definition with an owner + rationale in the description — e.g.
`launch_ready` per market as a governed metric that encodes "ready = ingredient-
compliant AND notification complete AND item-setup complete AND artwork
approved," with the owner noted. Include one governed definition even though the
agents also read raw tables, because "definitions are governed, not improvised"
resonates with Chopra's "get the data/pipes right or forget about agents" line.

**Layout:**
```
elfagent/
├── data/                     # DuckDB file + raw seed CSVs
├── dbt/
│   ├── models/
│   │   ├── staging/          # stg_*.sql — neutral, one row per source record
│   │   └── marts/            # launches.sql + launches.yml (governed metric)
│   └── dbt_project.yml
├── platform/                 # DOMAIN-AGNOSTIC shell (the "elfagent platform")
│   ├── contracts.py          # Finding/Recommendation base classes (§6)
│   ├── orchestrator.py       # LangGraph star graph, registry, checkpointing
│   ├── registry.py           # agent registration — use cases plug in here
│   └── tracing.py            # LangSmith wiring
├── usecases/
│   └── launch_readiness/     # THIS use case as configuration
│       ├── signal.py         # deterministic countdown detector
│       ├── tools/            # deterministic data-access fns (the TOOLS)
│       ├── specialists/      # the four AGENTS
│       └── judgment.py       # reconciliation → Recommendation
├── api/                      # thin FastAPI exposing the graph to React
├── web/                      # React + TypeScript front end
└── BUILD_SPEC.md             # this file
```

The `platform/` vs `usecases/` split is what makes the platform story real.

---

## 8. Seed data — with the conflict baked in

Keep each table small (~a dozen rows). Minimum tables:
`launches` (SKU, brand, target markets, first-ship date, countdown),
`skus` (brand, category), `ingredients` (INCI, per-market annex status + limit),
`sku_ingredients` (SKU → ingredient → concentration),
`notifications` (SKU × market × portal[CPNP/SCPN] × status),
`inventory` (SKU × market × units + lead time), `trend_signals` (SKU × window),
`item_setup` (SKU × retailer × status), `artwork` (SKU × market × status),
`launch_history` (past launches + outcomes — for the clean/clear cases and future
extension).

**Deliberately seed:**
- **LAUNCH-1001 — the partial (the star, §3):** e.l.f. SKIN Vitamin-C serum,
  US/DE/UK. DE has Annex III concentration exceedance + CPNP in-progress; UK SCPN
  complete + compliant; US fully ready; trend window open. Produces the genuine
  four-way split.
- **LAUNCH-1002 — clean GO:** US-only replenishment, everything ready.
- **LAUNCH-1003 — clear SLIP:** supply genuinely short in all markets, no partial
  sensible.

The edge cases ARE the value — clean data demonstrates nothing.

---

## 9. Front end — React + TypeScript

Purpose: make orchestration **legible** and stage the human gate. Screens:

1. **Launch queue** — launches at the countdown threshold (signal output). Click
   one to run the flow.
2. **Live orchestration view (centerpiece)** — orchestrator fanning out to four
   agents **in parallel**; each agent's status (running → returned) then its
   typed finding (lean + confidence + per-market readiness + rationale). When
   they disagree, make it visually obvious (leans in different colors; a per-
   market readiness grid US/DE/UK). This screen is where "multi-agent
   orchestration" stops being a claim and becomes visible.
   **Data source: the LangGraph event stream (real-time), via SSE/WebSocket from
   the API — NOT LangSmith polling (§4.1).** The fan-out must animate as it
   actually executes.
3. **Recommendation + human gate** — the reconciled go/slip/partial, the
   confidence, the **dissent stated explicitly**, the four raw findings beneath,
   and go / slip / partial buttons (with per-market breakdown for partial). On
   click, record the decision.
4. **Trace drawer (our own rendered view)** — a clean, product-styled reasoning
   tree for the finished run (data from captured LangGraph events or the LangSmith
   API). This is the in-product trace we *show* (§4.1, surface 2).
5. **LangSmith console (kept as-is, not built by us)** — the real observability
   console at `smith.langchain.com`, used live as the "is this real?" proof when a
   technical viewer asks (§4.1, surface 3). Not a screen we build; a tab we can
   flip to.

Clean and un-flashy; legibility over polish. Detail views as full pages with
back-nav, not modals/drawers (except the trace drawer).

---

## 10. The non-negotiables (design-against-failure checklist)

- **Star topology.** Specialists never call each other; only the orchestrator does.
- **Typed contracts** (§6) on every hand-off. No prose returns between nodes.
- **Dissent preserved.** Judgment must surface the minority view when findings
  conflict; never collapse to false consensus. Assert this in code
  (`dissent` non-empty when leans differ).
- **Durable checkpointing.** LangGraph checkpointer. The demo will kill the process
  mid-run and show it resume — build for that from the start.
- **Hard stop conditions.** Cap agent steps/iterations and total spend in code, not
  in a prompt.
- **Tracing from line one.** LangSmith wired as the graph is built, not
  retrofitted (recording + proof surface). AND the LangGraph event stream exposed
  through the API for the live view — decide both data sources up front per §4.1;
  do not build the live view against LangSmith polling.
- **Human gate is real.** The graph genuinely pauses. NO tool anywhere writes a
  launch decision. The system cannot act.
- **LLM spend cap.** A hard ceiling so a loop bug can't run up a bill.
- **Platform/usecase separation** (§4, §7). Shell stays domain-agnostic.

---

## 11. Stack summary (install / do NOT install)

**Use:**
- DuckDB (local warehouse) · dbt-duckdb (models + one governed metric)
- Python: LangGraph (orchestration, checkpointing, registry), LangSmith (tracing),
  Pydantic (contracts), an LLM SDK (Anthropic or OpenAI — one key, spend-capped),
  FastAPI (thin API)
- Web: React + TypeScript + Vite; minimal styling (Tailwind fine)

**Do NOT add (scope discipline — leaving these out is part of the credibility
story):**
- ❌ Cube — dbt Core covers the semantic layer for this demo.
- ❌ Ontology/graph tool (Neo4j, Stardog, Palantir) — launch readiness is
  relational; no multi-hop traversal. (Graph is a phase-2 story only.)
- ❌ Vector DB / RAG — not a document-retrieval use case. Don't add it because
  it's fashionable.
- ❌ Real Snowflake — DuckDB for the build; swap only if the client must see it.
- ❌ Real retailer/regulatory integration, autonomous actions, auth/multi-tenancy
  — out of scope for a demo.

---

## 12. Build order — PLATFORM SHELL + VERTICAL SLICE FIRST

Do not build all four agents at once. Prove one clean end-to-end path, then
replicate.

1. **Data layer.** Schema → seed CSVs (with §8 conflict) → load into DuckDB →
   dbt staging + marts + one governed `launch_ready` metric with owner/rationale.
   Confirm `dbt build` green and the metric resolves for LAUNCH-1001.
2. **Platform shell (domain-agnostic).** `contracts.py` (§6 base classes),
   `orchestrator.py` (LangGraph star + registry), `tracing.py` (LangSmith),
   checkpointing, hard stop conditions. No launch-readiness specifics here.
3. **Tools + ONE agent end-to-end.** Build the deterministic tools (unit-tested
   against seed data), then the **Regulatory** agent only, registered into the
   shell, returning a real `RegulatoryFinding` for LAUNCH-1001, traced and
   checkpointed. Confirm BOTH observability paths on this slice (§4.1): LangSmith
   records the run, AND the LangGraph event stream emits real-time node events.
   **Prove this slice before going further.**
4. **Fan out to four.** Add Supply, Retailer, Packaging as parallel nodes.
   Confirm parallel execution and typed collection.
5. **Judgment node.** Reconcile four findings → `Recommendation` with preserved
   dissent. Verify against LAUNCH-1001 that the four-way conflict reconciles to
   the partial (US+UK now, DE slip) with Supply's dissent surfaced.
6. **API layer.** Thin FastAPI: list queue; **run flow as a real-time stream
   (SSE or WebSocket) surfacing the LangGraph event stream** so the front end can
   animate the parallel fan-out live (§4.1); submit human decision. Do NOT reduce
   the run endpoint to a poll-when-done call — the live view depends on streaming.
7. **Front end.** Queue → live orchestration view (per-market grid, fed by the
   streaming endpoint) → recommendation + gate → trace drawer. Wire to API. Keep
   the real LangSmith console available as the separate "proof" surface (§4.1),
   not rebuilt.
8. **The demo moments.** Confirm all four credibility signals (§1) have a concrete
   on-screen moment: the tool-vs-agent callout, the LAUNCH-1001 disagreement +
   preserved dissent, the kill-and-resume, the human gate. Adjust seed data / UI
   so each lands.

Stop after each step and confirm green before proceeding. If step 3 (one agent
end-to-end) isn't clean, do NOT fan out — the tangle is far harder to debug at
four.

---

## 13. Deployment (later — do not build for this yet)

Build local. Git is the seam. For browser UX later: front end → Vercel/Netlify;
API + agents → a container host (Railway/Render/Fly); DuckDB bundled read-only or
swapped for Snowflake. Nothing in the local build blocks this. Do not add
deployment complexity during the prototype.

---

## 14. Definition of done

In a live browser demo, you can:
1. Show the launch queue, pick LAUNCH-1001, and watch four agents run **in
   parallel**, each returning a per-market readiness finding.
2. See them **genuinely disagree** (Supply: go; Regulatory: hold DE; Retailer:
   partial; Packaging: slip DE) and see judgment **reconcile to a partial with
   Supply's dissent explicitly preserved**.
3. **Point at a tool and an agent** and explain, truthfully, why each is what it
   is.
4. **Kill the process mid-run** and watch it **resume** from checkpoint.
5. **Decide** go/slip/partial as the human, and see the decision **recorded**.
6. Open the **in-app trace drawer** and show the full reasoning tree — then, if a
   technical viewer asks "is this real," flip to the **actual LangSmith console**
   and show the same run in raw tooling (§4.1). Product view for the narrative,
   raw console as proof.
7. Explain how the **platform shell** would drive the other three use cases as
   configuration — pointing at the `platform/` vs `usecases/` separation.

If all seven work and you can narrate the *why* behind each, the prototype has met
its goal: proving we understand what an agent is, how orchestration actually
works, and that elfagent is a platform, not a one-off.
