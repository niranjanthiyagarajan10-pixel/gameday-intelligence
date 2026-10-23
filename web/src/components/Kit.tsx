import type { Club, PlayerInfo } from "../types";

const KEEPER_SHIRT = "#16181b";

/**
 * The player's shirt in club colours with their number: our stand-in for a player photo.
 * `away` draws the change kit (dark shirt, club-colour number) for use on a club-colour band.
 */
export function Jersey({ club, info, size = 96, away = false }: { club: Club; info: PlayerInfo; size?: number; away?: boolean }) {
  const keeper = info.position === "GK";
  const dark = keeper || away;
  const shirt = dark ? (keeper ? KEEPER_SHIRT : club.secondary) : club.primary;
  const ink = dark ? club.primary : club.secondary;
  return (
    <svg className="jersey" width={size} height={size} viewBox="0 0 100 100" role="img" aria-label={`${info.name}, number ${info.number}`}>
      <path d="M31 9 L42 5 Q50 13 58 5 L69 9 L93 27 L82 45 L72 39 L72 95 L28 95 L28 39 L18 45 L7 27 Z" fill={shirt} />
      <path d="M42 5 Q50 13 58 5" fill="none" stroke={ink} strokeWidth={3} />
      <path d="M18 45 L7 27 M82 45 L93 27" stroke={ink} strokeWidth={3} />
      <text x={50} y={74} textAnchor="middle" fontFamily="Barlow Condensed" fontWeight={800} fontSize={34} fill={ink}>
        {info.number}
      </text>
    </svg>
  );
}

/** A round kit badge with the shirt number, for compact rows. */
export function KitAvatar({ club, info, size = 44 }: { club: Club; info: PlayerInfo; size?: number }) {
  const keeper = info.position === "GK";
  return (
    <svg className="kitavatar" width={size} height={size} viewBox="0 0 44 44" role="img" aria-label={`${info.name}, number ${info.number}`}>
      <circle cx={22} cy={22} r={20.5} fill={keeper ? KEEPER_SHIRT : club.primary} stroke={keeper ? club.primary : club.secondary} strokeWidth={2.5} />
      <text x={22} y={29} textAnchor="middle" fontFamily="Barlow Condensed" fontWeight={800} fontSize={20} fill={keeper ? club.primary : club.secondary}>
        {info.number}
      </text>
    </svg>
  );
}
