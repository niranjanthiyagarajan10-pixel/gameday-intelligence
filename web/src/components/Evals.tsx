import { useEffect, useState } from "react";
import { t } from "../i18n";

interface Row {
  check: string;
  planted: number;
  caught: number;
}
interface LiveRow {
  agent: string;
  lines: number;
  verified: number;
  first_draft: number;
  avg_drafts: number;
  p50_ms: number;
  p95_ms: number;
}
interface Question {
  question: string;
  expected: string[];
  answer: string;
  correct: boolean;
  source?: string;
  ms: number;
}
interface Report {
  planted?: { moments: number; planted: number; caught: number; clean: number; clean_passed: number; rows: Row[]; at: string };
  live?: { rows: LiveRow[]; rejections: [string, number][]; untraced: number; at: string; examples: Record<string, string> };
  analyst?: { questions: Question[]; correct: number; refusals: { question: string; answer: string; honest: boolean }[]; honest: number; p50_ms: number };
}

const fmt = (n: number) => n.toLocaleString("en-GB");
const pct = (a: number, b: number) => (b ? `${Math.round((a / b) * 100)}%` : "-");

function Big({ value, of, label, note }: { value: number; of: number; label: string; note?: string }) {
  const full = value === of;
  return (
    <div className="ev-big">
      <b className={`num ${full ? "up" : ""}`}>
        {fmt(value)}
        <small> / {fmt(of)}</small>
      </b>
      <span className="label">{label}</span>
      {note && <p>{note}</p>}
    </div>
  );
}

/** How we know the agents tell the truth: planted errors, live agent runs and Ask the match accuracy. */
export function Evals() {
  const [r, setR] = useState<Report | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    fetch("/api/evals")
      .then((x) => (x.ok ? x.json() : Promise.reject()))
      .then(setR)
      .catch(() => setFailed(true));
  }, []);
  if (failed) return <div className="empty" style={{ padding: 24 }}>{t("No eval report yet. Run python -m tests.agent_eval.")}</div>;
  if (!r) return <div className="empty" style={{ padding: 24 }}>{t("Loading the eval report.")}</div>;
  const p = r.planted;
  const live = r.live;
  const a = r.analyst;
  const groups = new Map<string, Row[]>();
  for (const row of p?.rows ?? []) {
    const [agent, check] = row.check.split(": ");
    groups.set(agent, [...(groups.get(agent) ?? []), { ...row, check }]);
  }
  const liveTotal = live?.rows.reduce((s, x) => s + x.lines, 0) ?? 0;
  const liveVerified = live?.rows.reduce((s, x) => s + x.verified, 0) ?? 0;

  return (
    <div className="ev">
      <section className="ev-hero">
        <span className="label">Agent evals &middot; how we know the words are true</span>
        <h1>{t("We tried to make the agents lie")}</h1>
        <p>
          {t("Every agent line is checked by code before a fan sees it. To prove the checks work, we took")} {p ? fmt(p.moments) : "every"} real key moments from the five
          scenario matches and broke their lines on purpose, the way language models break facts. Then we ran the real agents on Microsoft Foundry and checked them again.
        </p>
      </section>

      <section className="ev-bigs">
        {p && <Big value={p.caught} of={p.planted} label={t("Planted errors caught")} note={t("Typed numbers and names, false claims, made-up details, broken translations, fake tools.")} />}
        {p && <Big value={p.clean_passed} of={p.clean} label={t("Clean lines passed")} note={t("A check that rejects good lines is broken too.")} />}
        {live && <Big value={liveVerified} of={liveTotal} label={t("Live agent lines verified")} note={t("Narrator, Commentator in three styles, Personalizer, on gpt-4.1-mini.")} />}
        {a && (
          <Big value={a.correct} of={a.questions.length} label={t("Ask the match answers correct")}
            note={t("Checked against the same MCP tools. {n} wrong answers shown; the rest declined honestly.", { n: a.questions.filter((q) => !q.correct && q.source !== "fallback").length })} />
        )}
        {live && (
          <div className="ev-big">
            <b className={`num ${live.untraced === 0 ? "up" : "down"}`}>{live.untraced}</b>
            <span className="label">{t("Numbers no slot supplied")}</span>
            <p>{t("Every number in every published line came from code.")}</p>
          </div>
        )}
      </section>

      {p && (
        <section className="lg-panel">
          <div className="ev-h">
            <h2 className="lg-h">{t("Planted errors, by check")}</h2>
            <span className="label">{t("Run")} {p.at} &middot; no model needed &middot; runs in CI</span>
          </div>
          <div className="ev-groups">
            {[...groups.entries()].map(([agent, rows]) => (
              <div key={agent} className="ev-group">
                <h3>{agent}</h3>
                {rows.map((row) => (
                  <div key={row.check} className="ev-row">
                    <span>{row.check}</span>
                    <div className="ev-bar">
                      <i style={{ width: `${(row.caught / row.planted) * 100}%` }} className={row.caught === row.planted ? "full" : ""} />
                    </div>
                    <b className="num">
                      {fmt(row.caught)}/{fmt(row.planted)}
                    </b>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </section>
      )}

      {live && (
        <div className="lg-two">
          <section className="lg-panel">
            <div className="ev-h">
              <h2 className="lg-h">{t("The live agents")}</h2>
              <span className="label">{t("Run")} {live.at} &middot; Microsoft Foundry</span>
            </div>
            <table className="lg-table num">
              <thead>
                <tr>
                  <th className="l">{t("Agent")}</th>
                  <th>{t("Lines")}</th>
                  <th>{t("Verified")}</th>
                  <th>{t("First draft")}</th>
                  <th>{t("Drafts")}</th>
                  <th>p50</th>
                  <th>p95</th>
                </tr>
              </thead>
              <tbody>
                {live.rows.map((x) => (
                  <tr key={x.agent}>
                    <td className="l ev-agent">{x.agent}</td>
                    <td>{x.lines}</td>
                    <td className={x.verified === x.lines ? "up" : ""}>{pct(x.verified, x.lines)}</td>
                    <td>{pct(x.first_draft, x.lines)}</td>
                    <td>{x.avg_drafts.toFixed(2)}</td>
                    <td>{(x.p50_ms / 1000).toFixed(1)}s</td>
                    <td>{(x.p95_ms / 1000).toFixed(1)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="ev-fine">A line that fails the Verifier goes back to its agent with the reason, at most twice; then the template is used. Verified means the agent's own words went live.</p>
          </section>
          <section className="lg-panel">
            <h2 className="lg-h">{t("What the Verifier caught in real drafts")}</h2>
            <div className="ev-caught">
              {live.rejections.map(([reason, n]) => (
                <div key={reason}>
                  <b className="num">{n}</b>
                  <span>{reason}</span>
                </div>
              ))}
              {live.rejections.length === 0 && <div className="empty">{t("No draft was rejected in this run.")}</div>}
            </div>
          </section>
        </div>
      )}

      {a && (
        <section className="lg-panel">
          <div className="ev-h">
            <h2 className="lg-h">{t("Ask the match")}</h2>
            <span className="label">
              {a.correct}/{a.questions.length} correct &middot; {a.honest}/{a.refusals.length} honest when the data cannot answer &middot; p50 {(a.p50_ms / 1000).toFixed(1)}s
            </span>
          </div>
          <div className="ev-qs">
            {a.questions.map((q) => (
              <div key={q.question} className={`ev-q ${q.correct ? "ok" : q.source === "fallback" ? "held" : "no"}`}>
                <span className="mark">{q.correct ? "Right" : q.source === "fallback" ? "Declined" : "Wrong"}</span>
                <div>
                  <b>{q.question}</b>
                  <p>{q.answer}</p>
                  <span className="label">Truth from the tools: {q.expected.join(", ")}</span>
                </div>
              </div>
            ))}
            {a.refusals.map((q) => (
              <div key={q.question} className={`ev-q ${q.honest ? "ok" : "no"}`}>
                <span className="mark">{q.honest ? "Honest" : "Guessed"}</span>
                <div>
                  <b>{q.question}</b>
                  <p>{q.answer}</p>
                  <span className="label">{t("The data cannot answer this")}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
