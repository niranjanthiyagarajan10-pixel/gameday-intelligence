import type { ReactNode } from "react";

type Shape = "shield" | "round" | "pointed" | "octagon" | "heater";
type Mark = (ink: string, field: string) => ReactNode;

/** Outer outlines in a 40 x 46 box, and the same outline inset for the inner rule. */
const SHAPES: Record<Shape, [string, string]> = {
  shield: ["M2 2H38V24C38 34.5 30 41 20 44.5C10 41 2 34.5 2 24Z", "M5 5H35V24C35 32.6 28.6 38 20 41.2C11.4 38 5 32.6 5 24Z"],
  round: ["M20 3.5A19.5 19.5 0 1 1 19.99 3.5Z", "M20 6.5A16.5 16.5 0 1 1 19.99 6.5Z"],
  pointed: ["M2 2H38V19L20 44.5L2 19Z", "M5 5H35V18.2L20 40L5 18.2Z"],
  octagon: ["M12 2H28L38 12V34L28 44H12L2 34V12Z", "M13.3 5H26.7L35 13.3V32.7L26.7 41H13.3L5 32.7V13.3Z"],
  heater: ["M2 3Q20 -1 38 3V20C38 32 29 40 20 44.5C11 40 2 32 2 20Z", "M5 5.8Q20 2.4 35 5.8V20C35 30.4 27.4 37.4 20 41.2C12.6 37.4 5 30.4 5 20Z"],
};

const st = (ink: string, w = 2.2) => ({ stroke: ink, strokeWidth: w, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const });

/** Each club's emblem, drawn for this project. Centred near (20, 20). */
const MARKS: Record<string, Mark> = {
  // Kingsport Rovers, the Anchors
  KR: (ink) => (
    <g {...st(ink)}>
      <circle cx={20} cy={9.6} r={2.3} />
      <path d="M20 12V29.5M14.5 15.5H25.5M11.5 23.5Q12.5 30 20 30Q27.5 30 28.5 23.5" />
      <path d="M9.6 25.6L11.5 23.5L13.6 25.2M30.4 25.6L28.5 23.5L26.4 25.2" />
    </g>
  ),
  // Ashford Vale, the Oaks
  AV: (ink) => (
    <g fill={ink}>
      <circle cx={14.5} cy={16} r={5} /><circle cx={25.5} cy={16} r={5} /><circle cx={20} cy={11.5} r={5.6} /><circle cx={20} cy={19} r={5} />
      <path d="M18.6 21H21.4L22.2 30.5H17.8Z" />
      <path d="M12 30.5H28" {...st(ink, 1.8)} />
    </g>
  ),
  // Northvale Athletic, the Pines
  NA: (ink, field) => (
    <g>
      <path d="M20 7L28.5 18.5H24.5L30.5 27H9.5L15.5 18.5H11.5Z" fill={ink} />
      <path d="M18.8 27H21.2V31H18.8Z" fill={ink} />
      <path d="M20 12.5V25" stroke={field} strokeWidth={1.2} />
    </g>
  ),
  // Bramley Forge, the Anvils
  BF: (ink) => (
    <g fill={ink}>
      <path d="M9 14.5H29.5Q29 19.5 23.5 20.2V23.5H26.5V27.5H13.5V23.5H16.5V20.2Q12 19.5 11.4 17H9Z" />
      <path d="M13 30H27V31.8H13Z" />
      <path d="M24 7L30 10.5M27 8.8L25.3 11.8" {...st(ink, 2)} />
    </g>
  ),
  // Castlemere City, the Towers
  CC: (ink, field) => (
    <g>
      <path d="M12.5 30.5V14H15V10H18V14H22V10H25V14H27.5V30.5Z" fill={ink} />
      <path d="M17.6 30.5V25.5Q20 22.6 22.4 25.5V30.5Z" fill={field} />
      <path d="M18.7 17H21.3V20H18.7Z" fill={field} />
    </g>
  ),
  // Eastwick Albion, the Swifts
  EA: (ink) => (
    <g fill={ink}>
      <path d="M6.5 15.5Q14 16.5 20 21.5Q26 16.5 33.5 15.5Q27 19.5 23.2 24.5L25.5 31L20 26.8L14.5 31L16.8 24.5Q13 19.5 6.5 15.5Z" />
      <circle cx={20} cy={13.6} r={2.6} />
    </g>
  ),
  // Redmarsh United, the Marshmen
  RU: (ink) => (
    <g>
      <g {...st(ink, 1.6)}><path d="M14 31V14M20 31V10M26 31V14M20 22Q15 21 11.5 17M20 25Q25.5 23.5 29 19" /></g>
      <g fill={ink}><rect x={12.4} y={11} width={3.2} height={7} rx={1.6} /><rect x={18.4} y={7} width={3.2} height={7} rx={1.6} /><rect x={24.4} y={11} width={3.2} height={7} rx={1.6} /></g>
      <path d="M10 31.5H30" {...st(ink, 1.8)} />
    </g>
  ),
  // Thornwick Wanderers, the Thorns
  TW: (ink, field) => (
    <g>
      <path d="M20 6L22.6 14.3L30.6 10.2L26.3 18.1L34.5 20.5L26.3 23L30.6 30.8L22.6 26.7L20 35L17.4 26.7L9.4 30.8L13.7 23L5.5 20.5L13.7 18.1L9.4 10.2L17.4 14.3Z" fill={ink} />
      <circle cx={20} cy={20.5} r={3.4} fill={field} />
    </g>
  ),
  // Westholt, the Embers
  WH: (ink, field) => (
    <g>
      <path d="M20 6C26 13 29.5 18 28.5 24C27.6 29.5 24 32 20 32C15.5 32 12 29 12 24C12 20 14.5 17.5 16 14C17.2 17.6 18.4 19 20.2 19.8C21 15.5 20.8 10.5 20 6Z" fill={ink} />
      <path d="M20 21C23 24 23.6 26.4 22.6 28.3C21.6 30 18.4 30 17.4 28.3C16.6 26.6 17.6 24.4 20 21Z" fill={field} />
    </g>
  ),
  // Saltmoor Athletic, the Tide
  SM: (ink) => (
    <g {...st(ink, 2.4)}>
      <path d="M8.5 14Q11.4 10.8 14.3 14T20 14T25.7 14T31.5 14" />
      <path d="M8.5 21Q11.4 17.8 14.3 21T20 21T25.7 21T31.5 21" />
      <path d="M8.5 28Q11.4 24.8 14.3 28T20 28T25.7 28T31.5 28" />
    </g>
  ),
};

const DESIGN: Record<string, Shape> = {
  KR: "shield", AV: "round", NA: "pointed", BF: "octagon", CC: "heater",
  EA: "shield", RU: "heater", TW: "pointed", WH: "octagon", SM: "round",
};

/** A club crest: an outline in the club's colour, an inner rule and an original emblem. The clubs are fictional, so the crests are too. */
export function Crest({ club, size = 44 }: { club: { id?: string; club_id?: string; name: string; short: string; primary: string; secondary: string }; size?: number }) {
  const id = club.id ?? club.club_id ?? club.short;
  const [outer, inner] = SHAPES[DESIGN[id] ?? "shield"];
  const mark = MARKS[id];
  const round = DESIGN[id] === "round";
  return (
    <svg className="crest" width={size} height={size * 1.15} viewBox="0 0 40 46" role="img" aria-label={`${club.name} crest`}>
      <path d={outer} fill={club.primary} />
      <path d={inner} fill="none" stroke={club.secondary} strokeWidth={1.3} />
      {mark ? (
        <>
          {mark(club.secondary, club.primary)}
          {size >= 40 && DESIGN[id] !== "pointed" && (
            <text x={20} y={round ? 38.2 : 37.6} textAnchor="middle" fontFamily="Barlow Condensed" fontWeight={800} fontSize={6.4} letterSpacing={0.6} fill={club.secondary}>
              {club.short}
            </text>
          )}
        </>
      ) : (
        <text x={20} y={30} textAnchor="middle" fontFamily="Barlow Condensed" fontWeight={800} fontSize={15} fill={club.secondary}>
          {club.short}
        </text>
      )}
    </svg>
  );
}
