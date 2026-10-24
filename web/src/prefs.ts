import { useCallback, useState } from "react";
import type { Analyst, Audience, Card, Side } from "./types";

export type Lang = "en" | "es" | "hi";
export type Metric = "off" | "speed" | "distance" | "xg" | "leverage";
export type Voice = "classic" | "hype" | "stats" | "tactician";

/** What a fan has told us about themselves. Kept in this browser only. */
export interface Prefs {
  clubs: Side[];
  players: string[];
  metric: Metric;
  lang: Lang;
  voice: Voice;
  voiceOn: boolean;
}

export const LANG_LABEL: Record<Lang, string> = { en: "English", es: "Español", hi: "हिन्दी" };
export const METRIC_LABEL: Record<Metric, string> = {
  off: "Off",
  speed: "Top speed",
  distance: "Distance",
  xg: "xG",
  leverage: "Leverage",
};

const KEY = "gameday.prefs";
const DEFAULT: Prefs = { clubs: [], players: [], metric: "off", lang: "en", voice: "classic", voiceOn: false };

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULT, ...(JSON.parse(raw) as Partial<Prefs>) } : DEFAULT;
  } catch {
    return DEFAULT;
  }
}

export function usePrefs(): [Prefs, (change: Partial<Prefs>) => void] {
  const [prefs, setPrefs] = useState<Prefs>(load);
  const update = useCallback((change: Partial<Prefs>) => {
    setPrefs((p) => {
      const next = { ...p, ...change };
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        /* private mode: keep it for this visit only */
      }
      return next;
    });
  }, []);
  return [prefs, update];
}

/** A card's text in the fan's language, falling back to English when no verified translation exists yet. */
export function cardText(card: Card, audience: Audience, lang: Lang): { text: string; lang: Lang } {
  if (lang !== "en") {
    const translated = card.langs?.[lang]?.[audience];
    if (translated) return { text: translated.text, lang };
  }
  return { text: card.cues[audience].text, lang: "en" };
}

/** Is this card about one of the fan's clubs or players? */
export function isMine(card: Card, prefs: Prefs): "club" | "player" | null {
  if (card.moment.players.some((p) => prefs.players.includes(p))) return "player";
  if (card.moment.team && prefs.clubs.includes(card.moment.team)) return "club";
  return null;
}

/** The fan's chosen metric for every player who has one, best first. */
export function metricBoard(metric: Metric, analyst: Analyst | null): { player: string; value: number; text: string }[] {
  if (!analyst || metric === "off") return [];
  const rows: { player: string; value: number; text: string }[] = [];
  if (metric === "speed" || metric === "distance") {
    for (const [player, run] of Object.entries(analyst.runs)) {
      const value = metric === "speed" ? run.top_speed_kmh : run.distance_m / 1000;
      rows.push({ player, value, text: metric === "speed" ? `${value.toFixed(1)} km/h` : `${value.toFixed(1)} km` });
    }
  } else if (metric === "xg") {
    const by = new Map<string, number>();
    for (const s of analyst.shots) by.set(s.player, (by.get(s.player) ?? 0) + s.xg);
    for (const [player, value] of by) rows.push({ player, value, text: `${value.toFixed(2)} xG` });
  } else {
    for (const r of analyst.leverage) rows.push({ player: r.player, value: r.total, text: `${r.total >= 0 ? "+" : ""}${r.total.toFixed(2)} LVG` });
  }
  return rows.sort((a, b) => b.value - a.value);
}
