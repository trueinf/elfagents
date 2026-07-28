import type { Anatomy as AnatomyData } from "../api";

/**
 * Tools versus agents (BUILD_SPEC §1.1, §5.5) — the build's thesis, on screen.
 *
 * Every row here is read from `/api/usecase`, which the registry produces. The
 * classification and the reason for it are data the codebase already holds, so
 * this panel cannot drift out of step with what actually ran. That is the
 * point: the strongest credibility signal is one that would be awkward to fake.
 */
export function Anatomy({ anatomy }: { anatomy: AnatomyData | null }) {
  if (!anatomy) return <div className="empty">Loading…</div>;

  return (
    <section>
      <div className="sec-h">
        <span>What this use case is made of</span>
      </div>
      <p style={{ fontSize: 13.5, color: "var(--muted)", maxWidth: 720, marginBottom: 18, lineHeight: 1.6 }}>
        The test applied to every component: write the question the orchestrator
        asks it. If the answer is deterministic, it is a <b>tool</b>. If it
        requires interpretation, weighing, or judgment under ambiguity, it is an{" "}
        <b>agent</b>. Nothing here is inflated — the signal that fires the whole
        flow is a date comparison, and it is listed as a tool.
      </p>

      <div className="anat">
        <div className="anatcol">
          <h4>
            Agents · {anatomy.agents.length} — they reason
          </h4>
          {anatomy.agents.map((agent) => (
            <div className="anatrow" key={agent.name}>
              <div className="nm">
                {agent.name}
                <span className="kindtag agent">agent</span>
              </div>
              <div className="q">“{agent.question}”</div>
              <div className="why">{agent.why_agent}</div>
              <div className="why" style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--faint)" }}>
                tools: {agent.tools.join(", ") || "—"}
              </div>
            </div>
          ))}
        </div>

        <div className="anatcol">
          <h4>Tools · {anatomy.tools.length} — they look things up</h4>
          {anatomy.tools.map((tool) => (
            <div className="anatrow" key={tool.name}>
              <div className="nm">
                {tool.name}
                <span className="kindtag tool">tool</span>
              </div>
              <div className="why">{tool.description}</div>
              <div className="why" style={{ color: "var(--ink2)" }}>
                <b>Why a tool:</b> {tool.why_tool}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="context">
        <b>Governed definition:</b> every finding carries{" "}
        <code>{anatomy.semantic_version}</code> — the version of the{" "}
        <code>launch_ready</code> metric it was computed against, so a run can
        always be tied back to the semantics that produced it.
      </div>
    </section>
  );
}
