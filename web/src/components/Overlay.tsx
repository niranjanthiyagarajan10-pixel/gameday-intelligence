import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { Audience, Card, MatchState } from "../types";
import { Pitch } from "./Pitch";
import { KIND_LABEL, clock } from "../format";
import { Tick } from "../tween";

interface Props {
  state: MatchState;
  bg: boolean;
  audience: Audience;
}

const STAGE_W = 1920;
const STAGE_H = 1080;
const CUE_MIN_MS = 6000; // a lower third stays up long enough to read, even at high speed
const GOAL_FLASH_MS = 8000;
const NO_TAGS = new Set<string>();

/** Fit the 1080p stage to the window, so the same page works in OBS and in a browser tab. */
function useStageScale() {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const fit = () => setScale(Math.min(window.innerWidth / STAGE_W, window.innerHeight / STAGE_H));
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);
  return scale;
}

/** The newest card that arrived while this page was open, and when it arrived. */
function useLatestCard(cards: Card[], ready: boolean) {
  const seen = useRef<number | null>(null);
  const [latest, setLatest] = useState<{ card: Card; at: number } | null>(null);
  useEffect(() => {
    if (!ready) return;
    if (seen.current === null) {
      seen.current = cards.length; // cards from before the page opened are history, not news
      return;
    }
    if (cards.length > seen.current) setLatest({ card: cards[cards.length - 1], at: performance.now() });
    seen.current = cards.length;
  }, [cards, ready]);
  return latest;
}

/**
 * Broadcast graphics package: score bug, win probability strip, goal flash and verified cue
 * lower thirds, on a transparent 1920x1080 stage for OBS or a vision mixer. ?bg=pitch previews it
 * over the live pitch.
 */
export function Overlay({ state, bg, audience }: Props) {
  const scale = useStageScale();
  const latest = useLatestCard(state.cards, state.roster !== null);
  const { roster, stats, frame, analyst } = state;
  if (!roster || !stats) return null;

  const now = performance.now();
  const home = roster.clubs.home;
  const away = roster.clubs.away;
  const men = analyst?.men ?? [11, 11];
  const [h, d, a] = stats.win_prob;
  const half = state.status === "full_time" ? "FT" : stats.t < state.halfS ? "1H" : "2H";

  const goal = [...state.fx].reverse().find((e) => e.type === "goal" && now - e.at < GOAL_FLASH_MS);
  const scorer = goal?.player ? roster.players[goal.player] : undefined;

  const cue = latest ? latest.card.cues[audience] : null;
  const cueLive = cue && latest && (stats.t < cue.t_start + cue.duration_s || now - latest.at < CUE_MIN_MS);
  const m = latest?.card.moment;
  const cueColor = m?.team ? roster.clubs[m.team].primary : "var(--text)";
  const hero = latest?.card.hero;
  const heroClass = hero?.value.startsWith("+") ? "up" : hero?.value.startsWith("-") ? "down" : "";

  return (
    <div className="ov-stage" style={{ transform: `scale(${scale})` }}>
      {bg && (
        <div className="ov-bg">
          <Pitch frame={frame} roster={roster} focus={null} tagged={NO_TAGS} speed={state.speed} fx={state.fx} />
        </div>
      )}

      <div className="ov-bug">
        <div className="ov-row">
          {([home, away] as const).map((club, i) => (
            <div key={club.id} className={`ov-team ${i ? "r" : ""}`}>
              <span className="ov-stripe" style={{ background: club.primary }} />
              <span className="ov-short">{club.short}</span>
              {Array.from({ length: 11 - men[i] }, (_, k) => (
                <span key={k} className="redc" />
              ))}
              <span key={stats.score[i]} className="ov-goals num bump">
                {stats.score[i]}
              </span>
            </div>
          ))}
          <div className="ov-clock num">
            {state.status === "full_time" ? "FT" : clock(stats.t)}
            <small>{state.status === "full_time" ? "" : half}</small>
          </div>
        </div>
        <div className="ov-wp" aria-label="Win probability">
          <div className="ov-bar">
            <i style={{ width: `${h * 100}%`, background: home.primary }} />
            <i style={{ width: `${d * 100}%`, background: "#3a3d44" }} />
            <i style={{ width: `${a * 100}%`, background: away.primary }} />
          </div>
          <div className="ov-wpnums num">
            <span>
              {home.short} <Tick value={h} scale={100} />%
            </span>
            <span>
              Draw <Tick value={d} scale={100} />%
            </span>
            <span>
              {away.short} <Tick value={a} scale={100} />%
            </span>
          </div>
        </div>
        {goal && (
          <div key={goal.id} className="ov-goal" style={{ "--club": roster.clubs[goal.team].primary } as CSSProperties}>
            <b>Goal</b>
            <span>
              {scorer ? scorer.name : roster.clubs[goal.team].name} {Math.floor(goal.t / 60)}&prime;
            </span>
          </div>
        )}
      </div>

      {cueLive && cue && m && hero && (
        <div key={m.moment_id} className="ov-third" style={{ "--club": cueColor } as CSSProperties}>
          <div className="ov-kind">
            <b>{KIND_LABEL[m.kind] ?? m.kind}</b>
            <span className="num">{m.minute}&prime;</span>
          </div>
          <div className="ov-body">
            <p>{cue.text}</p>
            {cue.verified && <span className="ov-verified">Verified from tracking data</span>}
          </div>
          <div className="ov-hero">
            <b className={`num ${heroClass}`}>{hero.value}</b>
            <span>{hero.label}</span>
          </div>
        </div>
      )}

      <div className="ov-mark">Gameday Intelligence. Synthetic match.</div>
    </div>
  );
}
