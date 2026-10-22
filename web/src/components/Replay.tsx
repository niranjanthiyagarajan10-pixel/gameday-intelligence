import { useEffect, useMemo, useRef, useState } from "react";
import type { Clip, Roster, Shot } from "../types";
import { clock } from "../format";

interface Props {
  clip: Clip;
  shot: Shot;
  roster: Roster;
}

const LINE = { fill: "none", stroke: "rgba(255,255,255,.25)", strokeWidth: 0.3 } as const;
const RATES = [0.5, 1, 2];

type Pos = Map<string, [number, number]>;

/** Replays a shot from tracking frames: every player and the ball, interpolated between frames. */
export function Replay({ clip, shot, roster }: Props) {
  const frames = clip.frames;
  const t0 = frames.length ? frames[0].t : shot.t;
  const t1 = frames.length ? frames[frames.length - 1].t : shot.t;
  const [playhead, setPlayhead] = useState(t0);
  const [playing, setPlaying] = useState(true);
  const [rate, setRate] = useState(1);
  const last = useRef<number | null>(null);

  const maps = useMemo<Pos[]>(
    () => frames.map((f) => new Map(f.players.map((p) => [p[0], [p[1], p[2]] as [number, number]]))),
    [frames],
  );

  useEffect(() => {
    setPlayhead(t0);
    setPlaying(true);
  }, [t0]);

  useEffect(() => {
    if (!playing) {
      last.current = null;
      return;
    }
    let raf = 0;
    const tick = (now: number) => {
      const dt = last.current === null ? 0 : (now - last.current) / 1000;
      last.current = now;
      setPlayhead((p) => {
        const next = p + dt * rate;
        if (next >= t1) {
          setPlaying(false);
          return t1;
        }
        return next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, rate, t1]);

  // Find the frames either side of the playhead and blend between them.
  let i = 0;
  while (i < frames.length - 2 && frames[i + 1].t <= playhead) i++;
  const a = frames[i];
  const b = frames[Math.min(i + 1, frames.length - 1)];
  const span = b && a && b.t > a.t ? b.t - a.t : 1;
  const u = a ? Math.min(Math.max((playhead - a.t) / span, 0), 1) : 0;
  const lerp = (p: number, q: number) => p + (q - p) * u;

  const passes = clip.events.filter((e) => e.type === "pass" && e.team === shot.team && e.end_x !== null);
  const shotEvent = clip.events.find((e) => e.type === "shot" && Math.abs(e.t - shot.t) < 0.01);
  const shotColor = roster.clubs[shot.team].primary;
  const struck = playhead >= shot.t;
  const [h, aScore] = shot.score_before.split("-");

  if (!a) return <div className="empty">No tracking for this shot.</div>;

  return (
    <div className="replay">
      <div className="replay-stage">
        <svg viewBox="-3 -3 111 74" preserveAspectRatio="xMidYMid meet" className="pitch" role="img" aria-label="Shot replay">
          <rect x={0} y={0} width={105} height={68} {...LINE} />
          <line x1={52.5} y1={0} x2={52.5} y2={68} {...LINE} />
          <circle cx={52.5} cy={34} r={9.15} {...LINE} />
          {[0, 1].map((end) => (
            <g key={end}>
              <rect x={end ? 105 - 16.5 : 0} y={13.84} width={16.5} height={40.32} {...LINE} />
              <rect x={end ? 105 - 5.5 : 0} y={24.84} width={5.5} height={18.32} {...LINE} />
              <rect x={end ? 105 : -1.8} y={30.34} width={1.8} height={7.32} {...LINE} />
            </g>
          ))}
          {passes
            .filter((p) => p.t <= playhead)
            .map((p, n) => (
              <g key={`${p.t}-${n}`} opacity={p.outcome === "complete" ? 0.9 : 0.4}>
                <line x1={p.x} y1={p.y} x2={p.end_x!} y2={p.end_y!} stroke={shotColor} strokeWidth={0.35} strokeDasharray="1 0.6" />
                <circle cx={p.x} cy={p.y} r={1.3} fill="#000" stroke={shotColor} strokeWidth={0.25} />
                <text x={p.x} y={p.y + 0.55} textAnchor="middle" fontSize={1.5} fontWeight={700} fill="#F4F4F1" fontFamily="Barlow Condensed">
                  {n + 1}
                </text>
              </g>
            ))}
          {struck && shotEvent && shotEvent.end_x !== null && (
            <line x1={shotEvent.x} y1={shotEvent.y} x2={shotEvent.end_x} y2={shotEvent.end_y!} stroke="var(--signal)" strokeWidth={0.5} />
          )}
          {[...maps[i].entries()].map(([id, [x0, y0]]) => {
            const next = maps[Math.min(i + 1, maps.length - 1)].get(id) ?? [x0, y0];
            const x = lerp(x0, next[0]);
            const y = lerp(y0, next[1]);
            const info = roster.players[id];
            if (!info) return null;
            const isShooter = id === shot.player;
            return (
              <g key={id} transform={`translate(${x},${y})`} opacity={isShooter || info.side === shot.team ? 1 : 0.75}>
                {isShooter && <circle r={3} fill="none" stroke="var(--signal)" strokeWidth={0.35} />}
                <circle r={isShooter ? 1.9 : 1.55} fill={roster.clubs[info.side].primary} />
                <text y={0.62} textAnchor="middle" fontSize={1.7} fontWeight={700} fill="#000" fontFamily="Barlow">
                  {info.number}
                </text>
                {isShooter && (
                  <g transform="translate(3.4,-2.6)">
                    <rect width={info.short.length * 0.95 + 2} height={3.4} fill="#000" opacity={0.85} />
                    <rect width={0.5} height={3.4} fill={roster.clubs[info.side].primary} />
                    <text x={1.2} y={2.4} fontSize={2} fontWeight={700} fill="#F4F4F1" fontFamily="Barlow Condensed">
                      {info.short.toUpperCase()}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
          <circle cx={lerp(a.ball[0], b.ball[0])} cy={lerp(a.ball[1], b.ball[1])} r={0.75 + Math.min(lerp(a.ball[2], b.ball[2]), 6) * 0.08} fill="#fff" />
        </svg>
        <div className="bug">
          <span className="bug-team" style={{ background: roster.clubs.home.primary }}>
            {roster.clubs.home.short}
          </span>
          <b className="num">{h}</b>
          <span className="num bug-clock">{clock(playhead)}</span>
          <b className="num">{aScore}</b>
          <span className="bug-team" style={{ background: roster.clubs.away.primary }}>
            {roster.clubs.away.short}
          </span>
        </div>
      </div>
      <div className="replay-controls">
        <button onClick={() => (playhead >= t1 ? (setPlayhead(t0), setPlaying(true)) : setPlaying(!playing))}>
          {playing ? "Pause" : playhead >= t1 ? "Replay" : "Play"}
        </button>
        <input
          type="range"
          min={t0}
          max={t1}
          step={0.05}
          value={playhead}
          onChange={(e) => {
            setPlaying(false);
            setPlayhead(Number(e.target.value));
          }}
          aria-label="Scrub replay"
        />
        <span className="num label">{(playhead - shot.t).toFixed(1)} s</span>
        {RATES.map((r) => (
          <button key={r} className={rate === r ? "on" : ""} onClick={() => setRate(r)}>
            {r}x
          </button>
        ))}
      </div>
    </div>
  );
}
