import { useState } from "react";
import type { Network, Roster, Shot, Side } from "../types";
import { Markings } from "./Pitch";
import { playerHref } from "../route";

/** Pitch coordinates seen from a team attacking left to right. */
const attacking = (x: number, y: number, side: Side): [number, number] => (side === "home" ? [x, y] : [105 - x, 68 - y]);

/** Cumulative xG for both teams over the match, goals marked: who created more, and when. */
export function XGRace({ shots, roster, now, halfS }: { shots: Shot[]; roster: Roster; now: number; halfS: number }) {
  const W = 760;
  const H = 260;
  const left = 44;
  const right = 70;
  const y0 = 16;
  const bottom = 30;
  const total = 2 * halfS;
  const sorted = [...shots].sort((a, b) => a.t - b.t);
  const totals = { home: 0, away: 0 };
  const lines: Record<Side, [number, number][]> = { home: [[0, 0]], away: [[0, 0]] };
  const goals: { t: number; v: number; side: Side; player: string }[] = [];
  for (const s of sorted) {
    const before = totals[s.team];
    totals[s.team] += s.xg;
    lines[s.team].push([s.t, before], [s.t, totals[s.team]]);
    if (s.outcome === "goal") goals.push({ t: s.t, v: totals[s.team], side: s.team, player: s.player });
  }
  (["home", "away"] as Side[]).forEach((side) => lines[side].push([now, totals[side]]));
  const top = Math.max(1, totals.home, totals.away) * 1.15;
  const x = (t: number) => left + (Math.min(t, total) / total) * (W - left - right);
  const y = (v: number) => y0 + (1 - v / top) * (H - y0 - bottom);
  const ticks = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4].filter((v) => v <= top);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", display: "block" }} role="img" aria-label="Cumulative xG over the match">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={left} x2={W - right} y1={y(v)} y2={y(v)} stroke="var(--line-dash)" strokeDasharray="2 4" />
          <text x={left - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill="var(--text-muted)" fontFamily="Barlow">
            {v.toFixed(1)}
          </text>
        </g>
      ))}
      <line x1={x(halfS)} x2={x(halfS)} y1={y0} y2={H - bottom} stroke="var(--line)" />
      {[0, halfS, total].map((t, i) => (
        <text key={t} x={x(t)} y={H - 10} fontSize={11} fill="var(--text-muted)" fontFamily="Barlow" fontWeight={600}
          textAnchor={i === 0 ? "start" : i === 1 ? "middle" : "end"}>
          {i === 0 ? "0'" : i === 1 ? "HT" : "90'"}
        </text>
      ))}
      {(["home", "away"] as Side[]).map((side) => {
        const pts = lines[side];
        const color = roster.clubs[side].primary;
        const end = pts[pts.length - 1];
        return (
          <g key={side}>
            <polyline points={pts.map(([t, v]) => `${x(t)},${y(v)}`).join(" ")} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" />
            <text x={x(end[0]) + 8} y={y(end[1]) + 4} fontSize={13} fontWeight={700} fill={color} fontFamily="Barlow Condensed">
              {roster.clubs[side].short} {end[1].toFixed(2)}
            </text>
          </g>
        );
      })}
      {goals.map((g) => (
        <g key={`${g.t}-${g.player}`}>
          <circle cx={x(g.t)} cy={y(g.v)} r={5} fill={roster.clubs[g.side].primary} stroke="#000" strokeWidth={1.5}>
            <title>{`Goal, ${roster.players[g.player]?.name ?? g.player}, ${Math.floor(g.t / 60)}'`}</title>
          </circle>
          <text x={x(g.t)} y={y(g.v) - 10} textAnchor="middle" fontSize={11} fill="var(--text)" fontFamily="Barlow" fontWeight={600}>
            {roster.players[g.player]?.short ?? ""}
          </text>
        </g>
      ))}
    </svg>
  );
}

/** Average positions in possession (tracking) joined by completed passes: how a team actually played. */
export function PassNetwork({ network, roster }: { network: Record<Side, Network>; roster: Roster }) {
  const [side, setSide] = useState<Side>("home");
  const net = network[side];
  const color = roster.clubs[side].primary;
  const maxEdge = Math.max(1, ...net.edges.map((e) => e.n));
  const maxPasses = Math.max(1, ...net.nodes.map((n) => n.passes));
  const pos = new Map(net.nodes.map((n) => [n.player, attacking(n.x, n.y, side)]));

  return (
    <div className="panel">
      <div className="ph">
        <h3>Pass network</h3>
        <div className="filters">
          {(["home", "away"] as Side[]).map((s) => (
            <button key={s} className={side === s ? "on" : ""} onClick={() => setSide(s)}>
              {roster.clubs[s].short}
            </button>
          ))}
        </div>
      </div>
      <div className="pb">
        <svg viewBox="-3 -3 111 74" className="pitch mini" role="img" aria-label={`${roster.clubs[side].name} pass network`}>
          <Markings />
          {net.edges.map((e) => {
            const a = pos.get(e.a);
            const b = pos.get(e.b);
            if (!a || !b) return null;
            return (
              <line key={`${e.a}-${e.b}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={color}
                strokeWidth={0.3 + (e.n / maxEdge) * 1.4} strokeOpacity={0.25 + (e.n / maxEdge) * 0.6} strokeLinecap="round">
                <title>{`${roster.players[e.a]?.short} and ${roster.players[e.b]?.short}: ${e.n} passes`}</title>
              </line>
            );
          })}
          {net.nodes.map((n) => {
            const [nx, ny] = pos.get(n.player)!;
            const info = roster.players[n.player];
            return (
              <a key={n.player} href={playerHref(n.player)}>
                <title>{`${info?.name}: ${n.passes} passes made or received`}</title>
                <circle cx={nx} cy={ny} r={1.5 + 2.2 * Math.sqrt(n.passes / maxPasses)} fill={color} stroke="#000" strokeWidth={0.3} />
                <text x={nx} y={ny + 0.65} textAnchor="middle" fontSize={1.8} fontWeight={700} fill="#000" fontFamily="Barlow">
                  {info?.number}
                </text>
              </a>
            );
          })}
        </svg>
        <div className="maplegend">
          <span>Average position with the ball, from tracking. Lines: 2+ completed passes.</span>
          <span>Attacking &rarr;</span>
        </div>
      </div>
    </div>
  );
}

/** Where a player spent the match, from every tracking frame, drawn attacking left to right. */
export function Heatmap({ grid, side, roster }: { grid: number[][]; side: Side; roster: Roster }) {
  const max = Math.max(1, ...grid.flat());
  const color = roster.clubs[side].primary;
  const cells: { x: number; y: number; w: number; h: number; v: number }[] = [];
  grid.forEach((col, ix) =>
    col.forEach((count, iy) => {
      if (!count) return;
      const x0 = ix * 5;
      const y0 = iy * 5;
      const w = Math.min(5, 105 - x0);
      const h = Math.min(5, 68 - y0);
      const [ax, ay] = attacking(x0 + w / 2, y0 + h / 2, side);
      cells.push({ x: ax - w / 2, y: ay - h / 2, w, h, v: Math.sqrt(count / max) });
    }),
  );
  return (
    <svg viewBox="-3 -3 111 74" className="pitch mini" role="img" aria-label="Heatmap from tracking">
      {cells.map((c) => (
        <rect key={`${c.x}-${c.y}`} x={c.x} y={c.y} width={c.w} height={c.h} fill={color} fillOpacity={0.08 + c.v * 0.8} />
      ))}
      <Markings />
    </svg>
  );
}
