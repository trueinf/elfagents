import { useMemo, useState } from "react";
import type { OrchestrationEvent } from "../api";
import type { RunView } from "../useRun";

/**
 * The in-product trace (BUILD_SPEC §9 screen 4, §4.1 surface 2).
 *
 * Rendered from the captured event stream — the same events the live view
 * animated against, not a re-fetch from somewhere else. The LangSmith console
 * is surface 3 and stays in its native form; it is linked, never reproduced.
 */
export function TraceDrawer({
  open,
  onClose,
  run,
  launchId,
}: {
  open: boolean;
  onClose: () => void;
  run: RunView;
  launchId: string;
}) {
  const [tab, setTab] = useState<0 | 1 | 2>(0);

  const stats = useMemo(() => {
    const events = run.events;
    const first = events[0]?.at ? Date.parse(events[0].at) : 0;
    const last = events.length ? Date.parse(events[events.length - 1].at) : 0;
    const toolCalls = events.filter((e) => e.type === "agent_tool_call").length;
    return {
      duration: first && last ? `${((last - first) / 1000).toFixed(1)}s` : "—",
      events: events.length,
      toolCalls,
      agents: run.agents.length,
    };
  }, [run.events, run.agents.length]);

  const byAgent = useMemo(() => {
    const map = new Map<string, OrchestrationEvent[]>();
    for (const event of run.events) {
      if (!event.agent) continue;
      const list = map.get(event.agent) ?? [];
      list.push(event);
      map.set(event.agent, list);
    }
    return map;
  }, [run.events]);

  const regulatory = run.agents.find((a) => a.name === "regulatory")?.finding;

  return (
    <>
      <div className={`scrim${open ? " open" : ""}`} onClick={onClose} />
      <aside className={`drawer${open ? " open" : ""}`}>
        <div className="dhead">
          <div>
            <div className="t">Execution trace</div>
            <div className="s">
              {run.events[0]?.run_id ?? "—"} · e.l.f.orchestra · {launchId}
            </div>
          </div>
          <button className="dclose" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="dtabs">
          <button className={`dtab${tab === 0 ? " on" : ""}`} onClick={() => setTab(0)}>
            Run tree
          </button>
          <button className={`dtab${tab === 1 ? " on" : ""}`} onClick={() => setTab(1)}>
            Typed payload
          </button>
          <button className={`dtab${tab === 2 ? " on" : ""}`} onClick={() => setTab(2)}>
            Reconciliation
          </button>
        </div>

        <div className="dbody">
          {tab === 0 && (
            <>
              <div className="runmeta">
                <div className="rm">
                  <div className="k">Wall clock</div>
                  <div className="v">{stats.duration}</div>
                </div>
                <div className="rm">
                  <div className="k">Events</div>
                  <div className="v">{stats.events}</div>
                </div>
                <div className="rm">
                  <div className="k">Tool calls</div>
                  <div className="v">{stats.toolCalls}</div>
                </div>
                <div className="rm">
                  <div className="k">Specialists</div>
                  <div className="v">{stats.agents}</div>
                </div>
              </div>

              <div className="tree">
                <div className="tn">
                  <span className="nm">e.l.f.orchestra.run</span>
                  <span className="dur">{stats.duration}</span>
                </div>
                <div className="indent">
                  <div className="tn tool">
                    <span className="nm">signal.check · countdown threshold</span>
                    <span className="ret">→ FIRED</span>
                  </div>
                  <div className="tn par">
                    <span className="nm">
                      fan_out · {run.agents.length} specialists · PARALLEL
                    </span>
                  </div>
                  <div className="indent">
                    {run.agents.map((agent) => (
                      <div key={agent.name}>
                        <div className="tn agent">
                          <span className="nm">{agent.name}_agent</span>
                          {agent.finding && (
                            <span className={`alean ${agent.finding.lean}`}>
                              {agent.finding.lean}
                            </span>
                          )}
                          <span className="dur">{agent.tools.length} tool calls</span>
                        </div>
                        <div className="indent" style={{ opacity: 0.85 }}>
                          {agent.tools.map((call, index) => (
                            <div className="tn tool" key={index}>
                              <span className="nm">
                                {call.tool}({call.market ?? ""})
                              </span>
                              <span className="ret">→ {call.summary}</span>
                              <span className="dur">{call.durationMs}ms</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="tn">
                    <span className="nm">judgment.reconcile</span>
                    {run.recommendation && (
                      <span className="ret">
                        → {run.recommendation.recommended_action.toUpperCase()} ·
                        dissent={run.recommendation.dissent.length}
                      </span>
                    )}
                  </div>
                  {run.decision && (
                    <div className="tn human">
                      <span className="nm">human_gate.decision</span>
                      <span className="ret">
                        → {String(run.decision.decided_action).toUpperCase()} by{" "}
                        {run.decision.decided_by}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div className="lslink">
                🔎 <span>
                  The same run in raw tooling —{" "}
                  <a
                    href="https://smith.langchain.com"
                    target="_blank"
                    rel="noreferrer"
                  >
                    open it in LangSmith
                  </a>
                  . This panel is our rendered view of the LangGraph event
                  stream; LangSmith is the independent recording, kept in its
                  native form so it can be checked rather than trusted.
                </span>
              </div>
            </>
          )}

          {tab === 1 && (
            <>
              <p style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 12, lineHeight: 1.6 }}>
                The typed object the Regulatory agent returned to the
                orchestrator — schema-validated, so it cannot hand back
                malformed data. This is the contract between every agent and
                the orchestrator; no prose crosses the boundary.
              </p>
              <div className="payload">
                {regulatory
                  ? JSON.stringify(regulatory, null, 2)
                  : "No finding captured yet."}
              </div>
            </>
          )}

          {tab === 2 && (
            <>
              <p style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 14, lineHeight: 1.6 }}>
                How the findings were combined, and why the dissent was kept.
              </p>
              <div className="recon" style={{ background: "#fff", border: "1px solid var(--line)", borderRadius: 12, padding: 18 }}>
                {run.agents.map((agent) => (
                  <div
                    key={agent.name}
                    style={{
                      display: "flex",
                      gap: 10,
                      alignItems: "center",
                      padding: "9px 0",
                      borderBottom: "1px solid var(--line)",
                      fontSize: 12.5,
                    }}
                  >
                    <span style={{ width: 100, fontWeight: 700, textTransform: "capitalize" }}>
                      {agent.name}
                    </span>
                    {agent.finding && (
                      <span className={`alean ${agent.finding.lean}`}>
                        {agent.finding.lean}
                      </span>
                    )}
                    <span style={{ fontSize: 11.5, color: "var(--muted)" }}>
                      {byAgent.get(agent.name)?.filter((e) => e.type === "agent_tool_call").length ?? 0}{" "}
                      tool calls
                    </span>
                  </div>
                ))}
                {run.recommendation && (
                  <div
                    style={{
                      marginTop: 14,
                      padding: 14,
                      background: "var(--partial-bg)",
                      borderRadius: 10,
                      fontSize: 12.5,
                      lineHeight: 1.6,
                    }}
                  >
                    <b style={{ color: "var(--partial)" }}>Reconciliation:</b>{" "}
                    {run.recommendation.reconciliation}
                  </div>
                )}
                {run.recommendation?.dissent.map((entry, index) => (
                  <div
                    key={index}
                    style={{
                      marginTop: 10,
                      padding: 14,
                      background: "var(--slip-bg)",
                      borderRadius: 10,
                      fontSize: 12.5,
                      lineHeight: 1.6,
                    }}
                  >
                    <b style={{ color: "var(--slip)" }}>Preserved dissent:</b> {entry}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
