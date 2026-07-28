/**
 * Typed client for the elfagent API.
 *
 * The run endpoint is an EventSource, not a fetch. That is the whole point of
 * BUILD_SPEC §4.1 surface 1: the fan-out has to animate as it executes, which
 * means events must arrive as the graph emits them. Nothing here polls for a
 * finished run.
 */

export type Lean = "go" | "slip" | "partial" | "hold";
export type GateType = "hard" | "conditional" | null;

export interface Launch {
  launch_id: string;
  sku_id: string;
  sku_name: string;
  brand: string;
  category: string;
  target_markets: string[];
  first_ship_date: string;
  countdown_weeks: number;
  scenario: string;
  readiness_shape: "all_ready" | "mixed" | "none_ready";
  ready_markets: string[];
  blocked_markets: string[];
  semantic_version: string;
}

export interface MarketReadiness {
  market: string;
  ready: boolean | null;
  gate_type: GateType;
  detail: string;
}

export interface Finding {
  agent: string;
  lean: Lean;
  confidence: number;
  rationale: string;
  evidence: string[];
  per_market: MarketReadiness[];
  semantic_version: string;
  hard_gate_markets?: string[];
  cost_of_delay_note?: string;
  partial_viable?: boolean;
  long_pole_market?: string | null;
}

export interface Recommendation {
  subject_id: string;
  recommended_action: Lean;
  per_market_action: MarketReadiness[];
  confidence: number;
  reconciliation: string;
  dissent: string[];
  findings: Finding[];
}

export interface AgentAnatomy {
  name: string;
  kind: "agent";
  question: string;
  why_agent: string;
  tools: string[];
}

export interface ToolAnatomy {
  name: string;
  kind: "tool";
  description: string;
  why_tool: string;
}

export interface Anatomy {
  key: string;
  title: string;
  subject_label: string;
  semantic_version: string;
  agents: AgentAnatomy[];
  tools: ToolAnatomy[];
}

export type EventType =
  | "run_started"
  | "signal_fired"
  | "fan_out"
  | "agent_started"
  | "agent_tool_call"
  | "agent_returned"
  | "agent_failed"
  | "judgment_started"
  | "judgment_returned"
  | "awaiting_human"
  | "decision_recorded"
  | "limit_exceeded"
  | "run_failed"
  | "run_completed";

export const EVENT_TYPES: EventType[] = [
  "run_started",
  "signal_fired",
  "fan_out",
  "agent_started",
  "agent_tool_call",
  "agent_returned",
  "agent_failed",
  "judgment_started",
  "judgment_returned",
  "awaiting_human",
  "decision_recorded",
  "limit_exceeded",
  "run_failed",
  "run_completed",
];

export interface OrchestrationEvent {
  type: EventType;
  run_id: string;
  seq: number;
  at: string;
  agent: string | null;
  actor_kind: "agent" | "tool" | "human" | null;
  payload: Record<string, any>;
}

/**
 * Where the API lives.
 *
 * Empty in dev — Vite proxies `/api` so everything is same-origin. In a
 * deployed build this must be the absolute origin of the API container,
 * because the API cannot be hosted alongside this bundle: the run endpoint
 * holds an SSE connection open for a minute or more, which no serverless
 * function platform supports.
 */
export const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

const url = (path: string) => `${API_BASE}${path}`;

/** Raised when the API wants the shared access key. */
export class Unauthorised extends Error {}

/** Raised when there is no API to talk to — a setup problem, not a bug. */
export class ApiUnreachable extends Error {}

const NO_API =
  "This build has no API configured. Set VITE_API_BASE to the API's origin " +
  "and redeploy — Vite bakes the value in at build time, so adding the " +
  "variable without rebuilding changes nothing.";

async function parse<T>(response: Response, path: string): Promise<T> {
  // A deployed front end with no VITE_API_BASE calls its own origin, the SPA
  // redirect serves index.html, and JSON.parse fails on "<!doctype" — an
  // error that says nothing about the actual problem. Catch it here and say
  // what is really wrong.
  const kind = response.headers.get("content-type") ?? "";
  if (!kind.includes("application/json")) {
    throw new ApiUnreachable(
      API_BASE
        ? `${API_BASE}${path} did not return JSON (got ${kind || "no content-type"}). ` +
          "Check the API is running and that this origin is in its CORS allow-list."
        : NO_API,
    );
  }
  return response.json();
}

async function get<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url(path), { credentials: "include" });
  } catch (cause) {
    throw new ApiUnreachable(
      API_BASE
        ? `Could not reach ${API_BASE}. It may be asleep, down, or blocking this origin.`
        : NO_API,
    );
  }
  if (response.status === 401) throw new Unauthorised();
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return parse<T>(response, path);
}

export async function authenticate(key: string): Promise<void> {
  const response = await fetch(url("/api/auth"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ key }),
  });
  if (response.status === 401) throw new Unauthorised();
  if (!response.ok) throw new Error(await response.text());
}

export const getLaunches = () => get<Launch[]>("/api/launches");
export const getAnatomy = () => get<Anatomy>("/api/usecase");
export const getTrace = (thread: string) =>
  get<OrchestrationEvent[]>(`/api/runs/thread/${thread}/trace`);

export interface RunState {
  values: Record<string, any>;
  next: string[];
  awaiting_human: boolean;
  launch_id?: string | null;
  /** Deep link to this exact run in LangSmith — §4.1 surface 3. */
  langsmith_url?: string | null;
  /** False once the process that streamed this run is gone. */
  trace_captured?: boolean;
}

/** A run on record for a launch, resumable or already decided. */
export interface RunRecord {
  thread_id: string;
  created_at: string;
  awaiting_human: boolean;
  decided: boolean;
  findings: number;
  recommended_action: Lean | null;
  trace_captured: boolean;
}

export const getRunsFor = (launchId: string) =>
  get<RunRecord[]>(`/api/launches/${launchId}/runs`);

export async function getRunState(thread: string): Promise<RunState | null> {
  const response = await fetch(url(`/api/runs/thread/${thread}`), {
    credentials: "include",
  });
  if (response.status === 404) return null;
  if (response.status === 401) throw new Unauthorised();
  if (!response.ok) throw new Error(`state -> ${response.status}`);
  return response.json();
}

export async function submitDecision(
  thread: string,
  body: { decided_action: Lean; note?: string; per_market?: MarketReadiness[] },
) {
  const response = await fetch(url(`/api/runs/thread/${thread}/decision`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

/**
 * Open the run stream. Returns a close function.
 *
 * Every event type is registered individually because the server names its
 * events, and EventSource only routes unnamed events to `onmessage`.
 */
export function streamRun(
  launchId: string,
  onEvent: (event: OrchestrationEvent) => void,
  onError?: (error: Event) => void,
): () => void {
  // withCredentials so the access cookie rides along — EventSource cannot set
  // headers, which is why the key is exchanged for a cookie rather than sent
  // on each request.
  const source = new EventSource(url(`/api/runs/${launchId}/stream`), {
    withCredentials: true,
  });

  const handle = (raw: MessageEvent) => {
    try {
      onEvent(JSON.parse(raw.data) as OrchestrationEvent);
    } catch {
      /* a malformed frame should not tear down the run */
    }
  };

  for (const type of EVENT_TYPES) source.addEventListener(type, handle as any);
  source.onmessage = handle;
  source.onerror = (error) => {
    // The server closes the connection when the run reaches the human gate.
    // EventSource treats that as an error and would reconnect — which would
    // start the whole run again. Close it deliberately instead.
    source.close();
    onError?.(error);
  };

  return () => source.close();
}
