import type { Roster, Shot } from "../types";
import { shotHref } from "../route";
import { t } from "../i18n";

interface Props {
  shots: Shot[];
  roster: Roster;
  selected?: string;
}

const LINE = { fill: "none", stroke: "rgba(255,255,255,.3)", strokeWidth: 0.3 } as const;

/**
 * Half-pitch shot map with the goal at the top.
 * Shots are drawn in the shooting team's attacking frame, so both teams attack upward.
 * Map: pitch x (52.5 to 105) runs bottom to top, pitch y (0 to 68) runs left to right.
 */
export function ShotMap({ shots, roster, selected }: Props) {
  const toMap = (s: Shot): [number, number] => {
    const xa = s.team === "home" ? s.x : 105 - s.x;
    const ya = s.team === "home" ? s.y : 68 - s.y;
    return [ya, 105 - xa];
  };
  return (
    <svg viewBox="-2 -4 72 58" style={{ width: "100%", display: "block", background: "var(--bg)" }} role="img" aria-label={t("Shot map")}>
      <rect x={0} y={0} width={68} height={52.5} {...LINE} />
      <rect x={(68 - 40.32) / 2} y={0} width={40.32} height={16.5} {...LINE} />
      <rect x={(68 - 18.32) / 2} y={0} width={18.32} height={5.5} {...LINE} />
      <rect x={(68 - 7.32) / 2} y={-1.8} width={7.32} height={1.8} {...LINE} />
      <circle cx={34} cy={11} r={0.35} fill="rgba(255,255,255,.4)" />
      <path d={`M ${34 - 9.15} 52.5 A 9.15 9.15 0 0 1 ${34 + 9.15} 52.5`} {...LINE} />
      <path d="M 26.7 16.5 A 9.15 9.15 0 0 0 41.3 16.5" {...LINE} />
      {shots.map((s) => {
        const [mx, my] = toMap(s);
        const color = roster.clubs[s.team].primary;
        const on = s.event_id === selected;
        const r = on ? 1.6 : 1.1;
        return (
          <a key={s.event_id} href={shotHref(s.event_id)}>
            <title>{`${s.minute}', xG ${s.xg.toFixed(2)}, ${s.outcome.replace("_", " ")}`}</title>
            {s.outcome === "goal" ? (
              <circle cx={mx} cy={my} r={r} fill="none" stroke={on ? "var(--signal)" : color} strokeWidth={on ? 0.6 : 0.45} />
            ) : (
              <g stroke={on ? "var(--signal)" : "#9A9EA6"} strokeWidth={on ? 0.6 : 0.45} strokeLinecap="round">
                <line x1={mx - r} y1={my - r} x2={mx + r} y2={my + r} />
                <line x1={mx - r} y1={my + r} x2={mx + r} y2={my - r} />
              </g>
            )}
            <circle cx={mx} cy={my} r={2.2} fill="transparent" />
          </a>
        );
      })}
    </svg>
  );
}
