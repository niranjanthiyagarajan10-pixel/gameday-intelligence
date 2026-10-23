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
  source: string;
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
  analyst: Analyst | null;
  fx: FxEvent[];
}
