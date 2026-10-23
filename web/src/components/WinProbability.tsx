import type { Card, Roster, Stats } from "../types";
import { Tick } from "../tween";

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

export function WinProbability({ stats, history, cards, roster, halfS }: Props) {
  const total = 2 * halfS;
  const x = (t: number) => (Math.min(t, total) / total) * W;
  const y = (v: number) => H - v * H;
  const points = [...history, [stats.t, ...stats.win_prob]].sort((a, b) => a[0] - b[0]);

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

  const home = roster.clubs.home;
  const away = roster.clubs.away;
  const [h, d, a] = stats.win_prob;
  const markers = cards
    .filter((c) => MARKED.has(c.moment.kind))
    .map((c) => ({
      t: Number(c.moment.state_ref.split("@")[1]),
      color: c.moment.kind === "red_card" ? "var(--down)" : roster.clubs[c.moment.team ?? "home"].primary,
      id: c.moment.moment_id,
    }));

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
      <svg viewBox={`0 -4 ${W} ${H + 22}`} style={{ width: "100%", marginTop: 14, display: "block" }} role="img" aria-label="Win probability over the match">
        {[1, 2, 3].map((i) => (
          <line key={i} x1={0} x2={W} y1={(H * i) / 4} y2={(H * i) / 4} stroke="var(--line-dash)" strokeDasharray="2 4" />
        ))}
        <path d={band((p) => p[1], () => 0)} fill={home.primary} opacity={0.9} />
        <path d={band((p) => p[1] + p[2], (p) => p[1])} fill="#3A3D44" />
        <path d={band(() => 1, (p) => p[1] + p[2])} fill={away.primary} opacity={0.9} />
        <line x1={x(halfS)} x2={x(halfS)} y1={0} y2={H} stroke="#000" strokeWidth={1.5} />
        {markers.map((m) => (
          <g key={m.id}>
            <line x1={x(m.t)} x2={x(m.t)} y1={-2} y2={H} stroke="#000" strokeWidth={1} />
            <rect x={x(m.t) - 1} y={0} width={2} height={8} fill={m.color} />
          </g>
        ))}
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
    </>
  );
}
