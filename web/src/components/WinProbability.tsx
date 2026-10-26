import { useRef, useState } from "react";
import type { Card, Roster, Stats } from "../types";
import { Tick } from "../tween";
import { KIND_LABEL } from "../format";

interface Props {
  stats: Stats;
  history: number[][];
  cards: Card[];
  roster: Roster;
  halfS: number;
}

const W = 600;
const H = 150;
const MARKED = new Set(["goal", "low_xg_goal", "red_card"]);
const NEAR_S = 120; // a key moment within two minutes of the cursor is shown with the reading
const SWING_S = 300; // the change shown is against five minutes earlier

const pct = (v: number) => `${Math.round(v * 100)}%`;
const minute = (t: number) => `${Math.floor(t / 60)}'`;

export function WinProbability({ stats, history, cards, roster, halfS }: Props) {
  const total = 2 * halfS;
  const x = (t: number) => (Math.min(t, total) / total) * W;
  const y = (v: number) => H - v * H;
  const points = [...history, [stats.t, ...stats.win_prob]].sort((a, b) => a[0] - b[0]);
  const box = useRef<HTMLDivElement>(null);
  const [hoverT, setHoverT] = useState<number | null>(null);

  // A stepped band: each value holds until the next point, like a broadcast win probability strip.
  const band = (top: (p: number[]) => number, bottom: (p: number[]) => number) => {
    if (points.length === 0) return "";
    const last = points[points.length - 1];
    let d = `M${x(points[0][0])},${y(top(points[0]))}`;
    for (let i = 1; i < points.length; i++) d += `H${x(points[i][0])}V${y(top(points[i]))}`;
    d += `L${x(last[0])},${y(bottom(last))}`;
    for (let i = points.length - 1; i > 0; i--) d += `V${y(bottom(points[i - 1]))}H${x(points[i - 1][0])}`;
    return d + "Z";
  };
  // The edge between the home band and the draw band, drawn as a line so every swing reads.
  const edge = points.length
    ? points.reduce((d, p, i) => (i === 0 ? `M${x(p[0])},${y(p[1])}` : `${d}H${x(p[0])}V${y(p[1])}`), "")
    : "";

  const home = roster.clubs.home;
  const away = roster.clubs.away;
  const [h, d, a] = stats.win_prob;
  const moments = cards.map((c) => ({ card: c, t: Number(c.moment.state_ref.split("@")[1]) }));
  const markers = moments
    .filter((m) => MARKED.has(m.card.moment.kind))
    .map((m) => ({
      t: m.t,
      color: m.card.moment.kind === "red_card" ? "var(--down)" : roster.clubs[m.card.moment.team ?? "home"].primary,
      id: m.card.moment.moment_id,
    }));

  const at = (t: number) => {
    let found = points[0];
    for (const p of points) {
      if (p[0] <= t) found = p;
      else break;
    }
    return found;
  };

  const onMove = (e: React.PointerEvent) => {
    const r = box.current?.getBoundingClientRect();
    if (!r || points.length === 0) return;
    const t = ((e.clientX - r.left) / r.width) * total;
    setHoverT(Math.max(0, Math.min(t, stats.t)));
  };

  let reading = null;
  if (hoverT !== null && points.length) {
    const p = at(hoverT);
    const before = at(Math.max(hoverT - SWING_S, 0));
    const swing = Math.round((p[1] - before[1]) * 100);
    const near = moments
      .filter((m) => Math.abs(m.t - hoverT) <= NEAR_S && m.t <= stats.t)
      .sort((m1, m2) => Math.abs(m1.t - hoverT) - Math.abs(m2.t - hoverT))[0];
    const left = (x(hoverT) / W) * 100;
    reading = (
      <div className={`wp-tip ${left > 60 ? "flip" : ""}`} style={{ left: `${left}%` }}>
        <div className="wp-tip-min num">{minute(hoverT)}</div>
        <div className="wp-tip-row">
          <span><i style={{ background: home.primary }} />{home.short} {pct(p[1])}</span>
          <span><i style={{ background: "#3A3D44" }} />Draw {pct(p[2])}</span>
          <span><i style={{ background: away.primary }} />{away.short} {pct(p[3])}</span>
        </div>
        {hoverT >= SWING_S && swing !== 0 && (
          <div className={`wp-tip-swing ${swing > 0 ? "up" : "down"}`}>
            {home.short} {swing > 0 ? "+" : ""}
            {swing} pts since {minute(hoverT - SWING_S)}
          </div>
        )}
        {near && (
          <div className="wp-tip-moment">
            <b>
              {minute(near.t)} {KIND_LABEL[near.card.moment.kind] ?? near.card.moment.kind}
            </b>
            <span>{near.card.cues.casual.text}</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <>
      <div className="wpnums">
        <div>
          <div className="hero num" style={{ color: home.primary }}>
            <Tick value={h} scale={100} />
            <small>%</small>
          </div>
          <div className="label">{home.short} win</div>
        </div>
        <div>
          <div className="hero num" style={{ color: "var(--text-muted)" }}>
            <Tick value={d} scale={100} />
            <small>%</small>
          </div>
          <div className="label">Draw</div>
        </div>
        <div>
          <div className="hero num" style={{ color: away.primary }}>
            <Tick value={a} scale={100} />
            <small>%</small>
          </div>
          <div className="label">{away.short} win</div>
        </div>
      </div>
      <div className="wp-chart" ref={box} onPointerMove={onMove} onPointerLeave={() => setHoverT(null)}>
        <svg viewBox={`0 -4 ${W} ${H + 22}`} style={{ width: "100%", marginTop: 14, display: "block" }} role="img" aria-label="Win probability over the match. Hover for the reading at any minute.">
          {[1, 2, 3].map((i) => (
            <line key={i} x1={0} x2={W} y1={(H * i) / 4} y2={(H * i) / 4} stroke="var(--line-dash)" strokeDasharray="2 4" />
          ))}
          <path d={band((p) => p[1], () => 0)} fill={home.primary} opacity={0.82} />
          <path d={band((p) => p[1] + p[2], (p) => p[1])} fill="#3A3D44" />
          <path d={band(() => 1, (p) => p[1] + p[2])} fill={away.primary} opacity={0.82} />
          <path d={edge} fill="none" stroke="#fff" strokeWidth={1.5} opacity={0.85} />
          <line x1={0} x2={W} y1={H / 2} y2={H / 2} stroke="#000" strokeOpacity={0.35} strokeDasharray="4 4" />
          <line x1={x(halfS)} x2={x(halfS)} y1={0} y2={H} stroke="#000" strokeWidth={1.5} />
          {markers.map((m) => (
            <g key={m.id}>
              <line x1={x(m.t)} x2={x(m.t)} y1={-2} y2={H} stroke="#000" strokeWidth={1} />
              <rect x={x(m.t) - 1} y={0} width={2} height={8} fill={m.color} />
            </g>
          ))}
          {hoverT !== null && (
            <g pointerEvents="none">
              <line x1={x(hoverT)} x2={x(hoverT)} y1={-4} y2={H} stroke="var(--signal)" strokeWidth={1.5} />
              <circle cx={x(hoverT)} cy={y(at(hoverT)[1])} r={4} fill="var(--signal)" stroke="#000" strokeWidth={1.5} />
            </g>
          )}
          {[
            [0, "0'", "start"],
            [halfS, "HT", "middle"],
            [total, "90'", "end"],
          ].map(([t, label, anchor]) => (
            <text
              key={String(label)}
              x={x(Number(t))}
              y={H + 16}
              fontSize={11}
              fill="var(--text-muted)"
              fontFamily="Barlow"
              fontWeight={600}
              textAnchor={anchor as "start" | "middle" | "end"}
            >
              {label}
            </text>
          ))}
        </svg>
        {reading}
        {hoverT === null && <div className="wp-hint label">Hover the chart for any minute</div>}
      </div>
    </>
  );
}
