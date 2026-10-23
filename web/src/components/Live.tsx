import type { CSSProperties } from "react";
import type { Audience, FxEvent, MatchState, Roster } from "../types";
import { Pitch } from "./Pitch";
import { Tick } from "../tween";
import { WinProbability } from "./WinProbability";
import { MomentCard } from "./MomentCard";
import { signed } from "../format";
import { playerHref } from "../route";

interface Props {
  state: MatchState;
  depth: Audience;
  focus: string | null;
}

const TAG_WINDOW_S = 10;
const GOAL_BANNER_MS = 4200;

/** Broadcast GOAL slab over the pitch: club colour wipe, scorer, minute and the new score. */
function GoalBanner({ fx, roster, score }: { fx: FxEvent[]; roster: Roster; score: [number, number] }) {
  const now = performance.now();
  const goal = [...fx].reverse().find((e) => e.type === "goal" && now - e.at < GOAL_BANNER_MS);
  if (!goal) return null;
  const club = roster.clubs[goal.team];
  const scorer = goal.player ? roster.players[goal.player] : undefined;
  return (
    <div key={goal.id} className="goalbanner" style={{ "--club": club.primary } as CSSProperties} role="status">
      <div className="gb-slab">
        <span className="gb-word">Goal</span>
      </div>
      <div className="gb-info">
        <b>{scorer ? `#${scorer.number} ${scorer.name}` : club.name}</b>
        <span>
          {club.name} {Math.floor(goal.t / 60)}&prime;
          <em className="num">
            {roster.clubs.home.short} {score[0]} <i>:</i> {score[1]} {roster.clubs.away.short}
          </em>
        </span>
      </div>
    </div>
  );
}

export function Live({ state, depth, focus }: Props) {
  const { roster, stats, frame, analyst } = state;
  if (!roster || !stats) return null;
  const home = roster.clubs.home;
  const away = roster.clubs.away;

  const latest = state.cards[state.cards.length - 1];
  const latestT = latest ? Number(latest.moment.state_ref.split("@")[1]) : -Infinity;
  const tagged = new Set(stats.t - latestT <= TAG_WINDOW_S && latest ? latest.moment.players : []);

  const focusInfo = focus ? roster.players[focus] : null;
  const focusRun = focus ? analyst?.runs[focus] : undefined;
  const focusLev = focus ? analyst?.leverage.find((r) => r.player === focus)?.total : undefined;
  const liveSpeed = focus ? frame?.players.find((p) => p[0] === focus)?.[3] : undefined;

  const mom = stats.momentum;
  const cards = [...state.cards].reverse().slice(0, 12);

  return (
    <div className="grid">
      <div className="c8 col">
        <div className="panel">
          <div className="ph">
            <h3>Live pitch</h3>
            <div className="legend">
              <span>
                <i className="sw" style={{ background: home.primary }} />
                {home.name}
              </span>
              <span>
                <i className="sw" style={{ background: away.primary }} />
                {away.name}
              </span>
              {focusInfo && (
                <span className="label" style={{ color: "var(--signal)" }}>
                  Focus: #{focusInfo.number} {focusInfo.short}
                </span>
              )}
            </div>
          </div>
          <div className="pitchwrap">
            <Pitch frame={frame} roster={roster} focus={focus} tagged={tagged} speed={state.speed} fx={state.fx} />
            <GoalBanner fx={state.fx} roster={roster} score={stats.score} />
            {focusInfo && (
              <div className="focusbox" style={{ borderLeftColor: roster.clubs[focusInfo.side].primary }}>
                <div className="label">Player focus</div>
                <a className="nm" href={playerHref(focus!)}>
                  #{focusInfo.number} {focusInfo.name}
                </a>
                <div className="fstats">
                  <div>
                    <b className="num"><Tick value={focusRun ? focusRun.distance_m / 1000 : 0} digits={1} /></b>
                    <span className="label">km run</span>
                  </div>
                  <div>
                    <b className="num">{liveSpeed !== undefined ? (liveSpeed * 3.6).toFixed(1) : "-"}</b>
                    <span className="label">km/h now</span>
                  </div>
                  <div>
                    <b className="num">{focusRun ? focusRun.top_speed_kmh.toFixed(1) : "-"}</b>
                    <span className="label">top km/h</span>
                  </div>
                  <div>
                    <b className="num">{focusLev !== undefined ? signed(focusLev) : "+0.00"}</b>
                    <span className="label">leverage</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="grid" style={{ marginTop: 0 }}>
          <div className="panel c7">
            <div className="ph">
              <h3>Win probability</h3>
              <span className="label">Live Poisson model</span>
            </div>
            <div className="pb">
              <WinProbability stats={stats} history={state.history} cards={state.cards} roster={roster} halfS={state.halfS} />
            </div>
          </div>
          <div className="panel c5">
            <div className="ph">
              <h3>Momentum</h3>
              <span className="label">Threat added, recent play</span>
            </div>
            <div className="pb">
              <div className="mom">
                <div
                  className="fill"
                  style={{
                    left: mom >= 0 ? "50%" : `${50 + mom * 50}%`,
                    width: `${Math.abs(mom) * 50}%`,
                    background: mom >= 0 ? home.primary : away.primary,
                  }}
                />
                <div className="ctr" />
              </div>
              <div className="ends">
                <span className="label">{away.short}</span>
                <span className="label">{home.short}</span>
              </div>
              <div className="kv">
                <div className="k">
                  <span className="label">Control index</span>
                  <b className="num"><Tick value={stats.control_index} digits={2} /></b>
                </div>
                <div className="k">
                  <span className="label">Chaos index</span>
                  <b className="num"><Tick value={stats.chaos_index} digits={2} /></b>
                </div>
                <div className="k">
                  <span className="label">xG</span>
                  <b className="num">
                    <Tick value={stats.xg[0]} digits={2} /> <i>/</i> <Tick value={stats.xg[1]} digits={2} />
                  </b>
                </div>
                <div className="k">
                  <span className="label">Possession</span>
                  <b className="num">
                    <Tick value={stats.possession[0]} scale={100} /> <i>/</i> <Tick value={stats.possession[1]} scale={100} />
                  </b>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="c4 col">
        <div className="panel">
          <div className="ph">
            <h3>Key moments</h3>
            <span className="label">{state.cards.length} so far</span>
          </div>
          <div className="feed">
            {cards.length === 0 && <div className="empty">Key moments appear here as they happen.</div>}
            {cards.map((card, i) => (
              <MomentCard key={card.moment.moment_id} card={card} roster={roster} depth={depth} open={i === 0 && depth === "analyst"} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
