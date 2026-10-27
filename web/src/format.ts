import type { Roster, Side } from "./types";
import { labels } from "./i18n";

export const pct = (p: number) => `${Math.round(p * 100)}`;

export const signed = (v: number, digits = 2) => `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;

export function clock(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function playerName(roster: Roster | null, id: string, short = false): string {
  const p = roster?.players[id];
  if (!p) return id;
  return short ? p.short : p.name;
}

export function sideColor(roster: Roster | null, side: Side | null | undefined): string {
  if (!roster || !side) return "var(--text-muted)";
  return roster.clubs[side].primary;
}

export const KIND_LABEL: Record<string, string> = labels({
  goal: "Goal",
  low_xg_goal: "Goal against the odds",
  red_card: "Red card",
  big_chance: "Big chance",
  leverage_swing: "Key moment",
  top_speed: "Top speed",
  control_flip: "Control",
  shape_change: "Shape change",
});

export const SHAPE_LABEL: Record<string, string> = labels({
  low_block: "Low block",
  mid_block: "Mid block",
  high_press: "High press",
});

/** Human labels and formats for evidence keys shown in the evidence drawer. */
export function evidenceRows(evidence: Record<string, number | string>, roster: Roster | null): [string, string][] {
  const labels: Record<string, string> = {
    wp_before: "Win probability before",
    wp_after: "Win probability after",
    wp_opposite: "If it had gone the other way",
    wp_if_scored: "Win probability if scored",
    xg: "Expected goals (xG)",
    leverage: "Leverage",
    score: "Score",
    player: "Player",
    action: "Action",
    outcome: "Outcome",
    speed_kmh: "Speed (km/h)",
    speed_ms: "Speed (m/s)",
    line_height_m: "Line height (m)",
    compactness_m2: "Compactness (sq m)",
    pressers: "Pressers near the ball",
    from: "From",
    to: "To",
    now_in_control: "In control",
    control_index: "Control index",
    chaos_index: "Chaos index",
  };
  return Object.entries(evidence).map(([k, v]) => {
    let value = String(v);
    if (k.startsWith("wp_")) value = `${pct(Number(v))}%`;
    else if (k === "leverage") value = signed(Number(v));
    else if (k === "player") value = playerName(roster, String(v));
    else if (k === "from" || k === "to") value = SHAPE_LABEL[String(v)] ?? String(v);
    else if (k === "action") value = String(v).replace("_", " ");
    return [labels[k] ?? k, value];
  });
}
