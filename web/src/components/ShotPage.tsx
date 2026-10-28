import { useEffect, useState } from "react";
import type { PlayerSummary, Roster, ShotPageData } from "../types";
import { Replay } from "./Replay";
import { ShotMap } from "./ShotMap";
import { pct, playerName, signed } from "../format";
import { playerHref } from "../route";
import { t, labels } from "../i18n";

interface Props {
  room: string;
  id: string;
  roster: Roster;
}

const OUTCOME: Record<string, string> = labels({
  goal: "Goal",
  saved: "Saved",
  off_target: "Off target",
  blocked: "Blocked",
});

/** One shot: a replay, its difficulty and the details. */
export function ShotPage({ room, id, roster }: Props) {
  const [data, setData] = useState<ShotPageData | null>(null);
  const [player, setPlayer] = useState<PlayerSummary | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const load = async () => {
      const r = await fetch(`/api/rooms/${room}/shots/${encodeURIComponent(id)}`);
      if (!alive) return;
      if (r.status === 404) return setMissing(true);
      const body = (await r.json()) as ShotPageData;
      setData(body);
      const done = body.clip && body.clip.frames[body.clip.frames.length - 1]?.t >= body.shot.t + 2.9;
      if (!done) timer = window.setTimeout(load, 1000); // the clip is still recording its last seconds
      const p = await fetch(`/api/rooms/${room}/players/${encodeURIComponent(body.shot.player)}`);
      if (alive && p.ok) setPlayer((await p.json()).summary as PlayerSummary);
    };
    load();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [room, id]);

  if (missing) return <div className="empty" style={{ padding: 24 }}>{t("That shot is not in this match.")}</div>;
  if (!data) return <div className="empty" style={{ padding: 24 }}>{t("Loading the replay.")}</div>;

  const s = data.shot;
  const club = roster.clubs[s.team];
  const opp = roster.clubs[s.team === "home" ? "away" : "home"];
  const details: [string, string][] = [
    ["Result", OUTCOME[s.outcome] ?? s.outcome],
    ["Minute", `${s.minute}'`],
    ["Score before", `${roster.clubs.home.short} ${s.score_before} ${roster.clubs.away.short}`],
    ["Distance to goal", `${s.distance_m.toFixed(1)} m`],
    ["Angle of goal mouth", `${s.angle_deg.toFixed(0)} deg`],
    ["Nearest defender", s.defender_m !== null ? `${s.defender_m.toFixed(1)} m` : "-"],
    ["Pressure", `${Math.round(s.pressure * 100)}%`],
    ["Shot speed", s.speed_kmh ? `${Math.round(s.speed_kmh)} km/h` : "-"],
    ["Body part", s.body_part === "head" ? t("Head") : t("Foot")],
    ["Created by", s.creator ? playerName(roster, s.creator) : "Self-created"],
    [t("{club} win chance if it goes in", { club: club.short }), `${pct(s.wp_if_goal)}%`],
    [t("{club} win chance if it does not", { club: club.short }), `${pct(s.wp_if_miss)}%`],
    ["Leverage", signed(s.leverage)],
  ];

  return (
    <div className="grid">
      <div className="c12 pagehead">
        <a href="#/" className="back">
          &larr; Back to the match
        </a>
        <h1>
          {roster.clubs.home.short} v {roster.clubs.away.short} <span>{s.minute}'</span>
        </h1>
      </div>

      <div className="c8 col">
        <div className="panel">
          <div className="pb">
            {data.clip ? <Replay clip={data.clip} shot={s} roster={roster} /> : <div className="empty">{t("Recording the replay.")}</div>}
          </div>
        </div>
        <div className="shot-title">
          <div>
            <h2>
              <a href={playerHref(s.player)}>{playerName(roster, s.player)}</a> {s.shot_type}
            </h2>
            <div className="sub">
              {club.name} against {opp.name}. {OUTCOME[s.outcome] ?? s.outcome}.
            </div>
          </div>
          <div className="xgcard">
            <b className="num">{s.xg.toFixed(2)}</b>
            <span>{t("Shot difficulty (xG)")}</span>
          </div>
        </div>
        <div className="panel">
          <div className="ph">
            <h3>{t("Shot details")}</h3>
            <span className="label">{t("All measured from tracking and events")}</span>
          </div>
          <div className="pb details">
            {details.map(([k, v]) => (
              <div key={k}>
                <span className="label">{t(k)}</span>
                <b className="num">{v}</b>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="c4 col">
        <div className="panel">
          <div className="ph">
            <h3>{t("Shots by")} {playerName(roster, s.player, true)}</h3>
          </div>
          <div className="pb">
            {player ? (
              <>
                <ShotMap shots={player.list} roster={roster} selected={s.event_id} />
                <div className="maplegend">
                  <span>
                    {player.goals} of {player.shots} scored. xG {player.xg.toFixed(2)}
                  </span>
                  <span>
                    <i className="ring" /> {t("Goal")} <i className="cross">x</i> {t("Miss")}
                  </span>
                </div>
                <a className="more" href={playerHref(s.player)}>
                  All shots and game averages &rarr;
                </a>
              </>
            ) : (
              <div className="empty">{t("Loading.")}</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
