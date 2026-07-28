import { useCallback, useEffect, useState } from "react";
import {
  type Anatomy as AnatomyData,
  type Launch,
  type Lean,
  getAnatomy,
  getLaunches,
  submitDecision,
} from "./api";
import type { GridMode } from "./components/MarketGrid";
import { useRun } from "./useRun";
import { Anatomy } from "./views/Anatomy";
import { Decision } from "./views/Decision";
import { LiveRun } from "./views/LiveRun";
import { TraceDrawer } from "./views/TraceDrawer";

type View = "live" | "decision" | "anatomy";

const SHAPE_CHIP: Record<string, string> = {
  all_ready: "go",
  mixed: "partial",
  none_ready: "slip",
};

export default function App() {
  const [launches, setLaunches] = useState<Launch[]>([]);
  const [anatomy, setAnatomy] = useState<AnatomyData | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<View>("live");
  const [traceOpen, setTraceOpen] = useState(false);
  const [gridMode, setGridMode] = useState<GridMode>("adaptive");
  const [deciding, setDeciding] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const { run, start, reset, setRun } = useRun();

  useEffect(() => {
    getLaunches()
      .then((data) => {
        setLaunches(data);
        setSelected((current) => current ?? data[0]?.launch_id ?? null);
      })
      .catch((e) => setError(String(e)));
    getAnatomy().then(setAnatomy).catch(() => undefined);
  }, []);

  const launch = launches.find((l) => l.launch_id === selected) ?? null;

  const select = useCallback(
    (id: string) => {
      setSelected(id);
      setView("live");
      setError(undefined);
      reset();
    },
    [reset],
  );

  const decide = useCallback(
    async (action: Lean, note: string) => {
      if (!launch) return;
      setDeciding(true);
      setError(undefined);
      try {
        const result = await submitDecision(launch.launch_id, {
          decided_action: action,
          note,
          per_market: run.recommendation?.per_market_action ?? [],
        });
        setRun((prev) => ({ ...prev, decision: result.decision }));
      } catch (e) {
        setError(
          `Could not record the decision: ${String(e)}. The run stays paused — nothing was written.`,
        );
      } finally {
        setDeciding(false);
      }
    },
    [launch, run.recommendation, setRun],
  );

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">
          <div className="dot">e</div>
          <div>
            <b>elfagent</b>
            <br />
            <span>LAUNCH READINESS</span>
          </div>
        </div>

        <div className="rail-h">Gate review · this week</div>
        {launches.map((item) => (
          <button
            className={`launch${item.launch_id === selected ? " active" : ""}`}
            key={item.launch_id}
            onClick={() => select(item.launch_id)}
          >
            <div className="id">{item.launch_id}</div>
            <div className="nm">{item.sku_name}</div>
            <div className="meta">
              <span className={`chip ${SHAPE_CHIP[item.readiness_shape] ?? "pending"}`}>
                <span className="d" />
                {item.readiness_shape.replace("_", " ")}
              </span>
              <span>{item.target_markets.join(" · ")}</span>
            </div>
          </button>
        ))}

        <div className="rail-h" style={{ marginTop: 14 }}>
          Platform
        </div>
        <button
          className={`launch${view === "anatomy" ? " active" : ""}`}
          onClick={() => setView("anatomy")}
        >
          <div className="nm">Agents &amp; tools</div>
          <div className="meta">
            <span>what is what, and why</span>
          </div>
        </button>
      </aside>

      <main className="main">
        <div className="crumb">
          <b>Launch Readiness</b>
          <span className="sep">/</span>
          <span>Commercialization Stage-Gate</span>
          <span className="stagepill">Gate 4 · Go-to-market readiness</span>
        </div>

        {view !== "anatomy" && (
          <div className="viewbar">
            <button className={view === "live" ? "on" : ""} onClick={() => setView("live")}>
              ① Live run
            </button>
            <button
              className={view === "decision" ? "on" : ""}
              onClick={() => setView("decision")}
              disabled={!run.recommendation}
            >
              ② Decision
            </button>
          </div>
        )}

        {error && view === "live" && <div className="err">{error}</div>}

        {view === "anatomy" ? (
          <Anatomy anatomy={anatomy} />
        ) : !launch ? (
          <div className="empty">No launches at the gate.</div>
        ) : view === "live" ? (
          <LiveRun
            launch={launch}
            run={run}
            onRun={() => start(launch.launch_id)}
            onSeeDecision={() => setView("decision")}
          />
        ) : (
          <Decision
            launch={launch}
            run={run}
            gridMode={gridMode}
            onGridMode={setGridMode}
            onDecide={decide}
            onOpenTrace={() => setTraceOpen(true)}
            deciding={deciding}
            error={error}
          />
        )}
      </main>

      <TraceDrawer
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
        run={run}
        launchId={launch?.launch_id ?? "—"}
      />
    </div>
  );
}
