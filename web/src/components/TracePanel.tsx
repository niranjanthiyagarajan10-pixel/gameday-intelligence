import { useState } from "react";
import type { AgentInfo, TraceStep } from "../types";
import { clock } from "../format";

const GOOD = new Set(["ok", "pass"]);
const BAD = new Set(["reject", "timeout", "error"]);

/** Every agent step, live: Narrator drafts, Verifier verdicts, fallbacks, with timings. For judges. */
export function TracePanel({ steps, agents, onClose }: { steps: TraceStep[]; agents: AgentInfo | null; onClose: () => void }) {
  const [onlyIssues, setOnlyIssues] = useState(false);
  const drafts = steps.filter((s) => s.agent === "Narrator" && s.status === "ok");
  const passes = steps.filter((s) => s.agent === "Verifier" && s.status === "pass").length;
  const rejects = steps.filter((s) => s.agent === "Verifier" && s.status === "reject").length;
  const fallbacks = steps.filter((s) => s.agent === "Fallback").length;
  const avg = drafts.length ? Math.round(drafts.reduce((a, s) => a + s.ms, 0) / drafts.length) : null;
  const shown = [...steps].reverse().filter((s) => !onlyIssues || !GOOD.has(s.status)).slice(0, 200);

  return (
    <aside className="trace" aria-label="Agent trace">
      <div className="trace-head">
        <b>Agent trace</b>
        <button onClick={onClose} aria-label="Close the trace">
          Close
        </button>
      </div>
      <div className="trace-backend">
        {agents?.live ? (
          <>
            <span className="ok">&#9679;</span> {agents.backend === "replay" ? "Replay cache" : "Microsoft Foundry"} &middot; {agents.model}
          </>
        ) : (
          <>
            <span className="muted">&#9679;</span> No model connected: every card uses its verified template.
          </>
        )}
      </div>
      <div className="trace-sum">
        <span>drafts {drafts.length}</span>
        <span className="ok">passed {passes}</span>
        <span className="bad">rejected {rejects}</span>
        <span>fallbacks {fallbacks}</span>
        <span>avg {avg === null ? "-" : `${avg} ms`}</span>
      </div>
      <label className="trace-filter">
        <input type="checkbox" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} /> Only rejections, timeouts
        and fallbacks
      </label>
      <div className="trace-rows" role="log" aria-live="polite">
        {shown.length === 0 && <div className="trace-empty">Agent steps appear here as key moments happen.</div>}
        {shown.map((s, i) => (
          <div key={`${s.moment_id}-${s.audience}-${s.agent}-${s.action}-${i}`} className="trace-row">
            <span className="t">{clock(s.t)}</span>
            <span className="a">{s.agent}</span>
            <span className="act">
              {s.action}
              {s.audience !== "both" ? ` ${s.audience}` : ""}
            </span>
            <span className={`st ${GOOD.has(s.status) ? "ok" : BAD.has(s.status) ? "bad" : "muted"}`}>{s.status}</span>
            <span className="ms">{s.ms} ms</span>
            {s.detail && (
              <span className="d" title={s.detail}>
                {s.detail}
              </span>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}
