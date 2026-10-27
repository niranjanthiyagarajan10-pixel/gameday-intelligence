import { useEffect, useMemo, useState } from "react";
import type { Audience, MatchState, Side } from "./types";
import { useMatch } from "./useMatch";
import { Live } from "./components/Live";
import { Analyst } from "./components/Analyst";
import { ShotPage } from "./components/ShotPage";
import { PlayerPage } from "./components/PlayerPage";
import { Overlay } from "./components/Overlay";
import { Crest } from "./components/Crest";
import { Home } from "./components/Home";
import { Blueprint } from "./components/Blueprint";
import { League } from "./components/League";
import { Evals } from "./components/Evals";
import { Preview } from "./components/Preview";
import { Newsdesk } from "./components/Newsdesk";
import { DeepCards } from "./components/DeepCard";
import { TracePanel } from "./components/TracePanel";
import { Favourites } from "./components/Favourites";
import { LANG_LABEL, METRIC_LABEL, usePrefs, type Lang, type Metric } from "./prefs";
import { useChangedSinceMount } from "./tween";
import { clock } from "./format";
import { overlayHref, useRoute } from "./route";
import { setLang, t } from "./i18n";

const SPEEDS = [1, 4, 10, 30];

/** Room from the URL. ?t=55 asks the server for a private replay that starts at minute 55. */
function useRoom(): [string | null, (room: string) => void] {
  const [room, setRoom] = useState<string | null>(() => {
    const p = new URLSearchParams(location.search);
    return p.get("room") ?? (p.get("t") ? null : "main");
  });
  useEffect(() => {
    if (room) return;
    const p = new URLSearchParams(location.search);
    fetch("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_minute: Number(p.get("t")) || 0, speed: Number(p.get("speed")) || 1 }),
    })
      .then((r) => r.json())
      .then((body) => {
        p.delete("t");
        p.set("room", body.room_id);
        history.replaceState(null, "", `?${p.toString()}${location.hash}`);
        setRoom(body.room_id);
      })
      .catch(() => setRoom("main"));
  }, [room]);
  return [room, setRoom];
}

function Scoreboard({ state }: { state: MatchState }) {
  const { roster, stats, analyst, status, halfS } = state;
  const scored = useChangedSinceMount(stats ? stats.score.join(":") : "");
  if (!roster || !stats) return null;
  const men = analyst?.men ?? [11, 11];
  const half = status === "full_time" ? t("Full time") : stats.t < halfS ? t("First half") : t("Second half");
  const team = (side: Side) => {
    const c = roster.clubs[side];
    const reds = 11 - men[side === "home" ? 0 : 1];
    return { c, reds, sub: `${side === "home" ? t("Home") : t("Away")}. ${c.formation}${reds ? `, ${t("down to {n}", { n: 11 - reds })}` : ""}` };
  };
  const h = team("home");
  const a = team("away");
  return (
    <section className="score">
      <div className="team">
        <Crest club={h.c} />
        <div>
          <div className="nm">
            {h.c.name}
            {Array.from({ length: h.reds }, (_, i) => (
              <span key={i} className="redc" />
            ))}
          </div>
          <div className="sub">{h.sub}</div>
        </div>
      </div>
      <div className="mid">
        <div className="sc num">
          <span key={`h${stats.score[0]}`} className={scored ? "bump" : undefined}>{stats.score[0]}</span>
          <i>:</i>
          <span key={`a${stats.score[1]}`} className={scored ? "bump" : undefined}>{stats.score[1]}</span>
        </div>
        <div className="live">
          <span className={`dot ${status === "live" && !state.paused ? "" : "off"}`} />
          <span className="num">{status === "full_time" ? "FT" : clock(stats.t)}</span>
          <span className="label" style={{ marginLeft: 4 }}>
            {status === "catching_up" ? t("Catching up") : state.paused ? t("Paused") : half}
          </span>
        </div>
      </div>
      <div className="team r">
        <div>
          <div className="nm">
            {a.c.name}
            {Array.from({ length: a.reds }, (_, i) => (
              <span key={i} className="redc" />
            ))}
          </div>
          <div className="sub">{a.sub}</div>
        </div>
        <Crest club={a.c} />
      </div>
    </section>
  );
}

export default function App() {
  const [room, setRoom] = useRoom();
  const route = useRoute();
  const { state, control } = useMatch(room ?? "main", () => {
    // That replay has ended or the server restarted: fall back to the main broadcast.
    const p = new URLSearchParams(location.search);
    p.delete("room");
    history.replaceState(null, "", `${location.pathname}${p.toString() ? `?${p}` : ""}${location.hash}`);
    setRoom("main");
  });
  const [tab, setTab] = useState<"live" | "analyst">("live");
  const [depth, setDepth] = useState<Audience>("casual");
  const [prefs, updatePrefs] = usePrefs();
  setLang(prefs.lang); // before any child renders, so every t() reads the fan's language
  useEffect(() => {
    // Tell the room which language this fan watches in: agents write it from now on, and recent cards catch up.
    if (!state.room || prefs.lang === "en") return;
    const want = () => fetch(`/api/rooms/${state.room}/want`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: prefs.lang }),
    }).catch(() => undefined);
    want();
    const timer = window.setInterval(want, 5 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [state.room, prefs.lang]);
  useEffect(() => {
    document.documentElement.lang = prefs.lang;
  }, [prefs.lang]);
  const [focus, setFocus] = useState<string | null>(null);
  const [trace, setTrace] = useState(false);
  const { roster, stats, analyst } = state;

  useEffect(() => {
    if (roster && focus === null && roster.players["KR10"]) setFocus("KR10");
  }, [roster, focus]);

  const onPitch = useMemo(
    () => (state.frame?.players.map((p) => p[0]) ?? []).filter((id) => roster?.players[id]),
    [state.frame, roster],
  );

  const overlay = route.page === "overlay";
  useEffect(() => {
    // The overlay page is composited over video, so the page itself must be see-through.
    document.documentElement.classList.toggle("overlay-mode", overlay);
  }, [overlay]);

  // Start a private room playing one of the matchday's scenarios, then show it live.
  const watch = (scenario: string) => {
    fetch("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_minute: 0, speed: 1, scenario }),
    })
      .then((r) => r.json())
      .then((body) => {
        if (!body.room_id) return;
        const p = new URLSearchParams(location.search);
        p.set("room", body.room_id);
        history.replaceState(null, "", `?${p.toString()}${location.hash}`);
        setTab("live");
        setRoom(body.room_id);
        location.hash = "#/";
      });
  };

  const toggleDepth = () => {
    const next = depth === "casual" ? "analyst" : "casual";
    setDepth(next);
    setTab(next === "analyst" ? "analyst" : "live");
  };

  if (route.page === "overlay") return <Overlay state={state} bg={route.bg} audience={route.audience} />;

  if (!room || !roster || !stats) {
    return (
      <div className="wrap">
        <header className="topbar">
          <div className="brand">
            <b>Gameday</b>
            <span>Intelligence</span>
          </div>
        </header>
        <div className="empty" style={{ padding: 24 }}>
          {room ? t("Connecting to the match feed.") : t("Starting your replay.")}
        </div>
      </div>
    );
  }

  return (
    <div className="wrap">
      <header className="topbar">
        <a className={`brand brand-link ${route.page === "home" || route.page === "squad" ? "on" : ""}`} href="#/home" title={t("About Gameday Intelligence")}>
          <b>Gameday</b>
          <span>Intelligence</span>
        </a>
        <div className="tabs">
          <button className={`tab ${route.page === "preview" ? "on" : ""}`} onClick={() => (location.hash = "#/preview")}>
            {t("Preview")}
          </button>
          <button
            className={`tab ${route.page === "match" && tab === "live" ? "on" : ""}`}
            onClick={() => {
              setTab("live");
              location.hash = "#/";
            }}
          >
            {t("Live Match")}
          </button>
          <button
            className={`tab ${route.page === "match" && tab === "analyst" ? "on" : ""}`}
            onClick={() => {
              setTab("analyst");
              location.hash = "#/";
            }}
          >
            {t("Analyst")}
          </button>
          <button className={`tab ${route.page === "blueprint" ? "on" : ""}`} onClick={() => (location.hash = "#/blueprint")}>
            {t("Blueprint")}
          </button>
          <button className={`tab ${route.page === "news" ? "on" : ""}`} onClick={() => (location.hash = "#/news")}>
            {t("Newsdesk")}
          </button>
          <button className={`tab ${route.page === "league" ? "on" : ""}`} onClick={() => (location.hash = "#/league")}>
            {t("League")}
          </button>
        </div>
        <div className="settings">
          <button className="set" onClick={toggleDepth} title={t("Switch between casual and analyst depth")}>
            <span className="label">{t("Depth")}</span>
            <b>{depth === "casual" ? t("Casual") : t("Analyst")}</b>
          </button>
          <label className="set">
            <span className="label">{t("Language")}</span>
            <select value={prefs.lang} onChange={(e) => updatePrefs({ lang: e.target.value as Lang })}>
              {(Object.keys(LANG_LABEL) as Lang[]).map((l) => (
                <option key={l} value={l}>
                  {LANG_LABEL[l]}
                </option>
              ))}
            </select>
          </label>
          <Favourites roster={roster} prefs={prefs} update={updatePrefs} onPitch={onPitch} />
          <label className={`set ${prefs.metric !== "off" ? "on" : ""}`}>
            <span className="label">{t("Metric mode")}</span>
            <select value={prefs.metric} onChange={(e) => updatePrefs({ metric: e.target.value as Metric })}>
              {(Object.keys(METRIC_LABEL) as Metric[]).map((m) => (
                <option key={m} value={m}>
                  {METRIC_LABEL[m]}
                </option>
              ))}
            </select>
          </label>
          <label className={`set ${focus ? "on" : ""}`}>
            <span className="label">{t("Player focus")}</span>
            <select value={focus ?? ""} onChange={(e) => setFocus(e.target.value || "")}>
              <option value="">{t("Off")}</option>
              {(["home", "away"] as Side[]).map((side) => (
                <optgroup key={side} label={roster.clubs[side].name}>
                  {onPitch
                    .filter((id) => roster.players[id].side === side)
                    .sort((x, y) => roster.players[x].number - roster.players[y].number)
                    .map((id) => (
                      <option key={id} value={id}>
                        #{roster.players[id].number} {roster.players[id].short}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </label>
          <div className="playback" aria-label={t("Playback")}>
            <span className={`conn ${state.connected ? "ok" : ""}`} title={state.connected ? "Connected" : "Reconnecting"} />
            {SPEEDS.map((s) => (
              <button key={s} className={state.speed === s ? "on" : ""} onClick={() => control("speed", s)}>
                {s}x
              </button>
            ))}
            <button onClick={() => control(state.paused ? "resume" : "pause")}>{state.paused ? t("Play") : t("Pause")}</button>
            <button onClick={() => control("restart")}>{t("Restart")}</button>
            <a href={overlayHref(true)} target="_blank" rel="noreferrer" title={t("Broadcast graphics, 1920x1080, transparent without ?bg=pitch")}>
              Overlay &#8599;
            </a>
            <button className={trace ? "on" : ""} onClick={() => setTrace(!trace)} title={t("Every agent step, live")}>
              {t("Trace")}
            </button>
          </div>
        </div>
      </header>

      {!["blueprint", "league", "evals", "preview", "news", "squad", "home"].includes(route.page) && <Scoreboard state={state} />}

      {route.page === "shot" && <ShotPage room={room} id={route.id} roster={roster} />}
      {route.page === "player" && <PlayerPage room={room} id={route.id} roster={roster} />}
      {route.page === "league" && <League onWatch={watch} />}
      {route.page === "evals" && <Evals />}
      {(route.page === "home" || route.page === "squad") && (
        <Home
          state={state}
          toSquad={route.page === "squad"}
          open={(where) => {
            if (where === "live" || where === "analyst") {
              setTab(where);
              location.hash = "#/";
            } else location.hash = where;
          }}
        />
      )}
      {route.page === "preview" && <Preview room={room} lang={prefs.lang} />}
      {route.page === "news" && <Newsdesk lang={prefs.lang} />}
      {route.page === "blueprint" && <Blueprint room={room} roster={roster} halfS={state.halfS} lang={prefs.lang} />}
      {trace && <TracePanel steps={state.trace} agents={state.agents} onClose={() => setTrace(false)} />}
      <main className={route.page === "match" && tab === "live" ? "" : "hidden"}>
        <Live state={state} depth={depth} focus={focus || null} prefs={prefs} update={updatePrefs} onFocus={setFocus} />
      </main>
      <main className={route.page === "match" && tab === "analyst" ? "" : "hidden"}>
        <DeepCards cards={state.deep} roster={roster} lang={prefs.lang} />
        {analyst && <Analyst analyst={analyst} roster={roster} halfS={state.halfS} now={stats.t} />}
      </main>
    </div>
  );
}
