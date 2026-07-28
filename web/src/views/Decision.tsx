import { useState } from "react";
import type { Launch, Lean } from "../api";
import { GridToggle, MarketGrid, type GridMode } from "../components/MarketGrid";
import type { RunView } from "../useRun";

const QUESTIONS: Record<string, string> = {
  regulatory: "Is it legally clear per market?",
  supply: "Can we supply the window, and what does waiting cost?",
  retailer: "Which markets can receive, and is a partial coherent?",
  packaging: "Is artwork ready, and where is the long pole?",
};

/**
 * Recommendation and the human gate (BUILD_SPEC §9 screen 3).
 *
 * The dissent panel is not decoration. When the specialists disagreed, the
 * minority view is rendered at full strength before the decision buttons —
 * the human is meant to be able to overrule the recommendation on the strength
 * of it.
 */
export function Decision({
  launch,
  run,
  gridMode,
  onGridMode,
  onDecide,
  onOpenTrace,
  deciding,
  error,
}: {
  launch: Launch;
  run: RunView;
  gridMode: GridMode;
  onGridMode: (mode: GridMode) => void;
  onDecide: (action: Lean, note: string) => void;
  onOpenTrace: () => void;
  deciding: boolean;
  error?: string;
}) {
  const [note, setNote] = useState("");
  const recommendation = run.recommendation;

  if (!recommendation) {
    return (
      <div className="empty">
        No recommendation yet. Run the flow first — judgment reconciles only
        once every specialist has returned.
      </div>
    );
  }

  const action = recommendation.recommended_action;
  const leans = new Set(recommendation.findings.map((f) => f.lean));
  const contested = leans.size > 1;
  const decided = run.decision;

  return (
    <section>
      {error && <div className="err">{error}</div>}

      {run.resumed && (
        <div className="resumed-note">
          <b>Resumed from checkpoint.</b> The process that ran these
          specialists is gone. Everything below — the findings, the
          reconciliation, the preserved dissent — was read back from durable
          state, not re-computed, and the decision below still resumes the same
          graph. The live-run view is empty for this run because tool timings
          were events, and events do not survive the process that emitted them.
        </div>
      )}

      {decided && (
        <div className="decided">
          <h4>Decision recorded</h4>
          <p>
            <b>{String(decided.decided_action).toUpperCase()}</b> by{" "}
            {decided.decided_by}
            {decided.followed_recommendation
              ? " — followed the recommendation."
              : " — overruled the recommendation."}
            {decided.note ? ` “${decided.note}”` : ""}
          </p>
        </div>
      )}

      <div className={`hero ${action}`}>
        <div className="hero-top">
          <div>
            <div className="sku">
              {launch.launch_id} · {launch.brand} · reconciled by e.l.f.orchestra
              from {recommendation.findings.length} parallel specialists
            </div>
            <h1>{launch.sku_name}</h1>
            <div className="verdict">
              <span className="lbl">Recommendation</span>
              <span className={`big ${action}`}>
                {action === "partial" ? "Partial launch" : action}
              </span>
            </div>
            <p className="because">{recommendation.reconciliation}</p>
            <div className="conf">
              <span>Confidence</span>
              <span className="bar">
                <span
                  className="fill"
                  style={{ width: `${Math.round(recommendation.confidence * 100)}%` }}
                />
              </span>
              <span>{recommendation.confidence.toFixed(2)}</span>
            </div>
          </div>

          <div className="actions">
            <button
              className="btn pink"
              disabled={deciding || !!decided}
              onClick={() => onDecide(action, note)}
            >
              Approve {action}
            </button>
            {(["go", "partial", "slip", "hold"] as Lean[])
              .filter((option) => option !== action)
              .map((option) => (
                <button
                  key={option}
                  className="btn"
                  disabled={deciding || !!decided}
                  onClick={() => onDecide(option, note)}
                >
                  Override → {option}
                </button>
              ))}
            <textarea
              placeholder="Note (optional)"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              disabled={!!decided}
              style={{
                fontFamily: "inherit",
                fontSize: 12,
                padding: 8,
                borderRadius: 9,
                border: "1.5px solid var(--line2)",
                resize: "vertical",
                minHeight: 54,
              }}
            />
          </div>
        </div>
      </div>

      <div className="sec-h">
        <span>The decision, by market</span>
        <GridToggle mode={gridMode} onChange={onGridMode} />
      </div>
      <MarketGrid
        markets={recommendation.per_market_action}
        targetMarkets={launch.target_markets}
        mode={gridMode}
      />

      {contested ? (
        <div className="contested">
          <div className="ic">⚖</div>
          <div>
            <h4>Not unanimous — the dissent was preserved, not discarded</h4>
            {recommendation.dissent.map((entry, index) => (
              <p key={index}>{entry}</p>
            ))}
          </div>
        </div>
      ) : (
        <div className="unanimous">
          <b>Unanimous.</b> All {recommendation.findings.length} specialists
          reached the same lean independently, so there is no minority view to
          preserve. The dissent list is empty because nothing dissented — not
          because anything was dropped.
        </div>
      )}

      <div className="sec-h">
        <span>What each specialist decided</span>
        <button className="btn ghost" onClick={onOpenTrace}>
          Open full trace →
        </button>
      </div>
      <div className="stories">
        {recommendation.findings.map((finding) => {
          const dissented = finding.lean !== action;
          return (
            <div className={`story${dissented ? " dissent" : ""}`} key={finding.agent}>
              <div className="who">
                <span className="nm">{finding.agent}</span>
                <span className={`alean ${finding.lean}`} style={{ width: "fit-content" }}>
                  {finding.lean}
                </span>
                {dissented && <span className="dbadge">▎dissented</span>}
              </div>
              <div className="arc">
                <span className="q">
                  Asked: {QUESTIONS[finding.agent] ?? "—"}
                </span>
                <br />
                {finding.rationale}
              </div>
              <div className="verdictcol">
                <div className="cf">confidence {finding.confidence.toFixed(2)}</div>
                <div className="cfbar">
                  <div
                    className="cffill"
                    style={{
                      width: `${Math.round(finding.confidence * 100)}%`,
                      background: dissented ? "var(--slip)" : "var(--go)",
                    }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="context">
        <b>Where this sits:</b> the launch decision cockpit for the
        Commercialization / PMO team at the go-to-market Stage-Gate.
        e.l.f.orchestra assembles readiness across every specialist into one
        recommendation — but the gate decision stays with the launch owner.
        Nothing here ships product or writes to a system of record; it
        recommends, a human decides, the decision is recorded.
      </div>
    </section>
  );
}
