import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { CSSProperties, Ref } from "react";
import type { Frame, FxEvent, Roster } from "../types";

interface Props {
  frame: Frame | null;
  roster: Roster;
  focus: string | null;
  tagged: Set<string>;
  speed: number;
  fx: FxEvent[];
  labels?: Record<string, string>; // extra text on a player's tag, e.g. their value in metric mode
}

const LINE = { fill: "none", stroke: "rgba(255,255,255,.25)", strokeWidth: 0.3 } as const;
const SPOT = "rgba(255,255,255,.35)";
const POST = "#F4F4F1";
const FOCUS_TRAIL_S = 12;
const CARD_COLOR = { yellow: "#f5c518", red: "#ff4d4d" } as const;
const MOVING_MS = 1.2; // below this a player shows no heading tick
const SPRINT_MS = 7.0; // the sprint threshold used everywhere else
const CARRIER_M = 2.0; // nearest player within this of a ball on the ground has it
const BALL_TRAIL_MS = 180;
const SPIN_DEG_PER_M = 40;
const GOAL_RIPPLE_MS = 2500;
const PEN_ARC_DY = Math.sqrt(9.15 ** 2 - 5.5 ** 2); // where the penalty arc meets the box edge

/** SVG ids must be unique per page; useId gives colons, which url(#...) dislikes. */
function useSvgId() {
  return useId().replace(/:/g, "");
}

/** Mowing stripes, so the pitch reads as grass at a glance. */
export function Grass() {
  const w = 105 / 18;
  return (
    <g>
      {Array.from({ length: 11 }, (_, k) => 2 * k - 1).map((i) => (
        <rect key={i} x={i * w} y={-3} width={w} height={74} fill="#fff" opacity={0.03} />
      ))}
    </g>
  );
}

/** Lines, arcs and goals. `ripple` shakes the net of one goal (end 0 is x = 0) after a goal. */
export function Markings({ ripple }: { ripple?: { end: 0 | 1; id: string } | null }) {
  const net = `net${useSvgId()}`;
  return (
    <g>
      <defs>
        <pattern id={net} width={0.7} height={0.7} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <path d="M0 0V0.7M0 0H0.7" stroke="rgba(255,255,255,.45)" strokeWidth={0.07} fill="none" />
        </pattern>
      </defs>
      <rect x={0} y={0} width={105} height={68} {...LINE} />
      <line x1={52.5} y1={0} x2={52.5} y2={68} {...LINE} />
      <circle cx={52.5} cy={34} r={9.15} {...LINE} />
      <circle cx={52.5} cy={34} r={0.4} fill={SPOT} />
      <path d="M0,1A1 1 0 0 0 1,0M104,0A1 1 0 0 0 105,1M1,68A1 1 0 0 0 0,67M105,67A1 1 0 0 0 104,68" {...LINE} />
      {([0, 1] as const).map((end) => {
        const left = end === 0;
        const box = left ? 16.5 : 105 - 16.5;
        const line = left ? 0 : 105;
        const shaking = ripple?.end === end;
        return (
          <g key={end}>
            <rect x={left ? 0 : 105 - 16.5} y={13.84} width={16.5} height={40.32} {...LINE} />
            <rect x={left ? 0 : 105 - 5.5} y={24.84} width={5.5} height={18.32} {...LINE} />
            <path d={`M${box},${34 - PEN_ARC_DY}A9.15 9.15 0 0 ${left ? 1 : 0} ${box},${34 + PEN_ARC_DY}`} {...LINE} />
            <circle cx={left ? 11 : 94} cy={34} r={0.35} fill={SPOT} />
            <g key={shaking ? ripple.id : "still"} className={shaking ? "net-ripple" : undefined}
              style={{ "--dir": left ? -1 : 1 } as CSSProperties}>
              <rect x={left ? -2 : 105} y={30.34} width={2} height={7.32} fill={`url(#${net})`} stroke="rgba(255,255,255,.55)" strokeWidth={0.12} />
            </g>
            <line x1={line} y1={30.34} x2={line} y2={37.66} stroke={POST} strokeWidth={0.4} />
            <circle cx={line} cy={30.34} r={0.32} fill={POST} />
            <circle cx={line} cy={37.66} r={0.32} fill={POST} />
          </g>
        );
      })}
    </g>
  );
}

const pentagon = (cx: number, cy: number, size: number, deg: number) =>
  Array.from({ length: 5 }, (_, i) => {
    const a = ((deg + 72 * i) * Math.PI) / 180;
    return `${(cx + size * Math.cos(a)).toFixed(3)},${(cy + size * Math.sin(a)).toFixed(3)}`;
  }).join(" ");

/**
 * A classic black and white football centred on 0,0. The panels sit in their own group so they can
 * spin (`spin` in degrees, or `spinRef` for code that animates outside React) while the light stays put.
 */
export function Ball({ r = 1, spin, spinRef }: { r?: number; spin?: number; spinRef?: Ref<SVGGElement> }) {
  const id = useSvgId();
  const dirs = [0, 1, 2, 3, 4].map((k) => -90 + 72 * k);
  return (
    <g>
      <defs>
        <radialGradient id={`bl${id}`} cx="0.38" cy="0.34" r="0.75">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="0.7" stopColor="#e4e6e8" />
          <stop offset="1" stopColor="#9aa0a6" />
        </radialGradient>
        <radialGradient id={`bs${id}`} cx="0.4" cy="0.36" r="0.7">
          <stop offset="0.55" stopColor="#000" stopOpacity={0} />
          <stop offset="1" stopColor="#000" stopOpacity={0.35} />
        </radialGradient>
        <clipPath id={`bc${id}`}>
          <circle r={r} />
        </clipPath>
      </defs>
      <circle r={r} fill={`url(#bl${id})`} />
      <g clipPath={`url(#bc${id})`}>
        <g ref={spinRef} transform={spin === undefined ? undefined : `rotate(${spin.toFixed(1)})`}>
          <g stroke="#3a3d42" strokeWidth={r * 0.05}>
            {dirs.map((d) => {
              const a = (d * Math.PI) / 180;
              return <line key={d} x1={Math.cos(a) * r * 0.38} y1={Math.sin(a) * r * 0.38} x2={Math.cos(a) * r * 0.7} y2={Math.sin(a) * r * 0.7} />;
            })}
          </g>
          <g fill="#14161a">
            <polygon points={pentagon(0, 0, r * 0.38, -90)} />
            {dirs.map((d) => {
              const a = (d * Math.PI) / 180;
              return <polygon key={d} points={pentagon(Math.cos(a) * r * 1.05, Math.sin(a) * r * 1.05, r * 0.38, d + 180)} />;
            })}
          </g>
        </g>
      </g>
      <circle r={r} fill={`url(#bs${id})`} />
      <circle r={r} fill="none" stroke="#000" strokeOpacity={0.6} strokeWidth={r * 0.07} />
    </g>
  );
}

interface TokenProps {
  number: number;
  kit: string;
  trim: string;
  keeper: boolean;
  heading: number | null; // degrees, direction of travel
  speed: number; // m/s
  carrier: boolean;
  focus: boolean;
}

/** A player as a broadcast tracking token: kit colours, ground shadow, heading tick, sprint streak. */
export function PlayerToken({ number, kit, trim, keeper, heading, speed, carrier, focus }: TokenProps) {
  const r = focus ? 1.9 : 1.55;
  const streak = speed > SPRINT_MS ? 1.6 + (speed - SPRINT_MS) * 0.9 : 0;
  return (
    <>
      <ellipse cx={0.3} cy={0.45} rx={r} ry={r * 0.82} fill="#000" opacity={0.38} />
      {heading !== null && (
        <g className="heading" style={{ transform: `rotate(${heading}deg)` }}>
          {streak > 0 && <polygon points={`${-r * 0.5},${-r * 0.62} ${-r - streak},0 ${-r * 0.5},${r * 0.62}`} fill={kit} opacity={0.35} />}
          <polygon points={`${r + 0.25},-0.55 ${r + 1.1},0 ${r + 0.25},0.55`} fill="#F4F4F1" opacity={0.85} />
        </g>
      )}
      {carrier && <circle r={r + 0.95} fill="none" stroke="#F4F4F1" strokeWidth={0.22} />}
      {focus && <circle r={3.1} fill="none" stroke="var(--signal)" strokeWidth={0.35} />}
      <circle r={r} fill={keeper ? "#16181b" : kit} stroke={keeper ? kit : trim} strokeWidth={0.32} />
      <text y={0.62} textAnchor="middle" fontSize={1.7} fontWeight={700} fill={keeper ? kit : trim} fontFamily="Barlow">
        {number}
      </text>
    </>
  );
}

type Pos = Map<string, number[]>;

/**
 * Smooth movement between tracking frames. Each new frame starts a glide from where everything is
 * drawn now to where the frame says it is, lasting the measured gap between frames, so motion is
 * continuous at any speed. Runs on requestAnimationFrame and writes transforms directly, outside React.
 * The ball also carries its height: it grows and its shadow drifts away as it rises, and it spins
 * with the distance it travels.
 */
function useGlide(frame: Frame | null) {
  const nodes = useRef(new Map<string, SVGGraphicsElement>());
  const shadow = useRef<SVGEllipseElement>(null);
  const spin = useRef<SVGGElement>(null);
  const trail = useRef<SVGPolylineElement>(null);
  const trailPts = useRef<[number, number, number][]>([]);
  const from = useRef<Pos>(new Map());
  const to = useRef<Pos>(new Map());
  const drawn = useRef<Pos>(new Map());
  const start = useRef(0);
  const gap = useRef(200);
  const last = useRef(0);

  useEffect(() => {
    if (!frame) return;
    const now = performance.now();
    if (last.current) gap.current = Math.min(500, Math.max(60, 0.7 * gap.current + 0.3 * (now - last.current)));
    last.current = now;
    const next: Pos = new Map(frame.players.map((p) => [p[0], [p[1], p[2]]]));
    next.set("ball", [frame.ball[0], frame.ball[1], frame.ball[2]]);
    from.current = new Map(drawn.current);
    to.current = next;
    start.current = now;
  }, [frame]);

  useEffect(() => {
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    const tick = () => {
      const now = performance.now();
      const a = still ? 1 : Math.min(1, (now - start.current) / gap.current);
      for (const [id, target] of to.current) {
        const f = from.current.get(id);
        const v = target.map((t, k) => (f && f[k] !== undefined ? f[k] + (t - f[k]) * a : t));
        drawn.current.set(id, v);
        const [x, y] = v;
        if (id !== "ball") {
          nodes.current.get(id)?.setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)})`);
          continue;
        }
        const z = Math.min(Math.max(v[2] ?? 0, 0), 12);
        nodes.current.get(id)?.setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)}) scale(${(1 + z * 0.06).toFixed(3)})`);
        spin.current?.setAttribute("transform", `rotate(${(((x + y) * SPIN_DEG_PER_M) % 360).toFixed(1)})`);
        shadow.current?.setAttribute(
          "transform",
          `translate(${(x + z * 0.3).toFixed(2)} ${(y + z * 0.45).toFixed(2)}) scale(${Math.max(0.45, 1 - z * 0.05).toFixed(3)})`,
        );
        trailPts.current = [...trailPts.current.filter((p) => now - p[2] < BALL_TRAIL_MS), [x, y, now]];
        trail.current?.setAttribute("points", trailPts.current.map((p) => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" "));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  /** Ref for a moving element: registers it and places it at once, so it never flashes at 0,0. */
  const bind = (id: string) => (el: SVGGraphicsElement | null) => {
    if (!el) {
      nodes.current.delete(id);
      return;
    }
    nodes.current.set(id, el);
    const p = drawn.current.get(id) ?? to.current.get(id);
    if (p && !el.hasAttribute("transform")) el.setAttribute("transform", `translate(${p[0]} ${p[1]})`);
  };
  return { bind, shadow, spin, trail };
}

/** Direction of travel per player from consecutive frames, unwrapped so the tick turns the short way. */
function useHeadings(frame: Frame | null) {
  const prev = useRef(new Map<string, [number, number]>());
  const angle = useRef(new Map<string, number>());
  return useMemo(() => {
    const out = new Map<string, number>();
    if (!frame) return out;
    for (const [id, x, y, v] of frame.players) {
      const p = prev.current.get(id);
      if (p && v >= MOVING_MS && (x - p[0]) ** 2 + (y - p[1]) ** 2 > 1e-4) {
        const a = (Math.atan2(y - p[1], x - p[0]) * 180) / Math.PI;
        const was = angle.current.get(id) ?? a;
        angle.current.set(id, was + ((((a - was) % 360) + 540) % 360) - 180);
      }
      prev.current.set(id, [x, y]);
      const h = angle.current.get(id);
      if (v >= MOVING_MS && h !== undefined) out.set(id, h);
    }
    return out;
  }, [frame]);
}

/** The player on the ball: nearest to it while it is on the ground. */
export function carrierOf(players: [string, number, number, number][], ball: [number, number, number]): string | null {
  if (ball[2] > 1.5) return null;
  let best: string | null = null;
  let bestD = CARRIER_M;
  for (const [id, x, y] of players) {
    const d = Math.hypot(x - ball[0], y - ball[1]);
    if (d < bestD) {
      bestD = d;
      best = id;
    }
  }
  return best;
}

/** How long an effect stays on screen: shorter at high speed so the pitch does not fill with lines. */
const life = (base: number, speed: number, floor = 0.4) => Math.max(floor, base / Math.sqrt(speed));

export function Pitch({ frame, roster, focus, tagged, speed, fx, labels = {} }: Props) {
  const glide = useGlide(frame);
  const headings = useHeadings(frame);
  const [focusTrail, setFocusTrail] = useState<[number, number, number][]>([]);

  useEffect(() => {
    if (!frame || !focus) return;
    const me = frame.players.find((p) => p[0] === focus);
    setFocusTrail((prev) => {
      const kept = prev.filter((p) => frame.t - p[2] <= FOCUS_TRAIL_S && p[2] <= frame.t);
      return me ? [...kept, [me[1], me[2], frame.t]] : kept;
    });
  }, [frame, focus]);

  useEffect(() => setFocusTrail([]), [focus]);

  const focusColor = focus ? roster.clubs[roster.players[focus]?.side ?? "home"].primary : "";
  const carrier = frame ? carrierOf(frame.players, frame.ball) : null;
  const now = performance.now();
  const lifeOf = (e: FxEvent) =>
    e.type === "goal" ? GOAL_RIPPLE_MS / 1000 : e.type === "card" ? life(3, speed, 1.6) : e.type === "shot" ? life(2, speed, 0.8) : life(1.3, speed);
  const live = fx.filter((e) => now - e.at < lifeOf(e) * 1000);
  const dur = (e: FxEvent): CSSProperties => ({ animationDuration: `${lifeOf(e)}s` });
  const color = (e: FxEvent) => roster.clubs[e.team].primary;
  const passes = live.filter((e) => e.type === "pass" && e.end_x !== null && e.end_y !== null);
  const marks = live.filter((e) => e.type !== "pass" && e.type !== "goal");
  const goal = [...live].reverse().find((e) => e.type === "goal");
  const ripple = goal ? { end: (goal.team === "home" ? 1 : 0) as 0 | 1, id: goal.id } : null;

  return (
    <svg className="pitch" viewBox="-3 -3 111 74" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Live pitch">
      <Grass />
      <Markings ripple={ripple} />
      <text className="pitch-dir" x={0} y={70.6}>
        &larr; {roster.clubs.away.short} attack
      </text>
      <text className="pitch-dir" x={105} y={70.6} textAnchor="end">
        {roster.clubs.home.short} attack &rarr;
      </text>
      {focus && focusTrail.length > 1 && (
        <polyline
          points={focusTrail.map((p) => `${p[0]},${p[1]}`).join(" ")}
          fill="none"
          stroke={focusColor}
          strokeWidth={1.4}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.35}
        />
      )}

      {passes.map((e) => (
        <path
          key={e.id}
          className={`fx-pass${e.outcome === "complete" ? "" : " miss"}`}
          d={`M${e.x},${e.y}L${e.end_x},${e.end_y}`}
          pathLength={1}
          stroke={e.outcome === "complete" ? color(e) : "#fff"}
          style={dur(e)}
        />
      ))}

      {frame && <ellipse ref={glide.shadow} className="ball-shadow" rx={1.05} ry={0.8} />}

      {frame?.players.map(([id, , , speedMs]) => {
        const info = roster.players[id];
        if (!info) return null;
        const club = roster.clubs[info.side];
        const isFocus = id === focus;
        const dim = focus !== null && !isFocus && !tagged.has(id);
        const showTag = isFocus || tagged.has(id);
        const extra = labels[id] ? `  ${labels[id].toUpperCase()}` : "";
        const tag = isFocus ? `${info.short.toUpperCase()}  ${(speedMs * 3.6).toFixed(1)} KM/H` : `${info.short.toUpperCase()}${extra}`;
        const tagW = tag.length * 0.95 + 2;
        return (
          <g key={id} ref={glide.bind(id)} style={{ opacity: dim ? 0.3 : 1, transition: "opacity 300ms" }}>
            <PlayerToken
              number={info.number}
              kit={club.primary}
              trim={club.secondary}
              keeper={info.position === "GK"}
              heading={headings.get(id) ?? null}
              speed={speedMs}
              carrier={id === carrier}
              focus={isFocus}
            />
            {showTag && (
              <g transform="translate(3.4,-2.6)">
                <rect width={tagW} height={3.4} fill="#000" opacity={0.85} />
                <rect width={0.5} height={3.4} fill={club.primary} />
                <text x={1.2} y={2.4} fontSize={2} fontWeight={700} fill="#F4F4F1" fontFamily="Barlow Condensed">
                  {tag}
                </text>
              </g>
            )}
          </g>
        );
      })}

      {marks.map((e) => {
        if (e.type === "shot" && e.end_x !== null && e.end_y !== null) {
          return (
            <g key={e.id}>
              <path className="fx-shot" d={`M${e.x},${e.y}L${e.end_x},${e.end_y}`} pathLength={1} stroke={color(e)} style={dur(e)} />
              <circle className="fx-burst" cx={e.x} cy={e.y} r={2.2} stroke={color(e)} style={dur(e)} />
            </g>
          );
        }
        if (e.type === "tackle" || e.type === "interception") {
          return (
            <g key={e.id} transform={`translate(${e.x} ${e.y})`}>
              <circle className="fx-burst" r={2.4} stroke={color(e)} style={dur(e)} />
              <text className="fx-tag" y={-3.6} textAnchor="middle" style={dur(e)}>
                {e.type === "tackle" ? "TACKLE WON" : "INTERCEPTED"}
              </text>
            </g>
          );
        }
        if (e.type === "card") {
          const fill = e.outcome === "red" ? CARD_COLOR.red : CARD_COLOR.yellow;
          return (
            <g key={e.id} transform={`translate(${e.x + 1.6} ${e.y - 5.2})`}>
              <rect className="fx-card" width={2.2} height={3} rx={0.25} fill={fill} stroke="#000" strokeWidth={0.2} style={dur(e)} />
            </g>
          );
        }
        return null;
      })}

      {frame && <polyline ref={glide.trail} className="ball-trail" />}
      {frame && (
        <g ref={glide.bind("ball")}>
          <Ball r={1} spinRef={glide.spin} />
        </g>
      )}
    </svg>
  );
}
