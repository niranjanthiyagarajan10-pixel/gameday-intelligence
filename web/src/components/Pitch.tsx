import { useEffect, useRef, useState } from "react";
import type { Frame, Roster } from "../types";

interface Props {
  frame: Frame | null;
  roster: Roster;
  focus: string | null;
  tagged: Set<string>;
  frameMs: number;
}

const LINE = { fill: "none", stroke: "rgba(255,255,255,.25)", strokeWidth: 0.3 } as const;
const SPOT = "rgba(255,255,255,.35)";
const FOCUS_TRAIL_S = 12;

function Markings() {
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

export function Pitch({ frame, roster, focus, tagged, frameMs }: Props) {
  const ballTrail = useRef<[number, number][]>([]);
  const [focusTrail, setFocusTrail] = useState<[number, number, number][]>([]);

  useEffect(() => {
    if (!frame) return;
    ballTrail.current = [...ballTrail.current, [frame.ball[0], frame.ball[1]] as [number, number]].slice(-4);
    if (focus) {
      const me = frame.players.find((p) => p[0] === focus);
      setFocusTrail((prev) => {
        const kept = prev.filter((p) => frame.t - p[2] <= FOCUS_TRAIL_S && p[2] <= frame.t);
        return me ? [...kept, [me[1], me[2], frame.t]] : kept;
      });
    }
  }, [frame, focus]);

  useEffect(() => setFocusTrail([]), [focus]);

  const focusColor = focus ? roster.clubs[roster.players[focus]?.side ?? "home"].primary : "";

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
      {frame?.players.map(([id, x, y, speed]) => {
        const info = roster.players[id];
        if (!info) return null;
        const color = roster.clubs[info.side].primary;
        const isFocus = id === focus;
        const dim = focus !== null && !isFocus && !tagged.has(id);
        const showTag = isFocus || tagged.has(id);
        const tag = isFocus ? `${info.short.toUpperCase()}  ${(speed * 3.6).toFixed(1)} KM/H` : info.short.toUpperCase();
        const tagW = tag.length * 0.95 + 2;
        return (
          <g
            key={id}
            className="pl"
            style={{ transform: `translate(${x}px, ${y}px)`, transitionDuration: `${frameMs}ms`, opacity: dim ? 0.3 : 1 }}
          >
            {isFocus && <circle r={3} fill="none" stroke="var(--signal)" strokeWidth={0.35} />}
            <circle r={isFocus ? 1.9 : 1.55} fill={color} />
            <text y={0.62} textAnchor="middle" fontSize={1.7} fontWeight={700} fill="#000" fontFamily="Barlow">
              {info.number}
            </text>
            {showTag && (
              <g transform="translate(3.4,-2.6)">
                <rect width={tagW} height={3.4} fill="#000" opacity={0.85} />
                <rect width={0.5} height={3.4} fill={color} />
                <text x={1.2} y={2.4} fontSize={2} fontWeight={700} fill="#F4F4F1" fontFamily="Barlow Condensed">
                  {tag}
                </text>
              </g>
            )}
          </g>
        );
      })}
      {frame && (
        <g>
          {ballTrail.current.length > 1 && (
            <polyline
              points={ballTrail.current.map((p) => `${p[0]},${p[1]}`).join(" ")}
              fill="none"
              stroke="rgba(255,255,255,.4)"
              strokeWidth={0.35}
              strokeDasharray="0.8 0.8"
            />
          )}
          <circle
            className="pl"
            r={0.75 + Math.min(frame.ball[2], 6) * 0.08}
            fill="#fff"
            style={{ transform: `translate(${frame.ball[0]}px, ${frame.ball[1]}px)`, transitionDuration: `${frameMs}ms` }}
          />
        </g>
      )}
    </svg>
  );
}
