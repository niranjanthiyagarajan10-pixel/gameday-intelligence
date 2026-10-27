import { useEffect, useState } from "react";
import type { Roster } from "../types";
import type { Lang } from "../prefs";
import { Crest } from "./Crest";
import { getJson } from "./Preview";
import { t } from "../i18n";

interface Brief {
  bullets: string[];
  source: "agent" | "template";
  langs: Record<string, { bullets: string[] }>;
  stats: { xg: [number, number]; possession: [number, number]; win_prob: [number, number, number]; men: [number, number] };
  score: [number, number];
  minute: number;
  status: string;
}

const pct = (p: number) => `${Math.round(p * 100)}%`;

/** Catch me up: one tap, three points from the Summarizer agent, for a fan who just joined. */
export function CatchMeUp({ room, roster, lang }: { room: string; roster: Roster; lang: Lang }) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const h = roster.clubs.home;
  const a = roster.clubs.away;

  const load = async () => {
    setOpen(true);
    setLoading(true);
    const b = await getJson<Brief>(`/api/rooms/${room}/brief?lang=${lang}`);
    if (b) setBrief(b);
    setLoading(false);
  };

  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => {
    if (open) void load(); // a new language: fetch the points written in it
  }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) {
    return (
      <button className="cmu-open" onClick={load}>
        <b>{t("Catch me up")}</b>
        <span>{t("Three points, twenty seconds")}</span>
      </button>
    );
  }
  if (!brief) return <div className="panel cmu"><div className="empty" style={{ padding: 16 }}>{t("The Summarizer is reading the match.")}</div></div>;
  const bullets = (lang !== "en" && brief.langs?.[lang]?.bullets) || brief.bullets;
  const [ph, pd, pa] = brief.stats.win_prob;
  const lead = ph >= pa ? { c: h, p: ph } : { c: a, p: pa };
  const men = brief.stats.men;

  return (
    <div className="panel cmu">
      <div className="cmu-top">
        <Crest club={h} size={40} />
        <div className="nm">{h.name}</div>
        <div className="sc num">
          {brief.score[0]}
          <i>:</i>
          {brief.score[1]}
        </div>
        <div className="nm r">{a.name}</div>
        <Crest club={a} size={40} />
        <div className="clock label">{brief.status === "full_time" ? "Full time" : `${brief.minute}'`}</div>
      </div>
      <div className="cmu-kpis">
        <div>
          <b className="num" style={{ color: lead.c.primary }}>{pct(lead.p)}</b>
          <span>{lead.c.short} win chance</span>
          <div className="cmu-bar">
            <i style={{ flex: ph, background: h.primary }} />
            <i style={{ flex: pd, background: "var(--line-dash)" }} />
            <i style={{ flex: pa, background: a.primary }} />
          </div>
        </div>
        <div>
          <b className="num">
            {brief.stats.xg[0].toFixed(2)}
            <small> / {brief.stats.xg[1].toFixed(2)}</small>
          </b>
          <span>{t("xG")}</span>
        </div>
        <div>
          <b className="num">{pct(brief.stats.possession[0])}</b>
          <span>{h.short} possession</span>
        </div>
        <div>
          <b className="num">
            {men[0]}
            <small> v {men[1]}</small>
          </b>
          <span>{t("On the pitch")}</span>
        </div>
      </div>
      <ol className="cmu-points">
        {bullets.map((b, i) => (
          <li key={i} lang={lang}>
            <b>{i + 1}</b>
            <span>{b}</span>
          </li>
        ))}
      </ol>
      <div className="cmu-foot">
        {brief.source === "agent" ? <span className="verified">{t("Verified")}</span> : <span className="label">{t("Template")}</span>}
        <span className="label">{brief.source === "agent" ? "Summarizer agent" : "Filled from the match engine"}</span>
        <button onClick={load} disabled={loading}>{loading ? t("Updating") : t("Update")}</button>
        <button onClick={() => setOpen(false)}>{t("Close")}</button>
      </div>
    </div>
  );
}
