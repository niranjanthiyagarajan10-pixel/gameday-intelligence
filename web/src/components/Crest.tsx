import type { Club } from "../types";

/** A plain shield in the club's colours with its code. The clubs are fictional, so the crest is too. */
export function Crest({ club, size = 44 }: { club: Club; size?: number }) {
  return (
    <svg className="crest" width={size} height={size * 1.15} viewBox="0 0 40 46" role="img" aria-label={`${club.name} crest`}>
      <path d="M2 2H38V24C38 34.5 30 41 20 44.5C10 41 2 34.5 2 24Z" fill={club.primary} />
      <path d="M5 5H35V24C35 32.6 28.6 38 20 41.2C11.4 38 5 32.6 5 24Z" fill="none" stroke={club.secondary} strokeWidth={1.4} />
      <path d="M5 5H35V11H5Z" fill={club.secondary} />
      <text x={20} y={30} textAnchor="middle" fontFamily="Barlow Condensed" fontWeight={800} fontSize={15} fill={club.secondary}>
        {club.short}
      </text>
    </svg>
  );
}
