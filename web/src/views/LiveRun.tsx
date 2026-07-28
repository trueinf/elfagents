import type { Launch } from "../api";
import type { RunView } from "../useRun";

/**
 * The live orchestration view (BUILD_SPEC §9 screen 2).
 *
 * Hub and spoke: one orchestrator dispatching to N specialists that never
 * address each other. Lane states come from the event stream, so what animates
 * is what happened.
 */
export function LiveRun({
  launch,
  run,
  onRun,
  onSeeDecision,
}: {
  launch: Launch;
  run: RunView;
  onRun: () => void;
  onSeeDecision: () => void;
}) {
  const busy = run.status === "running" || run.status === "reconciling";
  const returned = run.agents.filter((a) => a.state === "done").length;

  return (
    <section>
      <div className="runhead">
        <div className="sku">
          {launch.launch_id} · {launch.brand} · {launch.target_markets.join(" · ")} ·
          triggered at T-minus {launch.countdown_weeks} weeks
        </div>
        <h1>{launch.sku_name}</h1>
      </div>

      <div className={`conductor${busy ? " busy" : ""}`}>
        <div className="cbadge">
          <div className="ring" />
          <b>eO</b>
        </div>
        <div className="cmeta">
          <div className="cn">
            e.l.f.orchestra <span className="role">Orchestrator</span>
          </div>
          <div className="cnarr">
            {run.narration || "Idle — select run to fire the flow."}
          </div>
        </div>
        <div className="cstat">
          <div className="big">
            {run.status === "idle"
              ? "ready"
              : run.status === "decided"
                ? "decided"
                : run.status === "failed"
                  ? "stopped"
                  : run.status}
          </div>
          <div className="sub">
            {run.agents.length
              ? `${returned} / ${run.agents.length} returned`
              : "not dispatched"}
          </div>
        </div>
      </div>

      <div className="canvas">
        <div className="spokelabel">
          Hub-and-spoke — <b>e.l.f.orchestra dispatches to each specialist and
          collects their findings.</b> The specialists never talk to each other
          (star topology).
        </div>

        {run.agents.length === 0 && (
          <div className="empty">
            Nothing dispatched yet. The signal has already fired for this launch
            — it reached the countdown threshold. Run the flow to fan out.
          </div>
        )}

        <div className="lanes">
          {run.agents.map((agent) => (
            <div className={`lane ${agent.state}`} key={agent.name}>
              <div className="spoke">
                <div className="wire" />
              </div>
              <div className="acard">
                <div className="row1">
                  <span className="aname">{agent.name}</span>
                  <span className="aq">{agent.question}</span>
                  {agent.finding && (
                    <span className={`alean ${agent.finding.lean}`}>
                      {agent.finding.lean}
                    </span>
                  )}
                  <span className={`astate ${agent.state}`}>
                    <span className="d" />
                    {agent.state === "done"
                      ? "returned"
                      : agent.state === "running"
                        ? "reasoning"
                        : agent.state === "failed"
                          ? "failed"
                          : "dispatched"}
                  </span>
                </div>

                {agent.tools.length > 0 && (
                  <div className="tools">
                    {agent.tools.map((call, index) => (
                      <div className="tc" key={index}>
                        <span className="nm">
                          {call.tool}({call.market ?? ""})
                        </span>
                        <span className="rs">→ {call.summary}</span>
                        <span style={{ marginLeft: "auto" }}>{call.durationMs}ms</span>
                      </div>
                    ))}
                  </div>
                )}

                {agent.finding && (
                  <div className="found">
                    <b>Found:</b> {agent.finding.rationale}
                  </div>
                )}
                {agent.error && (
                  <div className="found" style={{ color: "var(--hold)" }}>
                    <b>Failed:</b> {agent.error}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="runctl">
          <button className="btn" onClick={onRun} disabled={busy}>
            {run.status === "idle" ? "▷ Run the flow" : "▷ Run again"}
          </button>
          {run.recommendation && (
            <button className="btn primary" onClick={onSeeDecision}>
              See reconciled decision →
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
