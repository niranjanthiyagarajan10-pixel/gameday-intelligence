// Shapes of the messages the API sends. See app/payloads.py.

export type Side = "home" | "away";
export type Audience = "casual" | "analyst";

export interface Club {
  id: string;
  name: string;
  short: string;
  primary: string;
  secondary: string;
  formation: string;
  lineup: string[];
}

export interface PlayerInfo {
  name: string;
  short: string;
  number: number;
  position: "GK" | "DF" | "MF" | "FW";
  side: Side;
}

export interface Roster {
  clubs: Record<Side, Club>;
  players: Record<string, PlayerInfo>;
}

export interface Frame {
  t: number;
  ball: [number, number, number];
  players: [string, number, number, number][]; // id, x, y, speed m/s
}

export interface Stats {
  t: number;
  score: [number, number];
  xg: [number, number];
  xt: [number, number];
  possession: [number, number];
  win_prob: [number, number, number];
  momentum: number;
  control_index: number;
  chaos_index: number;
  box?: BoxRow[]; // the team stats a results page shows
}

/** One row of the match box score. Values are home, away. */
export interface BoxRow {
  key: string;
  label: string;
  values: [number, number];
  unit?: string;
  lower_better?: boolean;
}

export interface Moment {
  moment_id: string;
  minute: number;
  kind: string;
  leverage: number;
  team: Side | null;
  players: string[];
  evidence: Record<string, number | string>;
  event_ids: string[];
  state_ref: string;
}

export interface Cue {
  cue_id: string;
  t_start: number;
  duration_s: number;
  kind: string;
  audience: Audience;
  template: string;
  slots: Record<string, string>;
  verified: boolean;
  evidence_ref: string | null;
  text: string;
}

export interface Card {
  moment: Moment;
  cues: Record<Audience, Cue>;
  hero: { value: string; label: string };
  source: string; // "narrator" once an agent's verified draft replaced the template
  sources?: Record<Audience, string>;
  langs?: Partial<Record<string, Partial<Record<Audience, Cue>>>>; // verified Personalizer translations
}

/** One agent step for the trace panel (agents/desk.py). */
export interface TraceStep {
  moment_id: string;
  audience: string;
  agent: string;
  action: string;
  status: string;
  ms: number;
  detail: string;
  t: number;
}

export interface AgentInfo {
  backend: string;
  model: string;
  live: boolean;
}

export interface Shot {
  event_id: string;
  team: Side;
  player: string;
  minute: number;
  t: number;
  x: number;
  y: number;
  xg: number;
  outcome: string;
  body_part: string;
  speed_kmh: number | null;
  leverage: number;
  shot_type: string;
  distance_m: number;
  angle_deg: number;
  pressure: number;
  defender_m: number | null;
  defender?: string | null; // nearest outfield defender at the shot
  creator: string | null;
  score_before: string;
  wp_if_goal: number;
  wp_if_miss: number;
}

export interface ClipFrame {
  t: number;
  ball: [number, number, number];
  players: [string, number, number, number][];
}

export interface ClipEvent {
  t: number;
  type: string;
  team: Side;
  player: string | null;
  x: number;
  y: number;
  end_x: number | null;
  end_y: number | null;
  outcome: string | null;
}

export interface Clip {
  shot_t: number;
  dt: number;
  frames: ClipFrame[];
  events: ClipEvent[];
}

export interface ShotPageData {
  shot: Shot;
  clip: Clip | null;
  match_id: string;
}

export interface PlayerSummary {
  shots: number;
  goals: number;
  on_target: number;
  xg: number;
  goals_minus_xg: number;
  made_xg: number | null;
  missed_xg: number | null;
  avg_defender_m: number | null;
  distance_km: number;
  top_speed_kmh: number;
  sprints: number;
  leverage: number;
  press_rate: number | null;
  press_attempts: number;
  heatmap: number[][]; // frames per 5 m cell, [x cell][y cell]
  list: Shot[];
}

export interface LeverageRow {
  player: string;
  team: Side;
  total: number;
  shot_making: number;
  creation: number;
  defending: number;
  turnovers: number;
}

export interface PressRow {
  player: string;
  team: Side;
  attempts: number;
  retained: number;
  rate: number | null;
}

export interface Run {
  distance_m: number;
  hsr_m: number;
  sprints: number;
  top_speed_kmh: number;
  speed_kmh: number;
}

export interface ShapeInfo {
  timeline: [number, string][];
  state: string | null;
  window: [number, number, number] | null;
}

export interface NetworkNode {
  player: string;
  x: number;
  y: number;
  passes: number;
}

export interface Network {
  nodes: NetworkNode[];
  edges: { a: string; b: string; n: number }[];
}

export interface Analyst {
  t: number;
  network: Record<Side, Network>;
  shots: Shot[];
  leverage: LeverageRow[];
  press: PressRow[];
  runs: Record<string, Run>;
  shape: Record<Side, ShapeInfo>;
  passes: [number, number];
  completed: [number, number];
  men: [number, number];
}

export type Status = "live" | "catching_up" | "full_time";

// Match Blueprint (app/blueprint.py)

export interface BlueprintShot extends Shot {
  half: 1 | 2;
  score_after: string;
}

export interface Highlight {
  event_id: string;
  team: Side;
  player: string;
  title: string;
  subtitle: string;
  minute: number;
  xg: number;
  outcome: string;
}

export interface Performer {
  key: "goals_above_xg" | "creation" | "defending" | "gravity";
  label: string;
  info: string;
  player: string;
  team: Side;
  value: string;
}

export interface GravityPlayer {
  player: string;
  team: Side;
  overall: number;
  frames: number;
  seconds: number;
  build_up_off_ball: number | null;
  final_third_off_ball: number | null;
  build_up_on_ball: number | null;
  final_third_on_ball: number | null;
  text: string;
}

export interface GravityGrid {
  on_sum: number[][];
  on_n: number[][];
  off_sum: number[][];
  off_n: number[][];
}

export interface MarkingSpot {
  team: Side; // the defending side
  defender: string;
  attacker: string;
  seconds: number;
  defending_s: number;
  share: number;
  shots: number;
  xg: number;
  goals: number;
  received: number;
  tackles: number;
  caption: string;
  text: string;
}

export interface LeverageSpot {
  player: string;
  team: Side;
  total: number;
  shot_making: number;
  creation: number;
  defending: number;
  turnovers: number;
  text: string;
}

export interface BlueprintData {
  status: Status;
  t: number;
  score: [number, number];
  men: [number, number];
  overview: {
    headline: string;
    text: string;
    source?: string; // "recap" when the Recap agent wrote it
    langs?: Partial<Record<string, { headline: string; text: string }>>;
  };
  highlights: Highlight[];
  performers: Performer[];
  shots: BlueprintShot[];
  finishing: Partial<Record<Side, string>>;
  gravity: { players: GravityPlayer[]; maps: Record<Side, GravityGrid>; cell_m: number };
  marking: MarkingSpot[];
  leverage: LeverageSpot[];
}

/** A match event the live pitch animates, stamped with when it arrived (performance.now()). */
export interface FxEvent {
  id: string;
  t: number;
  type: "pass" | "shot" | "tackle" | "interception" | "card" | "goal";
  team: Side;
  player: string | null;
  x: number;
  y: number;
  end_x: number | null;
  end_y: number | null;
  outcome: string | null;
  at: number;
}

export interface MatchState {
  connected: boolean;
  room: string;
  status: Status;
  speed: number;
  paused: boolean;
  halfS: number;
  roster: Roster | null;
  frame: Frame | null;
  stats: Stats | null;
  history: number[][]; // [t, home, draw, away]
  cards: Card[];
  deep: DeepCard[];
  analyst: Analyst | null;
  fx: FxEvent[];
  trace: TraceStep[];
  agents: AgentInfo | null;
}

/** The In-depth Analyst's card: every fifteen minutes and after big moments. */
export interface DeepCard {
  id: string;
  minute: number;
  window: [string, string];
  headline: string;
  text: string;
  source: "agent" | "template";
  langs: Record<string, { headline: string; text: string }>;
  chart: { start: number; home: number }[];
}

/** Explain this moment: one beat of the move behind a shot, found in code, with its verified line. */
export type BeatDraw =
  | { arrow: [number, number, number, number] }
  | { run: [number, number, number, number] }
  | { ring: string | null; tone?: "beaten" }
  | { spot: [number, number] }
  | { shot: [number, number] }
  | { space: string; radius_m: number };

export interface ExplainBeat {
  kind: "won" | "foul_won" | "restart" | "pass" | "carry" | "tackle_beaten" | "shot";
  t: number;
  player: string | null;
  to?: string;
  x: number;
  y: number;
  end_x?: number;
  end_y?: number;
  key?: boolean;
  final?: boolean;
  facts: Record<string, string | number | null>;
  draw: BeatDraw[];
  line: string;
}

export interface Explanation {
  event_id: string;
  shot: Shot;
  clip: Clip;
  beats: ExplainBeat[];
  why: string;
  source: "agent" | "template";
  langs: Record<string, { lines: string[]; why: string }>;
}

/** A clip in the Highlights reel. Every field comes from the shot record, none from a model. */
export interface ReelClip {
  event_id: string;
  minute: number;
  team: "home" | "away";
  player: string;
  player_name: string;
  club: string;
  outcome: string;
  label: string;
  xg: number;
}

/** The Highlights reel: clips picked in code, the Producer's verified intro and outro. */
export interface Reel {
  intro: string;
  outro: string;
  source: "agent" | "template";
  langs: Record<string, { intro: string; outro: string }>;
  score: [number, number];
  status: string;
  minute: number;
  clips: ReelClip[];
}
