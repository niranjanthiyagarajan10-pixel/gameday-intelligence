import { useEffect, useState } from "react";
import type { PlayerSummary, Roster } from "../types";
import { ShotMap } from "./ShotMap";
import { signed } from "../format";
import { shotHref } from "../route";

interface Props {
  room: string;
  id: string;
  roster: Roster;
}

const POSITION: Record<string, string> = { GK: "Goalkeeper", DF: "Defender", MF: "Midfielder", FW: "Forward" };

/** A player's game averages and every shot, like the NBA player shot page. Refreshes while the match is live. */
export function PlayerPage({ room, id, roster }: Props) {
  const [summary, setSummary] = useState<PlayerSummary | null>(null);
  const info = roster.players[id];

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const r = await fetch(`/api/rooms/${room}/players/${encodeURIComponent(id)}`);
      if (alive && r.ok) setSummary((await r.json()).summary as PlayerSummary);
    };
    load();
    const timer = window.setInterval(load, 3000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [room, id]);

  if (!info) return <div className="empty" style={{ padding: 24 }}>That player is not in this match.</div>;
  const club = roster.clubs[info.side];
  const s = summary;
  const fmt = (v: number | null | undefined, digits = 2) => (v === null || v === undefined ? "-" : v.toFixed(digits));

  const kpis: [string, string, string][] = s
    ? [
        [`${s.goals}`, "", `Goals from ${s.shots} shots`],
        [signed(s.goals_minus_xg), "", "Goals above expected"],
        [fmt(s.made_xg), "xG", "Average xG of goals"],
        [fmt(s.missed_xg), "xG", "Average xG of misses"],
        [fmt(s.avg_defender_m, 1), "m", "Avg nearest defender at shot"],
      ]
    : [];
  const physical: [string, string, string][] = s
    ? [
        [s.distance_km.toFixed(1), "km", "Distance"],
        [s.top_speed_kmh.toFixed(1), "km/h", "Top speed"],
        [`${s.sprints}`, "", "Sprints"],
        [signed(s.leverage), "", "Leverage"],
        [s.press_rate !== null ? `${Math.round(s.press_rate * 100)}` : "-", s.press_rate !== null ? "%" : "", `Press resistance (${s.press_attempts})`],
      ]
    : [];

  return (
    <div className="grid">
      <div className="c12 pagehead">
        <a href="#/" className="back">
          &larr; Back to the match
        </a>
        <div className="playerhead">
          <span className="badge" style={{ background: club.primary }}>
            {info.number}
          </span>
          <div>
            <h1>{info.name}</h1>
            <div className="sub">
              {club.name}. {POSITION[info.position]}. Game averages, live.
            </div>
          </div>
        </div>
      </div>

      {s && (
        <>
          <div className="c12 kpis">
            {kpis.map(([v, unit, label]) => (
              <div key={label} className="kpi">
                <b className="num">
                  {v}
                  {unit && <small>{unit}</small>}
                </b>
                <span>{label}</span>
              </div>
            ))}
          </div>
          <div className="c12 kpis small">
            {physical.map(([v, unit, label]) => (
              <div key={label} className="kpi">
                <b className="num">
                  {v}
                  {unit && <small>{unit}</small>}
                </b>
                <span>{label}</span>
              </div>
            ))}
          </div>

          <div className="panel c8">
            <div className="ph">
              <h3>Every shot</h3>
              <span className="label">Click a shot to watch its replay</span>
            </div>
            <div className="pb">
              {s.list.length === 0 ? (
                <div className="empty">No shots yet.</div>
              ) : (
                <table className="lv shots">
                  <thead>
                    <tr>
                      <th>Shot type</th>
                      <th>Body</th>
                      <th>Result</th>
                      <th>Minute</th>
                      <th>Distance</th>
                      <th>xG</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.list.map((shot) => (
                      <tr key={shot.event_id} onClick={() => (location.hash = shotHref(shot.event_id))}>
                        <td>
                          <span className="play">&#9654;</span> {shot.shot_type}
                        </td>
                        <td>{shot.body_part === "head" ? "Head" : "Foot"}</td>
                        <td>{shot.outcome === "goal" ? <i className="ring" /> : <i className="cross">x</i>}</td>
                        <td>{shot.minute}'</td>
                        <td>{shot.distance_m.toFixed(1)} m</td>
                        <td>{shot.xg.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
          <div className="panel c4">
            <div className="ph">
              <h3>Shot map</h3>
            </div>
            <div className="pb">
              <ShotMap shots={s.list} roster={roster} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
