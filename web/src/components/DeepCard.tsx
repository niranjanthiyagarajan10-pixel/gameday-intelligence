import { useState } from "react";
import type { DeepCard as Deep, Roster } from "../types";
import type { Lang } from "../prefs";

/** Threat share in five-minute buckets: the home side's share from the top, the away side's from the bottom. */
function ThreatChart({ chart, roster }: { chart: Deep["chart"]; roster: Roster }) {
  const h = roster.clubs.home;
  const a = roster.clubs.away;
  const w = 280;
  const top = 18;
  const height = 110;
  const bw = chart.length ? (w - 30) / chart.length : 0;
  return (
    <svg viewBox={`0 0 ${w} ${top + height + 22}`} width="100%" role="img" aria-label="Share of the threat, five minutes at a time">
      <text x={0} y={11} fill="var(--text-muted)" fontSize={10} fontWeight={600}>
        SHARE OF THE THREAT, 5 MIN AT A TIME
      </text>
      <line x1={30} x2={w} y1={top + height / 2} y2={top + height / 2} stroke="var(--line-dash)" strokeDasharray="2 4" />
      <text x={24} y={top + 8} fill="var(--text-dim)" fontSize={9} textAnchor="end">{h.short}</text>
      <text x={24} y={top + height} fill="var(--text-dim)" fontSize={9} textAnchor="end">{a.short}</text>
      {chart.map((c, i) => {
        const x = 30 + i * bw + 2;
        const hh = c.home * height;
        return (
          <g key={c.start}>
            <rect x={x} y={top} width={bw - 4} height={hh} fill={h.primary} />
            <rect x={x} y={top + hh} width={bw - 4} height={height - hh} fill={a.primary} opacity={0.85} />
            <text x={x + (bw - 4) / 2} y={top + height + 14} fill="var(--text-muted)" fontSize={9} textAnchor="middle">
              {c.start}'
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** The In-depth Analyst's latest read, with the earlier ones a click away. */
export function DeepCards({ cards, roster, lang }: { cards: Deep[]; roster: Roster; lang: Lang }) {
  const [shown, setShown] = useState<string | null>(null);
  if (cards.length === 0) {
    return (
      <div className="panel deep">
        <div className="deep-empty">
          <span className="label">In-depth analysis</span>
          <p>The In-depth Analyst writes its first read at 15 minutes, then every 15 minutes and after every goal or red card.</p>
        </div>
      </div>
    );
  }
  const card = cards.find((c) => c.id === shown) ?? cards[cards.length - 1];
  const t = (lang !== "en" && card.langs?.[lang]) || card;
  return (
    <div className="panel deep">
      <div className="deep-main">
        <div>
          <span className="label">
            {card.minute}' &middot; Analyst read &middot; {card.window[0]} to {card.window[1]}
          </span>
          <h3 lang={lang}>{t.headline}</h3>
          <p lang={lang}>{t.text}</p>
          <div className="deep-by">
            {card.source === "agent" ? <span className="verified">Verified</span> : <span className="label">Template</span>}
            <span className="label">{card.source === "agent" ? "In-depth Analyst agent" : "Filled from the match engine"}</span>
          </div>
        </div>
        <div className="deep-chart">
          <ThreatChart chart={card.chart} roster={roster} />
        </div>
      </div>
      {cards.length > 1 && (
        <div className="deep-history">
          <span className="label">Earlier reads</span>
          {cards.map((c) => (
            <button key={c.id} className={c.id === card.id ? "on" : ""} onClick={() => setShown(c.id)}>
              {c.minute}'
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
