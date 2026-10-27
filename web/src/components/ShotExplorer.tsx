import { useEffect, useId, useMemo, useState } from "react";
import type { BlueprintShot, Roster, Side } from "../types";
import { Crest } from "./Crest";
import { KitAvatar } from "./Kit";
import { clock } from "../format";
import { shotHref } from "../route";
import { t, labels } from "../i18n";

const HARD_XG = 0.05;
const EASY_XG = 0.2;
const LEAGUE_XG = 0.12; // simulated league average per shot, docs/realism.md
const COLORS = { hard: "#FF4D4D", average: "#4DA3FF", easy: "#38E07B" } as const;
const LINE = { fill: "none", stroke: "rgba(255,255,255,.3)", strokeWidth: 0.3 } as const;
const PEN_ARC_DX = Math.sqrt(9.15 ** 2 - 5.5 ** 2);
const RESULT: Record<string, string> = labels({ goal: "Goal", saved: "Saved", off_target: "Wide", blocked: "Blocked" });

type Band = keyof typeof COLORS;
const band = (xg: number): Band => (xg < HARD_XG ? "hard" : xg >= EASY_XG ? "easy" : "average");

/** Attacking coordinates of a shot (the team attacks towards x = 105). */
const attacking = (s: BlueprintShot): [number, number] => (s.team === "home" ? [s.x, s.y] : [105 - s.x, 68 - s.y]);

/** Pitch point to the vertical half pitch, goal at the top: x across, y down from the goal line. */
const toHalf = (ax: number, ay: number): [number, number] => [ay, Math.min(105 - ax, 52.5)];

function Marker({ kind, x, y, goal, size = 1.25 }: { kind: Band; x: number; y: number; goal: boolean; size?: number }) {
  const fill = goal ? COLORS[kind] : "#0b0c0e";
  const common = { fill, stroke: COLORS[kind], strokeWidth: 0.35 };
  if (kind === "hard") {
    return <polygon points={`${x},${y - size * 1.1} ${x + size},${y + size * 0.75} ${x - size},${y + size * 0.75}`} {...common} />;
  }
  if (kind === "easy") return <rect x={x - size * 0.85} y={y - size * 0.85} width={size * 1.7} height={size * 1.7} {...common} />;
  return <circle cx={x} cy={y} r={size * 0.9} {...common} />;
}

/** The attacking half, standing up like the NBA half court, goal at the top. */
function HalfPitch({ children }: { children: React.ReactNode }) {
  const net = `hn${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="-3 -4 74 59" className="halfpitch" role="img" aria-label={t("Shots on the attacking half")}>
      <defs>
        <pattern id={net} width={0.7} height={0.7} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <path d="M0 0V0.7M0 0H0.7" stroke="rgba(255,255,255,.4)" strokeWidth={0.07} fill="none" />
        </pattern>
      </defs>
      <rect x={-3} y={-4} width={74} height={59} fill="var(--pitch)" />
      {[0, 1, 2].map((k) => (
        <rect key={k} x={-3} y={k * 21} width={74} height={10.5} fill="#fff" opacity={0.03} />
      ))}
      <rect x={0} y={0} width={68} height={52.5} {...LINE} />
      <path d={`M24.85,52.5A9.15 9.15 0 0 1 43.15,52.5`} {...LINE} />
      <circle cx={34} cy={52.5} r={0.4} fill="rgba(255,255,255,.4)" />
      <rect x={13.84} y={0} width={40.32} height={16.5} {...LINE} />
      <rect x={24.84} y={0} width={18.32} height={5.5} {...LINE} />
      <path d={`M${34 - PEN_ARC_DX},16.5A9.15 9.15 0 0 0 ${34 + PEN_ARC_DX},16.5`} {...LINE} />
      <circle cx={34} cy={11} r={0.35} fill="rgba(255,255,255,.4)" />
      <path d="M1,0A1 1 0 0 1 0,1M67,0A1 1 0 0 0 68,1" {...LINE} />
      <rect x={30.34} y={-2} width={7.32} height={2} fill={`url(#${net})`} stroke="rgba(255,255,255,.55)" strokeWidth={0.12} />
      <line x1={30.34} y1={0} x2={37.66} y2={0} stroke="#F4F4F1" strokeWidth={0.45} />
      {children}
    </svg>
  );
}

interface Props {
  shots: BlueprintShot[];
  roster: Roster;
  finishing: Partial<Record<Side, string>>;
  halfS: number;
}

/** Every shot on the attacking half by difficulty; pick one to see who took it, who was closest and how hard it was. */
export function ShotExplorer({ shots, roster, finishing, halfS }: Props) {
  const [side, setSide] = useState<Side>("home");
  const [half, setHalf] = useState<0 | 1 | 2>(0);
  const [picked, setPicked] = useState<string | null>(null);
  const shown = useMemo(() => shots.filter((s) => s.team === side && (half === 0 || s.half === half)), [shots, side, half]);
  const shot = shown.find((s) => s.event_id === picked) ?? shown[0] ?? null;

  useEffect(() => setPicked(null), [side, half]);

  const club = roster.clubs[side];
  const shooter = shot ? roster.players[shot.player] : undefined;
  const defender = shot?.defender ? roster.players[shot.defender] : undefined;
  const [home, away] = shot ? shot.score_after.split("-") : ["0", "0"];
  const period = shot ? (shot.t < halfS ? "1H" : "2H") : "";

  return (
    <section className="bp-section">
      <h3 className="bp-h">{t("Shot difficulty")}</h3>
      <div className="bp-two">
        <div>
          <div className="bp-seg">
            {(["home", "away"] as Side[]).map((s) => (
              <button key={s} className={side === s ? "on" : ""} onClick={() => setSide(s)}>
                {roster.clubs[s].name}
              </button>
            ))}
          </div>
          <div className="bp-field">
            <HalfPitch>
              {shown.map((s) => {
                const [x, y] = toHalf(...attacking(s));
                const on = shot?.event_id === s.event_id;
                return (
                  <g key={s.event_id} className="bp-shot" onClick={() => setPicked(s.event_id)} role="button"
                    aria-label={`${roster.players[s.player]?.name}, ${s.xg.toFixed(2)} xG, ${RESULT[s.outcome] ?? s.outcome}`}>
                    {on && <circle cx={x} cy={y} r={2.6} fill="none" stroke="#F4F4F1" strokeWidth={0.4} />}
                    <Marker kind={band(s.xg)} x={x} y={y} goal={s.outcome === "goal"} />
                    <circle cx={x} cy={y} r={2.4} fill="transparent" />
                  </g>
                );
              })}
            </HalfPitch>
          </div>
          <div className="bp-legend">
            <span><svg width={12} height={12} viewBox="-1.5 -1.5 3 3"><Marker kind="hard" x={0} y={0} goal size={1.2} /></svg><b>{t("Hard")}</b> {t("under")} {HARD_XG.toFixed(2)} xG</span>
            <span><svg width={12} height={12} viewBox="-1.5 -1.5 3 3"><Marker kind="average" x={0} y={0} goal size={1.2} /></svg><b>{t("Average")}</b></span>
            <span><svg width={12} height={12} viewBox="-1.5 -1.5 3 3"><Marker kind="easy" x={0} y={0} goal size={1.2} /></svg><b>{t("Easy")}</b> {EASY_XG.toFixed(2)} xG and up</span>
            <span className="muted">{t("Filled: goal. Hollow: no goal.")}</span>
          </div>
          <div className="bp-count">
            All shots: <b className="num">{shown.length} attempts</b>
          </div>
          <div className="bp-pills">
            {(["All", "1st half", "2nd half"] as const).map((label, i) => (
              <button key={label} className={half === i ? "on" : ""} onClick={() => setHalf(i as 0 | 1 | 2)}>
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="bp-card">
          {!shot || !shooter ? (
            <div className="empty">{t("No shots for")} {club.name} in this period yet.</div>
          ) : (
            <>
              <div className="bp-card-top">
                <Crest club={club} size={34} />
                <div>
                  <b className="num">
                    {period} {clock(shot.t)}
                  </b>
                  <span>{shot.shot_type}</span>
                </div>
                <div className="bp-scorepill num">
                  <span className={side === "home" ? "on" : ""}>
                    {roster.clubs.home.short} <b>{home}</b>
                  </span>
                  <span className={side === "away" ? "on" : ""}>
                    <b>{away}</b> {roster.clubs.away.short}
                  </span>
                </div>
              </div>
              <div className="bp-duel">
                <div>
                  <KitAvatar club={club} info={shooter} size={56} />
                  <div>
                    <span className="muted">{t("Shooter")}</span>
                    <b>{shooter.name}</b>
                    <span className="muted">{club.short}</span>
                  </div>
                </div>
                <div className="r">
                  <div>
                    <span className="muted">{t("Nearest defender")}</span>
                    <b>{defender ? defender.name : "None close"}</b>
                    <span className="muted">{defender ? roster.clubs[defender.side].short : ""}</span>
                  </div>
                  {defender && <KitAvatar club={roster.clubs[defender.side]} info={defender} size={56} />}
                </div>
              </div>
              <div className="bp-xg">
                <span className="lbl">{t("xG")}</span>
                <b className="num">{shot.xg.toFixed(2)}</b>
                <span className="muted">{Math.round(shot.xg * 100)}% chance of a goal</span>
              </div>
              <div className="bp-bar-avg" style={{ paddingLeft: `${LEAGUE_XG * 100}%` }}>
                {t("League avg")} {LEAGUE_XG.toFixed(2)}
              </div>
              <div className="bp-bar">
                <i style={{ width: `${Math.min(shot.xg, 1) * 100}%` }} />
                <em style={{ left: `${LEAGUE_XG * 100}%` }} />
              </div>
              <div className="bp-bar-labels">
                <span>{t("Hard 0")}</span>
                <span>{t("Easy 1")}</span>
              </div>
              <div className="bp-tiles">
                <div><b className="num">{shot.defender_m !== null ? shot.defender_m.toFixed(1) : "-"}<small>M</small></b><span>{t("Defender distance")}</span></div>
                <div><b className="num">{Math.round(shot.pressure * 100)}<small>%</small></b><span>{t("Pressure")}</span></div>
                <div><b className="num">{shot.speed_kmh !== null ? shot.speed_kmh.toFixed(0) : "-"}<small>{t("KM/H")}</small></b><span>{t("Shot speed")}</span></div>
                <div><b className="num">{shot.distance_m.toFixed(1)}<small>M</small></b><span>{t("Shot distance")}</span></div>
                <div><b className="num">{shot.angle_deg.toFixed(0)}<small>{t("DEG")}</small></b><span>{t("Goal angle")}</span></div>
                <div><b className={shot.outcome === "goal" ? "made" : "missed"}>{RESULT[shot.outcome] ?? shot.outcome}</b><span>{t("Result")}</span></div>
              </div>
              <a className="actlink" href={shotHref(shot.event_id)}>
                Watch the replay &rarr;
              </a>
            </>
          )}
        </div>
      </div>
      {finishing[side] && <p className="bp-note">{finishing[side]}</p>}
    </section>
  );
}
