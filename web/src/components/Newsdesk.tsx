import { useEffect, useState, type CSSProperties } from "react";
import type { Lang } from "../prefs";
import { Crest } from "./Crest";
import { getJson, useClubs } from "./Preview";

interface Article {
  scenario: string;
  title: string;
  home: string;
  away: string;
  ground: string;
  score: [number, number];
  headline: string;
  standfirst: string;
  body: string[];
  pull: string;
  source: "agent" | "template";
  langs: Record<string, { headline: string; standfirst: string; body: string[]; pull: string }>;
  stats: {
    xg: [number, number];
    shots: [number, number];
    possession: [number, number];
    top_player: string | null;
    top_player_leverage: string | null;
    spell: { team: "home" | "away"; start: number; end: number; share: number } | null;
  };
  goals: { minute: number; team: "home" | "away"; player: string; xg: number }[];
}
interface News {
  matchday: number;
  writing: boolean;
  articles: Article[];
}

const POLL_MS = 8000;

/** The Newsdesk: a match report for every fixture of the matchday, by the Newsdesk agent. */
export function Newsdesk({ lang }: { lang: Lang }) {
  const [news, setNews] = useState<News | null>(null);
  const [pick, setPick] = useState<string | null>(null);
  const clubs = useClubs();

  useEffect(() => {
    let alive = true;
    let timer = 0;
    const load = async () => {
      const n = await getJson<News>("/api/newsdesk");
      if (!alive || !n) return;
      setNews(n);
      if (n.writing) timer = window.setTimeout(load, POLL_MS); // the agent's reports replace templates as they pass
    };
    load();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, []);

  if (!news || !clubs) return <div className="empty" style={{ padding: 24 }}>The Newsdesk is filing.</div>;
  const a = news.articles.find((x) => x.scenario === pick) ?? news.articles[0];
  const t = (lang !== "en" && a.langs?.[lang]) || a;
  const h = clubs[a.home];
  const w = clubs[a.away];
  const won = a.score[0] === a.score[1] ? null : a.score[0] > a.score[1] ? "home" : "away";
  const spellClub = a.stats.spell ? (a.stats.spell.team === "home" ? h : w) : null;

  return (
    <div className="nd">
      <section className="nd-head">
        <span className="label">The Meridian League &middot; Newsdesk</span>
        <h1>Matchday {news.matchday}</h1>
        {news.writing && <span className="label nd-writing">The Newsdesk agent is writing the reports</span>}
      </section>
      <div className="nd-grid">
        <article className="nd-article" style={{ "--h": h.primary, "--a": w.primary } as CSSProperties}>
          <div className="nd-hero">
            <div className="nd-kicker">
              <em>Full time</em>
              <span className="label">
                {a.title} &middot; {a.ground}
              </span>
            </div>
            <h2 lang={lang}>{t.headline}</h2>
            <div className="nd-score">
              <Crest club={h} size={52} />
              <span className={won === "away" ? "lost" : ""}>{h.name}</span>
              <b className="num">
                {a.score[0]}
                <i>&ndash;</i>
                {a.score[1]}
              </b>
              <span className={won === "home" ? "lost" : ""}>{w.name}</span>
              <Crest club={w} size={52} />
            </div>
          </div>
          <p className="nd-stand" lang={lang}>{t.standfirst}</p>
          <div className="nd-by">
            {a.source === "agent" ? <span className="verified">Every figure checked</span> : <span className="label">Template report</span>}
            <span className="label">{a.source === "agent" ? "By the Newsdesk agent" : "Filled from the match engine"}</span>
          </div>
          <div className="nd-strip">
            <div>
              <b className="num">
                {a.stats.xg[0].toFixed(2)}
                <small> / {a.stats.xg[1].toFixed(2)}</small>
              </b>
              <span>xG</span>
            </div>
            <div>
              <b className="num">
                {Math.round(a.stats.possession[0] * 100)}
                <small>%</small>
              </b>
              <span>{h.short} possession</span>
            </div>
            <div>
              <b className="num">
                {a.stats.shots[0]}
                <small> / {a.stats.shots[1]}</small>
              </b>
              <span>Shots</span>
            </div>
            <div>
              <b className="num">{a.stats.top_player_leverage ?? "-"}</b>
              <span>{a.stats.top_player ?? "Top player"} leverage</span>
            </div>
            <div>
              <b className="num">{a.stats.spell ? `${Math.round(a.stats.spell.share * 100)}%` : "-"}</b>
              <span>{a.stats.spell && spellClub ? `${spellClub.short} threat, ${a.stats.spell.start}' to ${a.stats.spell.end}'` : "No dominant spell"}</span>
            </div>
          </div>
          <div className="nd-body" lang={lang}>
            {t.body.map((p, i) => (
              <div key={i}>
                <p>{p}</p>
                {i === 0 && (
                  <blockquote className="nd-pull">
                    {t.pull}
                    <small>From the match data</small>
                  </blockquote>
                )}
              </div>
            ))}
          </div>
          {a.goals.length > 0 && (
            <div className="nd-goals">
              {a.goals.map((g, i) => (
                <span key={i} style={{ borderColor: (g.team === "home" ? h : w).primary }}>
                  <b className="num">{g.minute}'</b> {g.player} <i className="num">{g.xg.toFixed(2)} xG</i>
                </span>
              ))}
            </div>
          )}
        </article>
        <aside className="nd-side">
          <h3>Matchday {news.matchday}</h3>
          {news.articles.map((x) => {
            const xh = clubs[x.home];
            const xa = clubs[x.away];
            const xt = (lang !== "en" && x.langs?.[lang]) || x;
            const lost = x.score[0] === x.score[1] ? null : x.score[0] > x.score[1] ? "away" : "home";
            return (
              <button key={x.scenario} className={`nd-fx ${x.scenario === a.scenario ? "on" : ""}`} onClick={() => setPick(x.scenario)}>
                <div className="teams">
                  <div className={lost === "home" ? "lose" : ""}>
                    <Crest club={xh} size={20} />
                    {xh.name}
                  </div>
                  <div className={lost === "away" ? "lose" : ""}>
                    <Crest club={xa} size={20} />
                    {xa.name}
                  </div>
                </div>
                <div className="goals num">
                  <span>{x.score[0]}</span>
                  <span>{x.score[1]}</span>
                </div>
                <p lang={lang}>{xt.standfirst}</p>
              </button>
            );
          })}
        </aside>
      </div>
    </div>
  );
}
