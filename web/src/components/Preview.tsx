import { useEffect, useState, type CSSProperties } from "react";
import { Crest } from "./Crest";
import type { Lang } from "../prefs";
import { t } from "../i18n";

export interface LeagueClub {
  id: string;
  name: string;
  short: string;
  primary: string;
  secondary: string;
  formation: string;
  nickname: string;
  ground: string;
  style: string;
}
interface Watch {
  player_id: string;
  name: string;
  side: "home" | "away";
  number: number;
  label: string;
  value: string;
}
interface Meeting {
  season: "last" | "this";
  matchday: number;
  home: string;
  away: string;
  score: [number, number];
}
interface PreviewData {
  home: string;
  away: string;
  headline: string;
  story: string;
  source: "agent" | "template";
  langs: Record<string, { headline: string; story: string }>;
  forecast: [number, number, number];
  watch: Watch[];
  h2h: Meeting[];
  form: { home: string[]; away: string[] };
  table: { home: { position: number; points: number }; away: { position: number; points: number } };
  facts: Record<string, string>;
}

/** Club identities for crests and names, shared by the Preview and After the match. */
export function useClubs(): Record<string, LeagueClub> | null {
  const [clubs, setClubs] = useState<Record<string, LeagueClub> | null>(null);
  useEffect(() => {
    getJson<{ clubs: Record<string, LeagueClub> }>("/api/league").then((d) => d && setClubs(d.clubs));
  }, []);
  return clubs;
}

/** GET with a few retries, so a dropped request on a flaky network does not leave a page empty. */
export async function getJson<T>(url: string, tries = 3): Promise<T | null> {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url);
      if (r.ok) return (await r.json()) as T;
    } catch {
      /* try again */
    }
    await new Promise((done) => setTimeout(done, 800 * (i + 1)));
  }
  return null;
}

const ord = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
const pct = (p: number) => `${Math.round(p * 100)}%`;

export function Form({ form }: { form: string[] }) {
  return (
    <span className="pv-form">
      {form.map((f, i) => (
        <i key={i} className={`f${f}`}>
          {f}
        </i>
      ))}
    </span>
  );
}

export function ForecastBar({ p, home, away, label }: { p: [number, number, number]; home: LeagueClub; away: LeagueClub; label?: boolean }) {
  return (
    <div className="pv-bar3">
      {([[home.short, p[0], home.primary], ["Draw", p[1], undefined], [away.short, p[2], away.primary]] as const).map(([name, v, bg]) => (
        <div key={name} className={bg ? "" : "draw"} style={{ flex: v, background: bg }} title={`${name} ${pct(v)}`}>
          {label !== false && v >= 0.12 && `${name} ${pct(v)}`}
        </div>
      ))}
    </div>
  );
}

function Side({ c, side, pos, pts, form }: { c: LeagueClub; side: "home" | "away"; pos: number; pts: number; form: string[] }) {
  return (
    <div className={`pv-side ${side}`} style={{ "--c": c.primary } as CSSProperties}>
      <Crest club={c} size={96} />
      <div>
        <span className="label">
          {side === "home" ? t("Home") : t("Away")} &middot; {ord(pos)} &middot; {pts} pts
        </span>
        <h2>{c.name}</h2>
        <div className="sub">
          {c.nickname} &middot; {c.style} &middot; {c.formation}
        </div>
        <Form form={form} />
      </div>
    </div>
  );
}

/** The Preview agent's page before kickoff: the matchup, the forecast, the story, head to head and players to watch. */
export function Preview({ room, lang }: { room: string; lang: Lang }) {
  const [pv, setPv] = useState<PreviewData | null>(null);
  const clubs = useClubs();
  useEffect(() => {
    let alive = true;
    setPv(null);
    getJson<PreviewData>(`/api/rooms/${room}/preview?lang=${lang}`).then((d) => alive && d && setPv(d));
    return () => {
      alive = false;
    };
  }, [room, lang]);
  if (!pv || !clubs) return <div className="empty" style={{ padding: 24 }}>{t("The Preview agent is writing.")}</div>;
  const h = clubs[pv.home];
  const a = clubs[pv.away];
  const text = (lang !== "en" && pv.langs?.[lang]) || { headline: pv.headline, story: pv.story };

  return (
    <div className="pv">
      <section className="pv-head">
        <Side c={h} side="home" pos={pv.table.home.position} pts={pv.table.home.points} form={pv.form.home} />
        <div className="pv-vs">
          <b>V</b>
          <span className="label">{t("Matchday")} {pv.facts.matchday}</span>
          <span className="label">{pv.facts.ground}</span>
        </div>
        <Side c={a} side="away" pos={pv.table.away.position} pts={pv.table.away.points} form={pv.form.away} />
      </section>

      <section className="pv-forecast">
        <span className="label">Pre-match forecast &middot; from the fitted team ratings</span>
        <ForecastBar p={pv.forecast} home={h} away={a} />
      </section>

      <div className="pv-grid">
        <section className="pv-story">
          <span className="label">{t("The story")}</span>
          <h3 lang={lang}>{text.headline}</h3>
          <p lang={lang}>{text.story}</p>
          <div className="pv-by">
            {pv.source === "agent" && <span className="verified">{t("Verified")}</span>}
            <span className="label">{pv.source === "agent" ? "Preview agent" : "Template preview, filled from the season data"}</span>
          </div>
        </section>
        <section className="pv-panel">
          <h4>{t("Head to head")}</h4>
          <div className="pv-h2h">
            {pv.h2h.slice(0, 5).map((m, i) => {
              const winner = m.score[0] > m.score[1] ? m.home : m.score[1] > m.score[0] ? m.away : null;
              return (
                <div key={i}>
                  <span className="label">{m.season === "last" ? "Last season" : "This season"} &middot; MD{m.matchday}</span>
                  <span className={winner === m.home ? "w" : ""}>{clubs[m.home].short}</span>
                  <b className="num">
                    {m.score[0]}&ndash;{m.score[1]}
                  </b>
                  <span className={winner === m.away ? "w" : ""}>{clubs[m.away].short}</span>
                </div>
              );
            })}
            {pv.h2h.length === 0 && <div className="empty">{t("First meeting.")}</div>}
          </div>
        </section>
        <section className="pv-panel">
          <h4>{t("Players to watch")}</h4>
          <div className="pv-watch">
            {pv.watch.map((p) => {
              const c = p.side === "home" ? h : a;
              return (
                <div key={p.player_id}>
                  <svg width="44" height="44" viewBox="0 0 44 44" aria-hidden>
                    <circle cx="22" cy="22" r="20.5" fill={c.primary} stroke={c.secondary} strokeWidth="2.5" />
                    <text x="22" y="29" textAnchor="middle" fontFamily="Barlow Condensed" fontWeight={800} fontSize={20} fill={c.secondary}>
                      {p.number}
                    </text>
                  </svg>
                  <div>
                    <b>{p.name}</b>
                    <span>{p.label}</span>
                  </div>
                  <em className="num">{p.value}</em>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
