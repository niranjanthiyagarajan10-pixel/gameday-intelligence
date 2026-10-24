import { useEffect, useState } from "react";
import { Crest } from "./Crest";
import { ForecastBar, getJson, useClubs } from "./Preview";
import type { Lang } from "../prefs";

interface Decided {
  moment_id: string;
  minute: number;
  kind: string;
  team: "home" | "away" | null;
  swing: number | null;
  leverage: number;
  text: string;
  langs: Record<string, string>;
}
interface Next {
  club: string;
  opponent: string;
  at_home: boolean;
  matchday: number;
  forecast: [number, number, number];
}
interface PostgameData {
  home: string;
  away: string;
  status: string;
  decided: Decided[];
  next: Next[];
  look_ahead: string[];
  source: "agent" | "template";
  langs: Record<string, { look_ahead: string[] }>;
}

const KIND: Record<string, string> = {
  goal: "Goal", low_xg_goal: "Goal", red_card: "Red card", leverage_swing: "Big play", big_chance: "Big chance",
};
const REFRESH_MS = 30000;

/** After the match: what decided it (code, from the verified key moments) and what comes next (Post-game agent). */
export function AfterMatch({ room, lang }: { room: string; lang: Lang }) {
  const [pg, setPg] = useState<PostgameData | null>(null);
  const clubs = useClubs();
  useEffect(() => {
    let alive = true;
    const load = () => getJson<PostgameData>(`/api/rooms/${room}/postgame`).then((d) => alive && d && setPg(d));
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [room]);
  if (!pg || !clubs) return null;
  const lines = (lang !== "en" && pg.langs?.[lang]?.look_ahead) || pg.look_ahead;
  const sideClub = (side: "home" | "away" | null) => clubs[side === "away" ? pg.away : pg.home];

  return (
    <div className="am">
      <section className="bp-section">
        <h3 className="bp-h">{pg.status === "full_time" ? "What decided it" : "What is deciding it"}</h3>
        <div className="am-decided">
          {pg.decided.map((d) => {
            const c = sideClub(d.team);
            const value = d.swing !== null ? `${d.swing > 0 ? "+" : ""}${d.swing}` : `${d.leverage > 0 ? "+" : ""}${d.leverage.toFixed(2)}`;
            return (
              <div key={d.moment_id} style={{ borderLeftColor: c.primary }}>
                <b className={`num ${d.swing !== null && d.swing < 0 ? "down" : "up"}`}>{value}</b>
                <div>
                  <span className="label">
                    {d.minute}' &middot; {KIND[d.kind] ?? d.kind} &middot; {d.swing !== null ? "win chance points" : "leverage"}
                  </span>
                  <p lang={lang}>{(lang !== "en" && d.langs?.[lang]) || d.text}</p>
                </div>
              </div>
            );
          })}
          {pg.decided.length === 0 && <div className="empty">No decisive moment yet.</div>}
        </div>
        <span className="bp-fine">Ranked by how much each moment moved the win probability. Each line is the Narrator's, already verified.</span>
      </section>
      <section className="bp-section">
        <h3 className="bp-h">Next up</h3>
        <div className="am-next">
          {pg.next.map((n) => {
            const club = clubs[n.club];
            const opp = clubs[n.opponent];
            const [home, away] = n.at_home ? [club, opp] : [opp, club];
            return (
              <div key={n.club}>
                <div className="am-fx">
                  <span>
                    <Crest club={home} size={30} />
                    {home.name}
                  </span>
                  <span className="label">Matchday {n.matchday}</span>
                  <span className="r">
                    {away.name}
                    <Crest club={away} size={30} />
                  </span>
                </div>
                <ForecastBar p={n.forecast} home={home} away={away} />
              </div>
            );
          })}
        </div>
        <div className="am-look">
          <span className="label">What to watch next time</span>
          {lines.map((l, i) => (
            <p key={i} lang={lang}>
              {l}
            </p>
          ))}
          <div className="pv-by">
            {pg.source === "agent" && <span className="verified">Verified</span>}
            <span className="label">{pg.source === "agent" ? "Post-game agent" : "Template, filled from the match and season data"}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
