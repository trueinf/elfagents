import type { MarketReadiness } from "../api";

/**
 * Per-market readiness, with a toggle between two honest views.
 *
 * ADAPTIVE shows only the markets this launch actually targets. A US-only
 * launch gets one card, and nothing on screen implies otherwise.
 *
 * PINNED always shows the full US/DE/UK set, marking untargeted markets as out
 * of scope. This makes *absence* legible — "this launch does not target
 * Germany" is a different fact from "Germany is blocked", and a grid that
 * silently drops the column cannot distinguish them.
 *
 * Neither is right for every case, which is why it is a toggle rather than a
 * decision baked in.
 */

export type GridMode = "adaptive" | "pinned";

const PINNED = ["US", "DE", "UK"];

const LABEL: Record<string, string> = {
  US: "United States",
  DE: "Germany",
  UK: "United Kingdom",
};

export function GridToggle({
  mode,
  onChange,
}: {
  mode: GridMode;
  onChange: (mode: GridMode) => void;
}) {
  return (
    <div className="gridtoggle" role="group" aria-label="Market grid mode">
      <button
        className={mode === "adaptive" ? "on" : ""}
        onClick={() => onChange("adaptive")}
        title="Show only the markets this launch targets"
      >
        Targeted
      </button>
      <button
        className={mode === "pinned" ? "on" : ""}
        onClick={() => onChange("pinned")}
        title="Always show US / DE / UK, marking untargeted markets out of scope"
      >
        All markets
      </button>
    </div>
  );
}

export function MarketGrid({
  markets,
  targetMarkets,
  mode,
}: {
  markets: MarketReadiness[];
  targetMarkets: string[];
  mode: GridMode;
}) {
  const byMarket = new Map(markets.map((m) => [m.market, m]));
  const columns =
    mode === "pinned"
      ? Array.from(new Set([...PINNED, ...targetMarkets]))
      : targetMarkets.filter((m) => byMarket.has(m) || true);

  return (
    <div className="markets">
      {columns.map((code) => {
        const inScope = targetMarkets.includes(code);
        const entry = byMarket.get(code);

        if (!inScope) {
          return (
            <div className="mkt out" key={code}>
              <div className="mkt-top">
                <span className="flag">
                  <span className="code">{code}</span> {LABEL[code] ?? code}
                </span>
                <span className="chip pending">
                  <span className="d" />
                  Not targeted
                </span>
              </div>
              <ul className="reasons">
                <li>
                  <span className="i na">–</span>
                  This launch does not target {LABEL[code] ?? code}. No
                  specialist assessed it.
                </li>
              </ul>
            </div>
          );
        }

        const ready = entry?.ready;
        const tone = ready === true ? "go" : "slip";
        return (
          <div className={`mkt ${tone}`} key={code}>
            <div className="mkt-top">
              <span className="flag">
                <span className="code">{code}</span> {LABEL[code] ?? code}
              </span>
              <span className={`chip ${tone}`}>
                <span className="d" />
                {ready === true ? "Go" : ready === false ? "Hold" : "Conditional"}
              </span>
            </div>
            <ul className="reasons">
              <li>
                <span className={`i ${ready === true ? "ok" : entry?.gate_type === "hard" ? "no" : "warn"}`}>
                  {ready === true ? "✓" : entry?.gate_type === "hard" ? "✕" : "!"}
                </span>
                {entry?.detail ?? "No assessment recorded."}
              </li>
              {entry?.gate_type && (
                <li>
                  <span className={`i ${entry.gate_type === "hard" ? "no" : "warn"}`}>
                    {entry.gate_type === "hard" ? "✕" : "!"}
                  </span>
                  {entry.gate_type === "hard"
                    ? "Hard gate — cannot be traded against a schedule preference."
                    : "Conditional gate — a path through it exists."}
                </li>
              )}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
