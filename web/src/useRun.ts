/**
 * Run state, derived from the event stream.
 *
 * Every field here comes from an event the graph emitted. Nothing is faked,
 * timed, or choreographed — the approved mockup animated on `setTimeout`, and
 * that scaffolding is deliberately not ported. If the fan-out looks concurrent
 * on screen it is because it was concurrent on the server.
 */

import { useCallback, useRef, useState } from "react";
import {
  type Finding,
  type OrchestrationEvent,
  type Recommendation,
  streamRun,
} from "./api";

export type AgentState = "idle" | "dispatching" | "running" | "done" | "failed";

export interface ToolCall {
  tool: string;
  market?: string;
  summary: string;
  durationMs: number;
}

export interface AgentView {
  name: string;
  question: string;
  state: AgentState;
  tools: ToolCall[];
  finding?: Finding;
  error?: string;
}

export interface RunView {
  status: "idle" | "running" | "reconciling" | "decided" | "failed";
  narration: string;
  agents: AgentView[];
  recommendation?: Recommendation;
  decision?: Record<string, any>;
  events: OrchestrationEvent[];
  error?: string;
  /** The graph thread this run owns. One per run, not one per launch — two
   *  viewers opening the same launch get independent runs. */
  thread?: string;
}

const EMPTY: RunView = {
  status: "idle",
  narration: "",
  agents: [],
  events: [],
};

export function useRun() {
  const [run, setRun] = useState<RunView>(EMPTY);
  const close = useRef<null | (() => void)>(null);

  const reset = useCallback(() => {
    close.current?.();
    close.current = null;
    setRun(EMPTY);
  }, []);

  const start = useCallback((launchId: string) => {
    close.current?.();
    setRun({ ...EMPTY, status: "running", narration: "Signal fired — dispatching…" });

    close.current = streamRun(
      launchId,
      (event) =>
        setRun((prev) => {
          const next: RunView = { ...prev, events: [...prev.events, event] };
          const agents = [...next.agents];
          const find = (name: string) => agents.findIndex((a) => a.name === name);

          switch (event.type) {
            case "run_started": {
              next.thread = event.payload.thread_id ?? event.run_id;
              return next;
            }
            case "fan_out": {
              const names: string[] = event.payload.agents ?? [];
              next.agents = names.map((name) => ({
                name,
                question: "",
                state: "dispatching",
                tools: [],
              }));
              next.narration = `Dispatching to ${names.length} specialists in parallel — they never talk to each other.`;
              return next;
            }
            case "agent_started": {
              const index = find(event.agent!);
              if (index >= 0) {
                agents[index] = {
                  ...agents[index],
                  state: "running",
                  question: event.payload.question ?? agents[index].question,
                };
              }
              next.agents = agents;
              next.narration = "Specialists reasoning in parallel…";
              return next;
            }
            case "agent_tool_call": {
              const index = find(event.agent!);
              if (index >= 0) {
                agents[index] = {
                  ...agents[index],
                  tools: [
                    ...agents[index].tools,
                    {
                      tool: event.payload.tool,
                      market: event.payload.args?.market,
                      summary: event.payload.summary,
                      durationMs: event.payload.duration_ms,
                    },
                  ],
                };
              }
              next.agents = agents;
              return next;
            }
            case "agent_returned": {
              const index = find(event.agent!);
              if (index >= 0) {
                agents[index] = {
                  ...agents[index],
                  state: "done",
                  finding: event.payload.finding as Finding,
                };
              }
              next.agents = agents;
              const done = agents.filter((a) => a.state === "done").length;
              next.narration = `${done} of ${agents.length} returned…`;
              return next;
            }
            case "agent_failed": {
              const index = find(event.agent!);
              if (index >= 0) {
                agents[index] = { ...agents[index], state: "failed", error: event.payload.error };
              }
              next.agents = agents;
              return next;
            }
            case "judgment_started": {
              next.status = "reconciling";
              const leans: Record<string, string> = event.payload.leans ?? {};
              const distinct = new Set(Object.values(leans));
              next.narration =
                distinct.size > 1
                  ? "All returned — they disagree. Reconciling without collapsing the dissent…"
                  : "All returned and unanimous. Reconciling…";
              return next;
            }
            case "judgment_returned": {
              next.recommendation = event.payload.recommendation as Recommendation;
              return next;
            }
            case "awaiting_human": {
              next.status = "decided";
              next.narration = "Recommendation ready. A human decides.";
              return next;
            }
            case "decision_recorded": {
              next.decision = event.payload.decision;
              return next;
            }
            case "run_failed":
            case "limit_exceeded": {
              next.status = "failed";
              next.error = JSON.stringify(event.payload);
              next.narration = "Run stopped.";
              return next;
            }
            default:
              return next;
          }
        }),
      () => {
        // The server closes the stream at the human gate; that is expected.
        setRun((prev) =>
          prev.status === "running" || prev.status === "reconciling"
            ? { ...prev, status: "failed", error: "stream closed unexpectedly" }
            : prev,
        );
      },
    );
  }, []);

  return { run, start, reset, setRun };
}
