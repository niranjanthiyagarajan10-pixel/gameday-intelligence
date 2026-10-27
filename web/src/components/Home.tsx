import { useEffect, useState } from "react";
import type { MatchState } from "../types";
import { Crest } from "./Crest";
import { SUB, XI } from "./Squad";
import { clock } from "../format";
import { overlayHref } from "../route";
import { t, tx } from "../i18n";

/**
 * Home: the whole product on one page. What it is, how a line gets from the tracking data to a fan,
 * where every feature lives, and how we know it tells the truth. Reached by clicking the brand.
 */

interface Evals { planted?: { caught: number; planted: number; clean: number; clean_passed: number } }

const FLOW = [
  { n: "01", title: tx("Match engine"), body: tx("A synthetic match with full player tracking. Deterministic: the same seed, the same match.") },
  { n: "02", title: tx("Moments"), body: tx("Code finds the goals, chances and swings, and computes xG, win probability and threat.") },
  { n: "03", title: tx("Agents write"), body: tx("Agents on Microsoft Foundry write the story with slots like {xg}. They never type a number or a name.") },
  { n: "04", title: tx("Code fills"), body: tx("Every slot is filled from the engine state, so each number is the real one.") },
  { n: "05", title: tx("VAR checks"), body: tx("The Verifier checks every slot and every claim. A line the data cannot back goes back to the agent.") },
  { n: "06", title: tx("You"), body: tx("Your club, your player, casual or analyst depth, eight languages, read aloud if you like.") },
];

const FEATURES: { title: string; body: string; go: string; tag: string }[] = [
  { title: tx("Live Match"), body: tx("The 3D pitch, key moments as they happen, win probability, Catch me up and Ask the match."), go: "live", tag: tx("Start here") },
  { title: tx("Match Theatre"), body: tx("The 3D pitch full screen. Explain this moment replays how a goal was made, beat by beat, with voice. Plus the Highlights reel."), go: "live", tag: tx("One more thing") },
  { title: tx("Analyst"), body: tx("Every fifteen minutes, why the match is going the way it is: threat, shape, gravity and pressure."), go: "analyst", tag: tx("Analyst depth") },
  { title: tx("Preview"), body: tx("Before kick-off: form, head to head, the forecast and the players to watch."), go: "#/preview", tag: tx("Before") },
  { title: tx("Blueprint"), body: tx("After the match: the report, what decided it and what each club should watch next."), go: "#/blueprint", tag: tx("After") },
  { title: tx("Newsdesk"), body: tx("A newspaper report for every fixture of the matchday."), go: "#/news", tag: tx("Around the league") },
  { title: tx("League"), body: tx("The table and every fixture. Watch any match from kick-off."), go: "#/league", tag: tx("Around the league") },
  { title: tx("The Squad"), body: tx("Meet the agents: eleven players and a Super-Sub, each marking the fan problem it solves."), go: "#/squad", tag: tx("The team") },
  { title: tx("Broadcast overlay"), body: tx("The same verified cards as 1920x1080 graphics, ready to lay over a match feed."), go: "overlay", tag: tx("For broadcasters") },
];

const STACK = ["Microsoft Foundry", "Microsoft Agent Framework", "Model Context Protocol", "Azure AI Speech", "Azure Container Apps", "OpenTelemetry"];

/** A draft line, filled by code, then judged by VAR. Two examples: one passes, one is sent back. */
const DEMO = [
  {
    draft: [["", "{player}"], [" finishes from ", ""], ["", "{dist}"], [" metres. A chance scored about ", ""], ["", "{n}"], [" times in 100.", ""]],
    fill: { "{player}": "Quinn Duarte", "{dist}": "14", "{n}": "31" } as Record<string, string>,
    pass: true,
    why: tx("Every slot matches the engine. Every claim is backed."),
  },
  {
    draft: [["A ", ""], ["clear chance", "!"], [" for ", ""], ["", "{player}"], [", scored about ", ""], ["", "{n}"], [" times in 100.", ""]],
    fill: { "{player}": "Zane Bellweather", "{n}": "4" } as Record<string, string>,
    pass: false,
    why: tx("4 in 100 is not a clear chance."),
  },
];

function SlotDemo() {
  const [step, setStep] = useState(0); // 0 draft, 1 filled, 2 judged; two examples in turn
  useEffect(() => {
    const id = window.setInterval(() => setStep((s) => (s + 1) % 6), 1700);
    return () => window.clearInterval(id);
  }, []);
  const ex = DEMO[Math.floor(step / 3)];
  const phase = step % 3;
  return (
    <div className="hm-demo" aria-live="polite">
      <div className="hm-demo-steps">
        {[t("Agent writes"), t("Code fills"), t("VAR checks")].map((s, i) => (
          <span key={s} className={i <= phase ? "on" : ""}>
            {i + 1}. {s}
          </span>
        ))}
      </div>
      <p className="hm-demo-line">
        {ex.draft.map(([text, slot], i) => {
          if (slot === "!") return <em key={i} className={phase === 2 && !ex.pass ? "bad" : ""}>{text}</em>;
          if (!slot) return <span key={i}>{text}</span>;
          return (
            <code key={`${i}-${phase > 0}`} className={phase > 0 ? "filled" : ""}>
              {phase > 0 ? ex.fill[slot] : slot}
            </code>
          );
        })}
      </p>
      <div className={`hm-demo-verdict ${phase === 2 ? (ex.pass ? "ok" : "no") : ""}`}>
        {phase < 2 ? <span>{t("Waiting for VAR")}</span> : (
          <>
            <b>{ex.pass ? t("Checked") : t("Sent back")}</b>
            <span>{t(ex.why)}</span>
          </>
        )}
      </div>
    </div>
  );
}

function LiveTile({ state, onOpen }: { state: MatchState; onOpen: () => void }) {
  const { roster, stats, status } = state;
  if (!roster || !stats) return null;
  const [h, d, a] = stats.win_prob;
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  return (
    <button className="hm-live" onClick={onOpen}>
      <div className="hm-live-top">
        <span className={`dot ${status === "live" && !state.paused ? "" : "off"}`} />
        <span className="label">{status === "full_time" ? t("Full time") : t("Live now")}</span>
        <span className="num hm-live-clock">{status === "full_time" ? "FT" : clock(stats.t)}</span>
      </div>
      <div className="hm-live-score">
        <div>
          <Crest club={roster.clubs.home} size={52} />
          <b>{roster.clubs.home.short}</b>
        </div>
        <span className="num">
          {stats.score[0]}
          <i>:</i>
          {stats.score[1]}
        </span>
        <div>
          <Crest club={roster.clubs.away} size={52} />
          <b>{roster.clubs.away.short}</b>
        </div>
      </div>
      <div className="hm-live-wp">
        <i style={{ flex: h }} className="h" />
        <i style={{ flex: d }} className="d" />
        <i style={{ flex: a }} className="a" />
      </div>
      <div className="hm-live-wpn">
        <span>{pct(h)}</span>
        <span className="label">{t("Win probability")}</span>
        <span>{pct(a)}</span>
      </div>
      <span className="hm-live-go">{t("Watch live")} &rarr;</span>
    </button>
  );
}

export function Home({ state, open }: { state: MatchState; open: (where: string) => void }) {
  const [evals, setEvals] = useState<Evals | null>(null);
  useEffect(() => {
    fetch("/api/evals").then((r) => (r.ok ? r.json() : null)).then(setEvals).catch(() => undefined);
  }, []);
  const p = evals?.planted;
  const go = (where: string) => {
    if (where === "overlay") window.open(overlayHref(true), "_blank", "noreferrer");
    else open(where);
  };

  return (
    <div className="home">
      <section className="hm-hero">
        <div className="hm-hero-text">
          <span className="hm-kicker">{t("A live match companion")}</span>
          <h1>{t("Every match tells a story.")}</h1>
          <p className="hm-lede">
            {t("Gameday Intelligence turns live tracking data into verified, explainable match stories for every fan. A squad of AI agents writes them. A referee made of code checks every one.")}
          </p>
          <div className="hm-cta">
            <button className="hm-btn main" onClick={() => go("live")}>{t("Watch live")}</button>
            <button className="hm-btn" onClick={() => go("#/squad")}>{t("Meet the Squad")}</button>
          </div>
        </div>
        <LiveTile state={state} onOpen={() => go("live")} />
      </section>

      <section className="hm-numbers">
        <div><b className="num">11<small>+1</small></b><span>{t("AI agents on Microsoft Foundry")}</span></div>
        <div><b className="num">15</b><span>{t("MCP tools over the match")}</span></div>
        <div><b className="num">8</b><span>{t("languages")}</span></div>
        <div><b className="num">{p ? `${p.caught.toLocaleString("en-GB")}/${p.planted.toLocaleString("en-GB")}` : "..."}</b><span>{t("planted errors caught by VAR")}</span></div>
        <div className="zero"><b className="num">0</b><span>{t("numbers typed by an AI")}</span></div>
      </section>

      <section className="hm-sec">
        <header className="hm-sec-h">
          <span className="hm-kicker">{t("How it works")}</span>
          <h2>{t("From tracking data to your screen")}</h2>
        </header>
        <ol className="hm-flow">
          {FLOW.map((f) => (
            <li key={f.n} className={f.n === "05" ? "var" : ""}>
              <span className="hm-flow-n num">{f.n}</span>
              <b>{t(f.title)}</b>
              <p>{t(f.body)}</p>
            </li>
          ))}
        </ol>
        <SlotDemo />
      </section>

      <section className="hm-sec">
        <header className="hm-sec-h">
          <span className="hm-kicker">{t("The Squad")}</span>
          <h2>{t("Eleven agents. One Super-Sub. One referee.")}</h2>
        </header>
        <div className="hm-squad">
          {[...XI, SUB].map((a) => (
            <a key={a.no} href="#/squad" className="hm-shirt">
              <b className="num">{a.no}</b>
              <span>{t(a.nick)}</span>
              <small>{a.agent}</small>
            </a>
          ))}
          <a href="#/squad" className="hm-shirt ref">
            <b>VAR</b>
            <span>{t("The referee")}</span>
            <small>{t("Code, not AI")}</small>
          </a>
        </div>
      </section>

      <section className="hm-sec">
        <header className="hm-sec-h">
          <span className="hm-kicker">{t("Where to go")}</span>
          <h2>{t("Everything in the product")}</h2>
        </header>
        <div className="hm-tiles">
          {FEATURES.map((f, i) => (
            <button key={f.title} className="hm-tile" onClick={() => go(f.go)}>
              <span className="hm-tile-n num">{String(i + 1).padStart(2, "0")}</span>
              <span className="hm-tile-tag">{t(f.tag)}</span>
              <b>{t(f.title)}</b>
              <p>{t(f.body)}</p>
              <span className="hm-tile-go">{t("Open")} &rarr;</span>
            </button>
          ))}
        </div>
      </section>

      <section className="hm-sec hm-trust">
        <div>
          <span className="hm-kicker">{t("Why you can trust it")}</span>
          <h2>{t("Every number true.")}</h2>
          <p>
            {t("We planted errors into agent lines on purpose: wrong numbers, wrong names, claims the data cannot back. VAR has to catch every one, and let every clean line through.")}
          </p>
          <a href="#/evals" className="hm-link">{t("See the full eval report")} &rarr;</a>
        </div>
        <div className="hm-trust-nums">
          <div><b className="num">{p ? `${Math.round((p.caught / p.planted) * 100)}%` : "..."}</b><span>{t("planted errors caught")}</span></div>
          <div><b className="num">{p ? `${Math.round((p.clean_passed / p.clean) * 100)}%` : "..."}</b><span>{t("clean lines let through")}</span></div>
          <div><b className="num">8s</b><span>{t("the longest any AI call may take. Then a checked template takes over.")}</span></div>
        </div>
      </section>

      <section className="hm-sec hm-stack">
        <span className="hm-kicker">{t("Built on")}</span>
        <div>
          {STACK.map((s) => (
            <span key={s}>{s}</span>
          ))}
        </div>
        <p className="hm-note">{t("Synthetic data only. Every club, player and league here is fictional.")}</p>
      </section>
    </div>
  );
}
