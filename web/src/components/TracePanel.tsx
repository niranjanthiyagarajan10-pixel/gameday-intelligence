import { useEffect, useState } from "react";
import type { AgentInfo, TraceStep } from "../types";
import { clock } from "../format";

const GOOD = new Set(["ok", "pass"]);
const BAD = new Set(["reject", "timeout", "error"]);

/** Every agent step, live: Narrator drafts, Verifier verdicts, fallbacks, with timings. For judges. */
interface Span {
  trace: string;
  id: string;
  parent: string | null;
  name: string;
  start: number | null;
  ms: number | null;
  status: string;
  attrs: Record<string, string | number | boolean>;
}

/** Agent Framework's OpenTelemetry spans, grouped into workflow runs: each executor and model call, timed. */
function WorkflowSpans() {
  const [data, setData] = useState<{ enabled: boolean; spans: Span[] } | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      fetch("/api/spans?limit=400")
        .then((r) => r.json())
        .then((d) => alive && setData(d))
        .catch(() => undefined);
    load();
    const timer = window.setInterval(load, 3000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);
  if (!data) return <div className="trace-empty">Loading spans.</div>;
  if (!data.enabled) return <div className="trace-empty">OpenTelemetry tracing is off on this server.</div>;
  const runs = new Map<string, Span[]>();
  for (const s of data.spans) runs.set(s.trace, [...(runs.get(s.trace) ?? []), s]);
  const shown = [...runs.values()]
    .map((spans) => spans.filter((s) => s.name.startsWith("workflow.run") || s.name.startsWith("executor.process") || s.attrs["gen_ai.operation.name"]))
    .filter((spans) => spans.some((s) => s.name.startsWith("workflow.run")))
    .reverse()
    .slice(0, 12);
  if (shown.length === 0) return <div className="trace-empty">Workflow runs appear here as key moments happen.</div>;
  return (
    <div className="trace-rows">
      {shown.map((spans) => {
        const run = spans.find((s) => s.name.startsWith("workflow.run"));
        // Nest each model call under the executor it ran in, by walking up its parent spans.
        const all = new Map(data.spans.map((s) => [s.id, s]));
        const owner = (s: Span): string | null => {
          let p = s.parent ? all.get(s.parent) : undefined;
          for (let i = 0; p && i < 12; i++, p = p.parent ? all.get(p.parent) : undefined) {
            if (p.name.startsWith("executor.process")) return p.id;
          }
          return null;
        };
        const byStart = (a: Span, b: Span) => (a.start ?? 0) - (b.start ?? 0);
        const executors = spans.filter((s) => s.name.startsWith("executor.process")).sort(byStart);
        const calls = spans.filter((s) => s.attrs["gen_ai.operation.name"] === "chat");
        const steps = executors.flatMap((e) => [e, ...calls.filter((c) => owner(c) === e.id).sort(byStart)]);
        const loose = calls.filter((c) => !executors.some((e) => owner(c) === e.id));
        steps.push(...loose.sort(byStart));
        return (
          <div key={spans[0].trace} className="span-run">
            <div className="span-head">
              <b>{String(run?.attrs["workflow.name"] ?? "workflow")}</b>
              <span className={run?.status === "ERROR" ? "bad" : "ok"}>{run?.status === "ERROR" ? "error" : "ok"}</span>
              <span className="ms">{run?.ms ?? "-"} ms</span>
            </div>
            {steps.map((s) => {
              const op = s.attrs["gen_ai.operation.name"];
              const tokens = op ? `${s.attrs["gen_ai.usage.input_tokens"] ?? "?"} in, ${s.attrs["gen_ai.usage.output_tokens"] ?? "?"} out` : "";
              return (
                <div key={s.id} className={`span-row ${op ? "llm" : ""}`}>
                  <span className="a">{String(s.attrs["executor.id"] ?? s.attrs["gen_ai.request.model"] ?? s.name)}</span>
                  <span className="act">{op ? `${op}, ${tokens}` : String(s.attrs["executor.type"] ?? "")}</span>
                  <span className="ms">{s.ms ?? "-"} ms</span>
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

export function TracePanel({ steps, agents, onClose }: { steps: TraceStep[]; agents: AgentInfo | null; onClose: () => void }) {
  const [onlyIssues, setOnlyIssues] = useState(false);
  const [view, setView] = useState<"steps" | "spans">("steps");
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
      <div className="trace-tabs">
        <button className={view === "steps" ? "on" : ""} onClick={() => setView("steps")}>
          Agent steps
        </button>
        <button className={view === "spans" ? "on" : ""} onClick={() => setView("spans")}>
          Workflow spans
        </button>
      </div>
      {view === "spans" ? (
        <WorkflowSpans />
      ) : (
        <>
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
        </>
      )}
    </aside>
  );
}
