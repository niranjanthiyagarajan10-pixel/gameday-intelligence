import { useState } from "react";
import type { Audience, Roster } from "../types";
import type { Lang } from "../prefs";
import { t } from "../i18n";

interface Evidence {
  slot: string;
  tool: string;
  args: Record<string, unknown>;
  field: string;
  value: string;
}

interface Answer {
  question: string;
  answer: string;
  source: "analyst" | "fallback";
  lang: Lang;
  evidence: Evidence[];
  tools_used: string[];
  limits: string;
}

interface Props {
  room: string;
  roster: Roster;
  lang: Lang;
  depth: Audience;
  favourites: string[];
}

/** Ask the match: the Analyst agent answers from the MCP tools; every number in the answer is re-read by code. */
export function AskPanel({ room, roster, lang, depth, favourites }: Props) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const fav = favourites.map((p) => roster.players[p]?.name).find(Boolean);
  const suggestions = [
    t("Who has created the most danger?"),
    fav ? t("How is {player} playing?", { player: fav }) : t("Who has created the best chances?"),
    t("Which team has the better chance of winning, and why?"),
  ];

  const ask = async (q: string) => {
    const text = q.trim();
    if (text.length < 2 || busy) return;
    setBusy(true);
    setQuestion("");
    try {
      const r = await fetch(`/api/rooms/${room}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text.slice(0, 300), lang, audience: depth }),
      });
      if (r.ok) {
        const answer = (await r.json()) as Answer;
        setAnswers((a) => [answer, ...a].slice(0, 6));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel ask">
      <div className="ask-head">
        <div>
          <span className="ask-kicker">{t("No. 1 Safe Hands")}</span>
          <h3>{t("Ask the match")}</h3>
        </div>
        <span className="ask-tag">{t("Answers from the match data only")}</span>
      </div>
      <div className="pb">
        <form
          className="ask-form"
          onSubmit={(e) => {
            e.preventDefault();
            ask(question);
          }}
        >
          <span className="ask-prompt" aria-hidden="true">?</span>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t("Ask about a player, a team or the score")}
            maxLength={300}
            aria-label={t("Your question")}
          />
          <button type="submit" disabled={busy || question.trim().length < 2}>
            {busy ? t("Checking") : t("Ask")}
          </button>
        </form>
        <div className="ask-chips">
          {suggestions.map((s, i) => (
            <button key={s} onClick={() => ask(s)} disabled={busy}>
              <i>Q{i + 1}</i>
              {s}
            </button>
          ))}
        </div>
        {busy && (
          <div className="ask-busy">
            <span className="ask-scan" />
            {t("The Analyst is checking the match data.")}
          </div>
        )}
        {answers.map((a, i) => (
          <div key={`${a.question}-${i}`} className={`ask-a ${i === 0 ? "latest" : ""}`}>
            <div className="ask-q">{a.question}</div>
            <p>{a.answer}</p>
            <div className="ask-meta">
              <span className={`ask-stamp ${a.source === "analyst" ? "ok" : "no"}`}>
                {a.source === "analyst" ? t("Verified from the match data") : t("No verified answer")}
              </span>
              {a.evidence.length > 0 && <span className="ask-count">{t("{n} values checked", { n: a.evidence.length })}</span>}
              {lang !== "en" && a.lang === "en" && <span className="written">{t("English")}</span>}
            </div>
            {a.evidence.length > 0 && (
              <details className="ask-ev">
                <summary>{t("Show the evidence")}</summary>
                <div className="ask-ev-grid">
                  {a.evidence.map((e) => (
                    <div key={e.slot} className="ask-ev-row">
                      <b className="num">{e.value}</b>
                      <span>
                        {e.tool}({Object.entries(e.args).map(([k, v]) => `${k}=${String(v)}`).join(", ")}).{e.field}
                      </span>
                    </div>
                  ))}
                </div>
                {a.limits && <div className="muted">{t("Limits")}: {a.limits}</div>}
              </details>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
