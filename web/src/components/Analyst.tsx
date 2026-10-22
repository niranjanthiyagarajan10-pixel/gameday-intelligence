import { useState } from "react";
import type { Analyst as AnalystData, LeverageRow, Roster, Shot, Side } from "../types";
import { SHAPE_LABEL, clock, playerName, signed } from "../format";
import { playerHref, shotHref } from "../route";

interface Props {
  analyst: AnalystData;
  roster: Roster;
  halfS: number;
  now: number;
}

const SIDES: Side[] = ["home", "away"];

const OUTCOME: Record<string, { label: string; color: string }> = {
  goal: { label: "Goal", color: "var(--up)" },
  saved: { label: "Saved", color: "var(--text-muted)" },
  off_target: { label: "Off target", color: "var(--down)" },
  blocked: { label: "Blocked", color: "var(--text-muted)" },
};

/** The hover card on a shot, in the spirit of the NBA's: who, how hard the chance was, what happened. */
function ShotCard({ shot, roster }: { shot: Shot; roster: Roster }) {
  const p = roster.players[shot.player];
  const club = roster.clubs[shot.team];
  const outcome = OUTCOME[shot.outcome] ?? { label: shot.outcome, color: "var(--text-muted)" };
  return (
    <>
      <div className="sc-who">
        <span className="sc-badge" style={{ background: club.primary }}>
          {p?.number}
        </span>
        <div>
          <div className="sc-name">{p?.name ?? shot.player}</div>
          <div className="sc-club">{club.short}</div>
        </div>
      </div>
      <div className="sc-body">
        <div>
          <div className="sc-big num">
            {(shot.xg * 100).toFixed(1)}
            <small>%</small>
          </div>
          <div className="sc-label">xG</div>
        </div>
        <div className="sc-facts">
          <div>
            <i className="sc-dot" style={{ background: outcome.color }} />
            {outcome.label}
          </div>
          <div className="num">{clock(shot.t)}</div>
          <div>{shot.shot_type}</div>
        </div>
      </div>
      <div className="sc-hint">Click to watch the replay</div>
    </>
  );
}

/** NBA Inside the Game style beeswarm: every shot placed by xG, goals filled, misses as crosses. */
function ShotQuality({ shots, roster }: { shots: Shot[]; roster: Roster }) {
  const W = 1560;
  const X0 = 300;
  const X1 = 1530;
  const MAX = 0.6;
  const H = 190;
  const GAP = 40;
  const R = 13;
  const TOTAL_H = 2 * H + GAP + 20;
  const xs = (v: number) => X0 + (Math.min(v, MAX) / MAX) * (X1 - X0);
  const ticks = [0, 0.15, 0.3, 0.45, 0.6];
  const [hover, setHover] = useState<{ shot: Shot; x: number; y: number } | null>(null);
  const edge = hover ? (hover.x / W < 0.18 ? "left" : hover.x / W > 0.82 ? "right" : "mid") : "mid";
  const below = hover !== null && hover.y < 190; // no room above a dot in the top row: open the card below it

  return (
    <div className="swarm-wrap" onMouseLeave={() => setHover(null)}>
    <svg viewBox={`0 0 ${W} ${TOTAL_H}`} role="img" aria-label="Shot quality by expected goals">
      {SIDES.map((side, row) => {
        const club = roster.clubs[side];
        const mine = shots.filter((s) => s.team === side).sort((a, b) => a.xg - b.xg);
        const xgTotal = mine.reduce((sum, s) => sum + s.xg, 0);
        const goals = mine.filter((s) => s.outcome === "goal").length;
        const diff = goals - xgTotal;
        const y0 = row * (H + GAP);
        const mid = y0 + H / 2;
        const placed: { x: number; y: number; s: Shot }[] = [];
        for (const s of mine) {
          const x = xs(s.xg);
          let y = mid;
          let k = 0;
          while (placed.some((p) => Math.hypot(p.x - x, p.y - y) < R * 2.1) && k < 40) {
            k++;
            y = mid + (k % 2 ? 1 : -1) * Math.ceil(k / 2) * R * 1.4;
          }
          placed.push({ x, y, s });
        }
        return (
          <g key={side}>
            <rect x={0} y={y0} width={W} height={H} fill="var(--bg)" />
            {ticks.map((v) => (
              <g key={v}>
                {v > 0 && <line x1={xs(v)} x2={xs(v)} y1={y0} y2={y0 + H} stroke="var(--line-dash)" strokeDasharray="3 4" />}
                <text
                  x={xs(v)}
                  y={y0 + H + 18}
                  fontSize={13}
                  fontFamily="Barlow Condensed"
                  fontWeight={700}
                  fill="var(--text-muted)"
                  textAnchor={v === 0 ? "start" : v === MAX ? "end" : "middle"}
                >
                  {v === MAX ? "0.60+ xG" : v.toFixed(2)}
                </text>
              </g>
            ))}
            <rect x={24} y={y0 + 30} width={54} height={54} rx={2} fill={club.primary} />
            <text x={51} y={y0 + 66} textAnchor="middle" fontSize={22} fontFamily="Barlow Condensed" fontWeight={800} fill="#000">
              {club.short}
            </text>
            <text x={94} y={y0 + 72} fontSize={52} fontFamily="Barlow Condensed" fontWeight={800} fill="var(--text)">
              {xgTotal.toFixed(2)}
              <tspan fontSize={22} dx={6}>
                xG
              </tspan>
            </text>
            <text x={96} y={y0 + 96} fontSize={15} fontFamily="Barlow" fontWeight={600} fill="var(--text-muted)">
              {goals} {goals === 1 ? "goal" : "goals"} from {mine.length} shots
            </text>
            {mine.length > 0 && (
              <text x={96} y={y0 + 118} fontSize={14} fontFamily="Barlow" fontWeight={600} fill={diff >= 0 ? "var(--up)" : "var(--down)"}>
                {signed(diff)} goals vs expected
              </text>
            )}
            {placed.map(({ x, y, s }) => {
              const label = `${playerName(roster, s.player)}, ${clock(s.t)}. xG ${s.xg.toFixed(2)}, ${s.outcome.replace("_", " ")}. Watch the replay.`;
              const on = hover?.shot.event_id === s.event_id;
              return (
                <a
                  key={s.event_id}
                  href={shotHref(s.event_id)}
                  className="mark"
                  aria-label={label}
                  onMouseEnter={() => setHover({ shot: s, x, y })}
                  onFocus={() => setHover({ shot: s, x, y })}
                  onBlur={() => setHover(null)}
                >
                  {on && <circle cx={x} cy={y} r={R + 6} fill="none" stroke="var(--signal)" strokeWidth={2} />}
                  {s.outcome === "goal" ? (
                    <circle cx={x} cy={y} r={R} fill={club.primary} />
                  ) : (
                    <g stroke={on ? "var(--text)" : "#7A7E86"} strokeWidth={3} strokeLinecap="round">
                      <line x1={x - 8} y1={y - 8} x2={x + 8} y2={y + 8} />
                      <line x1={x - 8} y1={y + 8} x2={x + 8} y2={y - 8} />
                    </g>
                  )}
                  <rect x={x - R} y={y - R} width={2 * R} height={2 * R} fill="transparent" />
                </a>
              );
            })}
          </g>
        );
      })}
    </svg>
      {hover && (
        <div
          className={`shotcard ${edge}${below ? " below" : ""}`}
          style={{
            left: `${(hover.x / W) * 100}%`,
            top: `${((below ? hover.y + R + 10 : hover.y - R - 10) / TOTAL_H) * 100}%`,
          }}
          role="tooltip"
        >
          <ShotCard shot={hover.shot} roster={roster} />
        </div>
      )}
    </div>
  );
}

type SortKey = keyof Omit<LeverageRow, "player" | "team">;
const COLUMNS: [SortKey, string][] = [
  ["total", "Total"],
  ["shot_making", "Shot making"],
  ["creation", "Creation"],
  ["defending", "Defending"],
  ["turnovers", "Turnovers"],
];

function LeverageTable({ rows, roster }: { rows: LeverageRow[]; roster: Roster }) {
  const [sort, setSort] = useState<SortKey>("total");
  const [club, setClub] = useState<Side | "all">("all");
  const shown = rows
    .filter((r) => club === "all" || r.team === club)
    .sort((a, b) => b[sort] - a[sort])
    .slice(0, 12);
  const max = Math.max(1.5, ...rows.map((r) => Math.abs(r.total)));
  return (
    <div className="panel">
      <div className="ph">
        <h3>Player leverage</h3>
        <div className="filters">
          {(["all", "home", "away"] as const).map((c) => (
            <button key={c} className={club === c ? "on" : ""} onClick={() => setClub(c)}>
              {c === "all" ? "All" : roster.clubs[c].short}
            </button>
          ))}
        </div>
      </div>
      <div className="pb" style={{ paddingTop: 6 }}>
        {shown.length === 0 ? (
          <div className="empty">Leverage builds as the match is played.</div>
        ) : (
          <table className="lv">
            <thead>
              <tr>
                <th>Player</th>
                {COLUMNS.map(([key, label]) => (
                  <th key={key} className={sort === key ? "sorted" : ""} onClick={() => setSort(key)}>
                    {label}
                    {sort === key ? " ↓" : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const p = roster.players[r.player];
                const color = roster.clubs[r.team].primary;
                return (
                  <tr key={r.player}>
                    <td>
                      <div className="pl-cell">
                        <span className="shirt" style={{ background: color }}>
                          {p?.number}
                        </span>
                        <a href={playerHref(r.player)}>
                          <b>{p?.name ?? r.player}</b>
                        </a>
                        <em>{roster.clubs[r.team].short}</em>
                      </div>
                    </td>
                    <td>
                      <span className="bar" style={{ width: (Math.abs(r.total) / max) * 80, background: r.total < 0 ? "var(--down)" : color }} />
                      <b className={r.total < 0 ? "neg" : ""}>{signed(r.total)}</b>
                    </td>
                    <td>{signed(r.shot_making)}</td>
                    <td>{signed(r.creation)}</td>
                    <td>{signed(r.defending)}</td>
                    <td className={r.turnovers < 0 ? "neg" : ""}>{signed(r.turnovers)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <div className="label" style={{ marginTop: 10 }}>
          1.0 leverage = 10 points of win value. Credit is earned against expectation.
        </div>
      </div>
    </div>
  );
}

function ShapeStrip({ analyst, roster, halfS, now }: Props) {
  const total = 2 * halfS;
  const colors: Record<string, string> = {
    high_press: "var(--shape-high)",
    mid_block: "var(--shape-mid)",
    low_block: "var(--shape-low)",
  };
  return (
    <div className="pb shape">
      {SIDES.map((side) => {
        const tl = analyst.shape[side].timeline;
        const segs = tl.map(([t, state], i) => {
          const end = i + 1 < tl.length ? tl[i + 1][0] : now;
          return { t, state, w: Math.max(0, ((end - t) / total) * 100) };
        });
        const lead = tl.length ? (tl[0][0] / total) * 100 : (now / total) * 100;
        return (
          <div className="row" key={side}>
            <span className="label">{roster.clubs[side].short}</span>
            <div className="strip">
              <i style={{ width: `${lead}%`, background: "transparent" }} />
              {segs.map((s) => (
                <i key={s.t} title={`${SHAPE_LABEL[s.state]} from ${Math.floor(s.t / 60)}'`} style={{ width: `${s.w}%`, background: colors[s.state] }} />
              ))}
            </div>
          </div>
        );
      })}
      <div className="axis">
        <span />
        <div>
          <span>0'</span>
          <span>15'</span>
          <span>30'</span>
          <span>45'</span>
          <span>60'</span>
          <span>75'</span>
          <span>90'</span>
        </div>
      </div>
      <div className="legend" style={{ marginTop: 12 }}>
        {(["high_press", "mid_block", "low_block"] as const).map((s) => (
          <span key={s}>
            <i className="sw" style={{ borderRadius: 0, background: colors[s] }} />
            {SHAPE_LABEL[s]}
          </span>
        ))}
        <span className="label" style={{ marginLeft: "auto" }}>
          Low block: back line under 36 m and very compact. High press: line over 45 m with pressure on the ball.
        </span>
      </div>
    </div>
  );
}

export function Analyst({ analyst, roster, halfS, now }: Props) {
  const goals = analyst.shots.filter((s) => s.outcome === "goal").sort((a, b) => a.xg - b.xg).slice(0, 3);
  const press = analyst.press.filter((r) => r.rate !== null).slice(0, 6);
  const fastest = Object.entries(analyst.runs)
    .sort((a, b) => b[1].top_speed_kmh - a[1].top_speed_kmh)
    .slice(0, 5);

  return (
    <div className="grid">
      <div className="panel c12">
        <div className="ph">
          <h3>Shot quality</h3>
          <span className="label">Every shot placed by expected goals (xG)</span>
        </div>
        <div className="dirs">
          <span>&larr; More difficult</span>
          <span>Less difficult &rarr;</span>
        </div>
        <div className="swarm">
          <ShotQuality shots={analyst.shots} roster={roster} />
        </div>
      </div>

      <div className="c7">
        <LeverageTable rows={analyst.leverage} roster={roster} />
      </div>

      <div className="c5 col">
        <div className="panel">
          <div className="ph">
            <h3>Press resistance</h3>
            <span className="label">Kept the ball when pressed</span>
          </div>
          <div className="pb">
            {press.length === 0 && <div className="empty">Shown once a player has been pressed 5 times.</div>}
            {press.map((r) => (
              <div className="pr" key={r.player}>
                <div className="pl-cell">
                  <a href={playerHref(r.player)}>
                    <b>{playerName(roster, r.player)}</b>
                  </a>
                  <em>{roster.clubs[r.team].short}</em>
                </div>
                <div className="track">
                  <i style={{ width: `${(r.rate ?? 0) * 100}%`, background: roster.clubs[r.team].primary }} />
                </div>
                <span className="pct num">{Math.round((r.rate ?? 0) * 100)}%</span>
                <span className="att num">{r.attempts} att</span>
              </div>
            ))}
          </div>
        </div>
        <div className="grid" style={{ marginTop: 0 }}>
          <div className="panel c6">
            <div className="ph">
              <h3>Hardest goals</h3>
            </div>
            <div className="pb">
              {goals.length === 0 && <div className="empty">No goals yet.</div>}
              <ul className="lb">
                {goals.map((s, i) => (
                  <li key={s.event_id}>
                    <span className="r">{i + 1}</span>
                    <div>
                      <a href={shotHref(s.event_id)}>
                        <b>{playerName(roster, s.player, true)}</b>
                      </a>{" "}
                      <span className="d">
                        {s.minute}'{s.body_part === "head" ? ", header" : ""}
                      </span>
                    </div>
                    <span className="v num">{s.xg.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="panel c6">
            <div className="ph">
              <h3>Fastest</h3>
            </div>
            <div className="pb">
              <ul className="lb">
                {fastest.map(([pid, run], i) => (
                  <li key={pid}>
                    <span className="r">{i + 1}</span>
                    <div>
                      <b>{playerName(roster, pid, true)}</b> <span className="d">{roster.players[pid]?.side ? roster.clubs[roster.players[pid].side].short : ""}</span>
                    </div>
                    <span className="v num">{run.top_speed_kmh.toFixed(1)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>

      <div className="panel c12">
        <div className="ph">
          <h3>Team shape</h3>
          <span className="label">Out of possession, rolling 60 s</span>
        </div>
        <ShapeStrip analyst={analyst} roster={roster} halfS={halfS} now={now} />
      </div>
    </div>
  );
}
