import type { Audience, MatchState } from "../types";
import { Pitch } from "./Pitch";
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

export function Live({ state, depth, focus }: Props) {
  const { roster, stats, frame, analyst } = state;
  if (!roster || !stats) return null;
  const home = roster.clubs.home;
  const away = roster.clubs.away;

  const latest = state.cards[state.cards.length - 1];
  const latestT = latest ? Number(latest.moment.state_ref.split("@")[1]) : -Infinity;
  const tagged = new Set(stats.t - latestT <= TAG_WINDOW_S && latest ? latest.moment.players : []);
  const frameMs = Math.round(Math.max(100, 200 / state.speed));

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
            <Pitch frame={frame} roster={roster} focus={focus} tagged={tagged} frameMs={frameMs} />
            {focusInfo && (
              <div className="focusbox" style={{ borderLeftColor: roster.clubs[focusInfo.side].primary }}>
                <div className="label">Player focus</div>
                <a className="nm" href={playerHref(focus!)}>
                  #{focusInfo.number} {focusInfo.name}
                </a>
                <div className="fstats">
                  <div>
                    <b className="num">{focusRun ? (focusRun.distance_m / 1000).toFixed(1) : "0.0"}</b>
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
                  <b className="num">{stats.control_index.toFixed(2)}</b>
                </div>
                <div className="k">
                  <span className="label">Chaos index</span>
                  <b className="num">{stats.chaos_index.toFixed(2)}</b>
                </div>
                <div className="k">
                  <span className="label">xG</span>
                  <b className="num">
                    {stats.xg[0].toFixed(2)} <i>/</i> {stats.xg[1].toFixed(2)}
                  </b>
                </div>
                <div className="k">
                  <span className="label">Possession</span>
                  <b className="num">
                    {Math.round(stats.possession[0] * 100)} <i>/</i> {Math.round(stats.possession[1] * 100)}
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
