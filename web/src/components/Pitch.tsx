import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { Frame, FxEvent, Roster } from "../types";

interface Props {
  frame: Frame | null;
  roster: Roster;
  focus: string | null;
  tagged: Set<string>;
  speed: number;
  fx: FxEvent[];
}

const LINE = { fill: "none", stroke: "rgba(255,255,255,.25)", strokeWidth: 0.3 } as const;
const SPOT = "rgba(255,255,255,.35)";
const FOCUS_TRAIL_S = 12;
const CARD_COLOR = { yellow: "#f5c518", red: "#ff4d4d" } as const;

export function Markings() {
  return (
    <g>
      <rect x={0} y={0} width={105} height={68} {...LINE} />
      <line x1={52.5} y1={0} x2={52.5} y2={68} {...LINE} />
      <circle cx={52.5} cy={34} r={9.15} {...LINE} />
      <circle cx={52.5} cy={34} r={0.4} fill={SPOT} />
      {[0, 1].map((end) => {
        const left = end === 0;
        return (
          <g key={end}>
            <rect x={left ? 0 : 105 - 16.5} y={13.84} width={16.5} height={40.32} {...LINE} />
            <rect x={left ? 0 : 105 - 5.5} y={24.84} width={5.5} height={18.32} {...LINE} />
            <rect x={left ? -1.8 : 105} y={30.34} width={1.8} height={7.32} {...LINE} />
            <circle cx={left ? 11 : 94} cy={34} r={0.35} fill={SPOT} />
          </g>
        );
      })}
    </g>
  );
}

type Pos = Map<string, [number, number]>;

/**
 * Smooth movement between tracking frames. Each new frame starts a glide from where everything is
 * drawn now to where the frame says it is, lasting the measured gap between frames, so motion is
 * continuous at any speed. Runs on requestAnimationFrame and writes transforms directly, outside React.
 */
function useGlide(frame: Frame | null) {
  const nodes = useRef(new Map<string, SVGGraphicsElement>());
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
    next.set("ball", [frame.ball[0], frame.ball[1]]);
    from.current = new Map(drawn.current);
    to.current = next;
    start.current = now;
  }, [frame]);

  useEffect(() => {
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    const tick = () => {
      const a = still ? 1 : Math.min(1, (performance.now() - start.current) / gap.current);
      for (const [id, [tx, ty]] of to.current) {
        const f = from.current.get(id);
        const x = f ? f[0] + (tx - f[0]) * a : tx;
        const y = f ? f[1] + (ty - f[1]) * a : ty;
        drawn.current.set(id, [x, y]);
        nodes.current.get(id)?.setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)})`);
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
  return bind;
}

/** How long an effect stays on screen: shorter at high speed so the pitch does not fill with lines. */
const life = (base: number, speed: number, floor = 0.4) => Math.max(floor, base / Math.sqrt(speed));

export function Pitch({ frame, roster, focus, tagged, speed, fx }: Props) {
  const bind = useGlide(frame);
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
  const now = performance.now();
  const lifeOf = (e: FxEvent) =>
    e.type === "goal" ? 3.2 : e.type === "card" ? life(3, speed, 1.6) : e.type === "shot" ? life(2, speed, 0.8) : life(1.3, speed);
  const live = fx.filter((e) => now - e.at < lifeOf(e) * 1000);
  const dur = (e: FxEvent): CSSProperties => ({ animationDuration: `${lifeOf(e)}s` });
  const color = (e: FxEvent) => roster.clubs[e.team].primary;
  const passes = live.filter((e) => e.type === "pass" && e.end_x !== null && e.end_y !== null);
  const marks = live.filter((e) => e.type !== "pass");

  return (
    <svg className="pitch" viewBox="-3 -3 111 74" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Live pitch">
      <Markings />
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

      {frame?.players.map(([id, , , speedMs]) => {
        const info = roster.players[id];
        if (!info) return null;
        const club = roster.clubs[info.side].primary;
        const isFocus = id === focus;
        const dim = focus !== null && !isFocus && !tagged.has(id);
        const showTag = isFocus || tagged.has(id);
        const tag = isFocus ? `${info.short.toUpperCase()}  ${(speedMs * 3.6).toFixed(1)} KM/H` : info.short.toUpperCase();
        const tagW = tag.length * 0.95 + 2;
        return (
          <g key={id} ref={bind(id)} style={{ opacity: dim ? 0.3 : 1, transition: "opacity 300ms" }}>
            {isFocus && <circle r={3} fill="none" stroke="var(--signal)" strokeWidth={0.35} />}
            <circle r={isFocus ? 1.9 : 1.55} fill={club} />
            <text y={0.62} textAnchor="middle" fontSize={1.7} fontWeight={700} fill="#000" fontFamily="Barlow">
              {info.number}
            </text>
            {showTag && (
              <g transform="translate(3.4,-2.6)">
                <rect width={tagW} height={3.4} fill="#000" opacity={0.85} />
                <rect width={0.5} height={3.4} fill={club} />
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
        if (e.type === "goal") {
          const gx = e.team === "home" ? 105 : 0;
          return (
            <g key={e.id}>
              {[0, 0.35, 0.7].map((delay) => (
                <circle key={delay} className="fx-pulse" cx={gx} cy={34} r={10} stroke={color(e)}
                  style={{ ...dur(e), animationDelay: `${delay}s` }} />
              ))}
            </g>
          );
        }
        return null;
      })}

      {frame && (
        <circle
          ref={bind("ball")}
          r={0.75 + Math.min(frame.ball[2], 6) * 0.08}
          fill="#fff"
          stroke="#000"
          strokeWidth={0.15}
        />
      )}
    </svg>
  );
}
