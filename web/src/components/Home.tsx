import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import type { MatchState } from "../types";
import { Crest } from "./Crest";
import { Squad } from "./Squad";
import { clock } from "../format";
import { overlayHref } from "../route";
import { t, tx } from "../i18n";

/**
 * Home: the whole product as a run of scenes, one idea per screen, in the spirit of a product launch
 * page. The live score, the headline numbers, how a line is made and checked, the Squad on its pitch,
 * every feature, and why it can be trusted. Reached by clicking the brand.
 */

interface Evals { planted?: { caught: number; planted: number; clean: number; clean_passed: number } }

const FEATURES: { title: string; body: string; go: string; tag: string; big?: boolean }[] = [
  { title: tx("Live Match"), body: tx("The 3D pitch, every key moment as it happens, Catch me up and Ask the match."), go: "live", tag: tx("During"), big: true },
  { title: tx("Match Theatre"), body: tx("Pick any goal. See how it was made, beat by beat, in 3D, with voice."), go: "live", tag: tx("One more thing"), big: true },
  { title: tx("Analyst"), body: tx("Why the match is going the way it is."), go: "analyst", tag: tx("Go deeper") },
  { title: tx("Preview"), body: tx("Form, head to head and players to watch."), go: "#/preview", tag: tx("Before") },
  { title: tx("Blueprint"), body: tx("The report, and what decided it."), go: "#/blueprint", tag: tx("After") },
  { title: tx("Newsdesk"), body: tx("A report for every fixture."), go: "#/news", tag: tx("Around the league") },
  { title: tx("League"), body: tx("The table. Watch any match."), go: "#/league", tag: tx("Around the league") },
  { title: tx("Broadcast overlay"), body: tx("The same cards as TV graphics."), go: "overlay", tag: tx("For broadcasters") },
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

/** Fades each .rv element up as it scrolls into view. */
function useReveal(root: RefObject<HTMLElement>) {
  useEffect(() => {
    const els = root.current?.querySelectorAll(".rv");
    if (!els) return;
    if (!("IntersectionObserver" in window)) {
      els.forEach((e) => e.classList.add("in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add("in");
          io.unobserve(e.target);
        }
      }),
      { threshold: 0.12 },
    );
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [root]);
}

function SlotDemo() {
  const [step, setStep] = useState(0); // 0 draft, 1 filled, 2 judged; two examples in turn
  useEffect(() => {
    const id = window.setInterval(() => setStep((s) => (s + 1) % 6), 1800);
    return () => window.clearInterval(id);
  }, []);
  const ex = DEMO[Math.floor(step / 3)];
  const phase = step % 3;
  return (
    <div className="hm-demo" aria-live="polite">
      <div className="hm-demo-steps">
        {[t("Agent writes"), t("Code fills"), t("VAR checks")].map((s, i) => (
          <span key={s} className={i === phase ? "on" : i < phase ? "done" : ""}>
            {s}
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
    <button className="hm-live rv" onClick={onOpen}>
      <div className="hm-live-top">
        <span className={`dot ${status === "live" && !state.paused ? "" : "off"}`} />
        <span className="label">{status === "full_time" ? t("Full time") : t("Live now")}</span>
        <span className="num hm-live-clock">{status === "full_time" ? "FT" : clock(stats.t)}</span>
      </div>
      <div className="hm-live-score">
        <div>
          <Crest club={roster.clubs.home} size={64} />
          <b>{roster.clubs.home.name}</b>
        </div>
        <span className="num">
          {stats.score[0]}
          <i>:</i>
          {stats.score[1]}
        </span>
        <div>
          <Crest club={roster.clubs.away} size={64} />
          <b>{roster.clubs.away.name}</b>
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

export function Home({ state, open, toSquad }: { state: MatchState; open: (where: string) => void; toSquad?: boolean }) {
  const [evals, setEvals] = useState<Evals | null>(null);
  const root = useRef<HTMLDivElement>(null);
  useReveal(root);
  useEffect(() => {
    fetch("/api/evals").then((r) => (r.ok ? r.json() : null)).then(setEvals).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (toSquad) window.setTimeout(() => document.getElementById("squad")?.scrollIntoView({ behavior: "smooth" }), 50);
  }, [toSquad]);
  const p = evals?.planted;
  const fmt = (n: number) => n.toLocaleString("en-GB");
  const go = (where: string) => {
    if (where === "overlay") window.open(overlayHref(true), "_blank", "noreferrer");
    else if (where === "squad") document.getElementById("squad")?.scrollIntoView({ behavior: "smooth" });
    else open(where);
  };

  return (
    <div className="home" ref={root}>
      <section className="hm-scene hm-hero">
        <span className="hm-eyebrow rv">Gameday Intelligence</span>
        <h1 className="rv">{t("Every match tells a story.")}</h1>
        <p className="hm-sub rv">{t("Now every fan can read it.")}</p>
        <div className="hm-cta rv">
          <button className="hm-btn main" onClick={() => go("live")}>{t("Watch live")}</button>
          <button className="hm-btn" onClick={() => go("squad")}>{t("Meet the Squad")}</button>
        </div>
        <LiveTile state={state} onOpen={() => go("live")} />
      </section>

      <section className="hm-scene">
        <h2 className="hm-h rv">{t("Get the highlights.")}</h2>
        <div className="hm-bento">
          <div className="hm-stat rv"><b className="num">11<small>+1</small></b><span>{t("AI agents on Microsoft Foundry")}</span></div>
          <div className="hm-stat rv"><b className="num">8</b><span>{t("languages")}</span></div>
          <div className="hm-stat rv"><b className="num">15</b><span>{t("MCP tools over the match")}</span></div>
          <div className="hm-stat hl rv"><b className="num">0</b><span>{t("numbers typed by an AI")}</span></div>
        </div>
      </section>

      <section className="hm-scene">
        <h2 className="hm-h hm-stack-h rv">
          <span>{t("Agents write.")}</span>
          <span>{t("Code fills.")}</span>
          <span className="sig">{t("VAR checks.")}</span>
        </h2>
        <p className="hm-copy rv">
          {t("Agents never type a number or a name.")}{" "}
          <b>{t("Code fills every one from the match engine, then VAR checks each claim before a fan sees it.")}</b>
        </p>
        <div className="hm-wide rv"><SlotDemo /></div>
      </section>

      <section className="hm-scene hm-squad-scene" id="squad">
        <h2 className="hm-h rv">{t("Meet the Gameday XI.")}</h2>
        <p className="hm-copy rv">
          {t("Eleven AI agents and a Super-Sub, one fan problem each.")}{" "}
          <b>{t("Hover a player to see what it does. Press Kick off to watch them win.")}</b>
        </p>
        <div className="hm-full rv">
          <Squad trace={state.trace} embedded />
        </div>
      </section>

      <section className="hm-scene">
        <h2 className="hm-h rv">{t("Before. During. After.")}</h2>
        <p className="hm-copy rv">
          <b>{t("Everything a fan needs, in one place.")}</b> {t("Pick a part to open it.")}
        </p>
        <div className="hm-tiles">
          {FEATURES.map((f) => (
            <button key={f.title} className={`hm-tile rv ${f.big ? "big" : ""}`} onClick={() => go(f.go)}>
              <span className="hm-tile-tag">{t(f.tag)}</span>
              <b>{t(f.title)}</b>
              <p>{t(f.body)}</p>
              <span className="hm-tile-go">{t("Open")} &rarr;</span>
            </button>
          ))}
        </div>
      </section>

      <section className="hm-scene hm-trust">
        <span className="hm-eyebrow rv">{t("Why you can trust it")}</span>
        <div className="hm-giant num rv">
          {p ? fmt(p.caught) : "..."}
          <small>/{p ? fmt(p.planted) : "..."}</small>
        </div>
        <p className="hm-copy rv">
          {t("We planted errors on purpose: wrong numbers, wrong names, claims the data cannot back.")}{" "}
          <b>{t("VAR caught every one.")}</b>
        </p>
        <div className="hm-trust-row rv">
          <div><b className="num">{p ? `${Math.round((p.clean_passed / p.clean) * 100)}%` : "..."}</b><span>{t("clean lines let through")}</span></div>
          <div><b className="num">8s</b><span>{t("longest wait, then a checked template")}</span></div>
          <div><b className="num">0</b><span>{t("errors shown to a fan")}</span></div>
        </div>
        <a href="#/evals" className="hm-link rv">{t("See the full eval report")} &rarr;</a>
      </section>

      <section className="hm-scene hm-built">
        <span className="hm-eyebrow rv">{t("Built on")}</span>
        <div className="hm-chips rv">
          {STACK.map((s) => (
            <span key={s}>{s}</span>
          ))}
        </div>
        <p className="hm-note rv">{t("Synthetic data only. Every club, player and league here is fictional.")}</p>
      </section>
    </div>
  );
}
