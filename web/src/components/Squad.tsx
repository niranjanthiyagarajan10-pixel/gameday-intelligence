import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { TraceStep } from "../types";
import { t, tx } from "../i18n";

/**
 * The Squad: our eleven agents as a football team, each marking the problem it solves. Hover or tap a
 * player for what it does, where it plays in the product and what it has done in this match (from the
 * live trace). Kick off sends every agent at its problem; VAR, the code that checks every line, blows
 * the whistle.
 */

type Href = { label: string; href: string };

interface Agent {
  no: number;
  nick: string;
  agent: string;
  trace: string[]; // the agent's name in the trace
  pos: [number, number]; // metres on a 105 x 68 pitch, attacking right
  skin: string;
  does: string;
  problem: string;
  pain: string;
  where: Href[];
}

const SKIN = ["#f1c7a0", "#d9a273", "#a86b45", "#7a4a2e", "#e8b98f", "#c68a5e"];

export const XI: Agent[] = [
  { no: 1, nick: tx("Safe Hands"), agent: "Analyst", trace: ["Analyst"], pos: [7, 34], skin: SKIN[2],
    does: tx("Answers any question about the match through 15 read-only MCP tools. Code re-runs every tool call to fill each number, and it says so when the data cannot answer."),
    problem: tx("Made-up stats"), pain: tx("Chatbots answer football questions with numbers nobody checked."),
    where: [{ label: tx("Ask the match"), href: "#/" }] },
  { no: 2, nick: tx("The Sweeper"), agent: "Summarizer", trace: ["Summarizer"], pos: [15, 9], skin: SKIN[0],
    does: tx("Catch me up: three points a late arrival can read in twenty seconds, rewritten as the match moves on."),
    problem: tx("Arrived late, totally lost"), pain: tx("Join at half time and nothing tells you what you missed."),
    where: [{ label: tx("Catch me up"), href: "#/" }] },
  { no: 3, nick: tx("The Scout"), agent: "Preview", trace: ["Preview"], pos: [14, 25], skin: SKIN[3],
    does: tx("Writes the story before kick-off: form, head to head, the forecast and the players to watch."),
    problem: tx("No idea what is at stake"), pain: tx("Fans arrive without the context that makes a match matter."),
    where: [{ label: tx("Preview"), href: "#/preview" }] },
  { no: 4, nick: tx("The Debrief"), agent: "Post-game", trace: ["Post-game"], pos: [14, 43], skin: SKIN[4],
    does: tx("What decided the match, and what each club should watch next time."),
    problem: tx("Final whistle, no takeaway"), pain: tx("The match ends and the story ends with it."),
    where: [{ label: tx("Blueprint"), href: "#/blueprint" }] },
  { no: 5, nick: tx("The Interpreter"), agent: "Personalizer", trace: ["Personalizer"], pos: [15, 59], skin: SKIN[1],
    does: tx("Every verified line in eight languages. Slots carry over untouched, so numbers and names stay true in every one."),
    problem: tx("Not in my language"), pain: tx("Most match apps speak one language to a global game."),
    where: [{ label: tx("Language switch"), href: "#/" }] },
  { no: 6, nick: tx("The Anchor"), agent: "In-depth Analyst", trace: ["Deep Analyst"], pos: [24, 34], skin: SKIN[5],
    does: tx("Every fifteen minutes and after big moments: why the match is going the way it is, from threat, shape and gravity."),
    problem: tx("Why is this even happening?"), pain: tx("Stats show what happened, never why."),
    where: [{ label: tx("Live tab, analyst depth"), href: "#/" }] },
  { no: 7, nick: tx("The Wingers"), agent: "Narrator x2", trace: ["Narrator"], pos: [40, 58], skin: SKIN[0],
    does: tx("Two Narrators run in parallel down both flanks: every key moment written for casual fans and for analysts, in an Agent Framework workflow."),
    problem: tx("Score only, no story"), pain: tx("A goal alert says 1-0 and nothing about how or why."),
    where: [{ label: tx("Key moments"), href: "#/" }] },
  { no: 8, nick: tx("The Voice"), agent: "Commentator", trace: ["Commentator", "Voice"], pos: [29, 16], skin: SKIN[2],
    does: tx("The same moment in Classic, Hype, Stats or Tactician style, read aloud by Azure AI Speech. Only the tone changes, never the facts."),
    problem: tx("Dead air"), pain: tx("Second-screen apps are silent."),
    where: [{ label: tx("Commentator"), href: "#/" }] },
  { no: 9, nick: tx("The Finisher"), agent: "Explainer", trace: ["Explainer"], pos: [42, 34], skin: SKIN[3],
    does: tx("Explain this moment: how every goal was made, beat by beat, replayed in 3D with drawings and voice."),
    problem: tx("Saw the goal, did not get it"), pain: tx("Replays show the goal but never explain it."),
    where: [{ label: tx("Match Theatre"), href: "#/" }] },
  { no: 10, nick: tx("The Playmaker"), agent: "Recap", trace: ["Recap"], pos: [29, 52], skin: SKIN[4],
    does: tx("The match report on the Blueprint: a headline and a story over the facts the engine computed."),
    problem: tx("Where is the match report?"), pain: tx("Reports arrive hours later, if at all."),
    where: [{ label: tx("Blueprint"), href: "#/blueprint" }] },
  { no: 11, nick: tx("The Back Page"), agent: "Newsdesk", trace: ["Newsdesk"], pos: [40, 10], skin: SKIN[1],
    does: tx("A newspaper report for every fixture of the matchday, written ahead and checked."),
    problem: tx("What happened elsewhere?"), pain: tx("Your match is one of five, and the rest are a blur."),
    where: [{ label: tx("Newsdesk"), href: "#/news" }] },
];

export const SUB: Agent = {
  no: 12, nick: tx("The Super-Sub"), agent: "Producer", trace: ["Producer"], pos: [0, 0], skin: SKIN[5],
  does: tx("The newest signing: picks the clips and presents a narrated Highlights reel with a verified intro and outro."),
  problem: tx("No time to watch it all"), pain: tx("Ninety minutes is a lot to ask."),
  where: [{ label: tx("Highlights reel"), href: "#/" }],
};

const VAR = {
  nick: tx("VAR"),
  does: tx("Not an AI: code. Agents never type a number or a name. Code fills every slot, then checks every claim against the match data. A line that fails goes back to its agent with the reasons, then falls back to a template. Nothing unchecked reaches a fan."),
};

const W = 1050;
const H = 680;
const PX = W / 105;
const RUN_MS = 900;
const STAGGER_MS = 260;

const px = ([x, y]: [number, number]): [number, number] => [x * PX, y * PX];
const mirror = ([x, y]: [number, number]): [number, number] => [105 - x, y];

/** A player: shadow, boots, shorts, shirt with number, a round head with a face. */
function Figure({ kind, no, skin, mood }: { kind: "agent" | "problem" | "ref"; no?: number; skin: string; mood: "happy" | "grumpy" | "calm" }) {
  const shirt = kind === "agent" ? "var(--signal)" : kind === "problem" ? "#1d1f25" : "#0b0c0e";
  const ink = kind === "agent" ? "#000" : kind === "problem" ? "#ff4d4d" : "#f4f4f1";
  const shorts = kind === "agent" ? "#0b0c0e" : kind === "problem" ? "#3a1416" : "#0b0c0e";
  return (
    <g className={`fig fig-${kind}`}>
      <ellipse cx={0} cy={30} rx={15} ry={4} fill="#000" opacity={0.45} />
      <rect x={-8} y={14} width={6} height={14} rx={2} fill="#f4f4f1" />
      <rect x={2} y={14} width={6} height={14} rx={2} fill="#f4f4f1" />
      <rect x={-9} y={26} width={8} height={4} rx={1.5} fill="#000" />
      <rect x={1} y={26} width={8} height={4} rx={1.5} fill="#000" />
      <rect x={-10} y={8} width={20} height={10} rx={2} fill={shorts} />
      <path d="M-11,-12 L-19,-6 L-15,1 L-11,-2 L-11,12 L11,12 L11,-2 L15,1 L19,-6 L11,-12 Z" fill={shirt}
        stroke={kind === "problem" ? "#ff4d4d" : "#000"} strokeWidth={kind === "problem" ? 1.4 : 1} />
      <text x={0} y={6} textAnchor="middle" className="fig-no" fill={ink}>{kind === "problem" ? "?" : kind === "ref" ? "" : no}</text>
      {kind === "ref" && <rect x={-3} y={-8} width={6} height={14} fill="#f4f4f1" opacity={0.9} />}
      <circle cx={0} cy={-22} r={11} fill={skin} stroke="#000" strokeWidth={1} />
      <path d="M-11,-24 Q-10,-35 0,-35 Q10,-35 11,-24 Q5,-30 0,-29 Q-6,-30 -11,-24 Z" fill="#17120e" />
      <circle cx={-4} cy={-21} r={1.6} fill="#000" />
      <circle cx={4} cy={-21} r={1.6} fill="#000" />
      {mood === "grumpy" && <path d="M-7,-26 L-2,-24 M7,-26 L2,-24" stroke="#000" strokeWidth={1.4} strokeLinecap="round" />}
      <path d={mood === "happy" ? "M-4,-16 Q0,-12 4,-16" : mood === "grumpy" ? "M-4,-14 Q0,-17 4,-14" : "M-3,-15 L3,-15"}
        stroke="#000" strokeWidth={1.4} fill="none" strokeLinecap="round" />
    </g>
  );
}

function Plate({ title, sub, kind, width = 150 }: { title: string; sub: string; kind: "agent" | "problem" | "ref"; width?: number }) {
  return (
    <g className={`plate plate-${kind}`} transform="translate(0,50)">
      <rect x={-width / 2} y={0} width={width} height={34} rx={2} />
      <text x={0} y={14} textAnchor="middle" className="plate-t">{title}</text>
      <text x={0} y={27} textAnchor="middle" className="plate-s">{sub}</text>
    </g>
  );
}

function PitchLines() {
  const s = PX;
  return (
    <g className="sq-lines" fill="none">
      <rect x={0} y={0} width={W} height={H} />
      <line x1={W / 2} y1={0} x2={W / 2} y2={H} />
      <circle cx={W / 2} cy={H / 2} r={9.15 * s} />
      <circle cx={W / 2} cy={H / 2} r={3} className="dot" />
      <rect x={0} y={(34 - 20.16) * s} width={16.5 * s} height={40.32 * s} />
      <rect x={W - 16.5 * s} y={(34 - 20.16) * s} width={16.5 * s} height={40.32 * s} />
      <rect x={0} y={(34 - 9.16) * s} width={5.5 * s} height={18.32 * s} />
      <rect x={W - 5.5 * s} y={(34 - 9.16) * s} width={5.5 * s} height={18.32 * s} />
      <path d={`M${16.5 * s},${(34 - 7.3) * s} A${9.15 * s},${9.15 * s} 0 0 1 ${16.5 * s},${(34 + 7.3) * s}`} />
      <path d={`M${W - 16.5 * s},${(34 - 7.3) * s} A${9.15 * s},${9.15 * s} 0 0 0 ${W - 16.5 * s},${(34 + 7.3) * s}`} />
    </g>
  );
}

interface Evals { planted?: { caught: number; planted: number; clean: number; clean_passed: number } }

export function Squad({ trace }: { trace: TraceStep[] }) {
  const [sel, setSel] = useState<number | "var">(9);
  const [phase, setPhase] = useState<"idle" | "play" | "done">("idle");
  const [beaten, setBeaten] = useState<Set<number>>(new Set());
  const [evals, setEvals] = useState<Evals | null>(null);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    fetch("/api/evals").then((r) => (r.ok ? r.json() : null)).then(setEvals).catch(() => undefined);
    return () => timers.current.forEach((id) => window.clearTimeout(id));
  }, []);

  const stats = useMemo(() => {
    const by: Record<string, { drafts: number; passed: number }> = {};
    let pass = 0;
    let reject = 0;
    for (const s of trace) {
      if (s.agent === "Verifier") {
        if (s.status === "pass") pass++;
        else if (s.status === "reject") reject++;
        continue;
      }
      const row = (by[s.agent] ??= { drafts: 0, passed: 0 });
      if (s.status === "ok" || s.status === "pass") row.drafts++;
      if (s.status === "pass") row.passed++;
    }
    return { by, pass, reject };
  }, [trace]);

  const kickOff = () => {
    timers.current.forEach((id) => window.clearTimeout(id));
    timers.current = [];
    setBeaten(new Set());
    setPhase("play");
    const order = [...XI].sort((a, b) => b.pos[0] - a.pos[0]); // forwards first, the keeper last
    order.forEach((a, i) => {
      timers.current.push(window.setTimeout(() => setSel(a.no), i * STAGGER_MS));
      timers.current.push(window.setTimeout(() => setBeaten((b) => new Set(b).add(a.no)), i * STAGGER_MS + RUN_MS));
    });
    timers.current.push(window.setTimeout(() => {
      setPhase("done");
      setSel("var");
    }, order.length * STAGGER_MS + RUN_MS + 500));
  };
  const reset = () => {
    timers.current.forEach((id) => window.clearTimeout(id));
    setBeaten(new Set());
    setPhase("idle");
    setSel(9);
  };

  const card = sel === "var" ? null : sel === 12 ? SUB : XI.find((a) => a.no === sel)!;
  const used = card ? card.trace.reduce((n, name) => n + (stats.by[name]?.drafts ?? 0), 0) : 0;
  const p = evals?.planted;

  return (
    <div className="squad">
      <header className="sq-head">
        <div>
          <span className="label">{t("Meet the team")}</span>
          <h1>{t("The Gameday XI")}</h1>
          <p>{t("Eleven AI agents on Microsoft Foundry, one problem each. And a referee that is code, not AI.")}</p>
        </div>
        <div className="sq-actions">
          {phase === "idle" && <button className="sq-kick" onClick={kickOff}>{t("Kick off")}</button>}
          {phase !== "idle" && <button className="sq-reset" onClick={reset}>{t("Line up again")}</button>}
        </div>
      </header>

      <div className="sq-body">
        <div className="sq-stage">
          <svg viewBox={`-20 -50 ${W + 40} ${H + 170}`} className="sq-pitch" role="img"
            aria-label={t("Our eleven agents in a 4-3-3, each marking the problem it solves")}>
            {Array.from({ length: 12 }, (_, i) => (
              <rect key={i} x={(i * W) / 12} y={0} width={W / 12} height={H} className={i % 2 ? "stripe a" : "stripe b"} />
            ))}
            <PitchLines />
            <text x={W * 0.25} y={-18} textAnchor="middle" className="sq-side us">{t("The Gameday XI")}</text>
            <text x={W * 0.75} y={-18} textAnchor="middle" className="sq-side them">{t("The Chaos XI")}</text>

            {card && card.no !== 12 && (() => {
              const [ax, ay] = px(card.pos);
              const [bx, by] = px(mirror(card.pos));
              return <line x1={ax} y1={ay} x2={bx} y2={by} className="sq-mark" />;
            })()}

            {XI.map((a, i) => {
              const [x, y] = px(mirror(a.pos));
              const out = beaten.has(a.no);
              return (
                <g key={`p${a.no}`} transform={`translate(${x},${y})`} className={`sq-player problem ${out ? "beaten" : ""} ${sel === a.no ? "on" : ""}`}
                  onMouseEnter={() => phase !== "play" && setSel(a.no)} onClick={() => setSel(a.no)}>
                  <g transform="scale(1.4)"><Figure kind="problem" skin={SKIN[(i + 2) % SKIN.length]} mood="grumpy" /></g>
                  <Plate title={t(a.problem)} sub={out ? t("Solved") : t("The problem")} kind="problem" width={168} />
                </g>
              );
            })}

            {XI.map((a) => {
              const [x, y] = px(a.pos);
              const [tx2] = px(mirror(a.pos));
              const run = phase !== "idle" && (beaten.has(a.no) || sel === a.no) ? tx2 - x - 60 : 0;
              return (
                <g key={`a${a.no}`} transform={`translate(${x},${y})`}>
                  <g className={`sq-player agent ${sel === a.no ? "on" : ""}`} style={{ transform: `translateX(${run}px)` } as CSSProperties}
                    onMouseEnter={() => phase !== "play" && setSel(a.no)} onClick={() => setSel(a.no)} tabIndex={0}
                    onFocus={() => setSel(a.no)} role="button" aria-label={`${a.no} ${t(a.nick)}`}>
                    <g transform="scale(1.4)"><Figure kind="agent" no={a.no} skin={a.skin} mood="happy" /></g>
                    <Plate title={`${a.no} ${t(a.nick)}`} sub={a.agent} kind="agent" />
                  </g>
                </g>
              );
            })}

            <g transform={`translate(${W / 2},${H * 0.2})`} className={`sq-player ref ${sel === "var" ? "on" : ""} ${phase === "done" ? "whistle" : ""}`}
              onMouseEnter={() => phase !== "play" && setSel("var")} onClick={() => setSel("var")} role="button" aria-label="VAR">
              <g transform="scale(1.4)"><Figure kind="ref" skin={SKIN[4]} mood="calm" /></g>
              <Plate title={t("VAR")} sub={t("Code, not AI")} kind="ref" width={120} />
            </g>

            <g transform={`translate(0,${H + 22})`} className="sq-bench">
              <rect x={0} y={0} width={W} height={88} />
              <text x={14} y={20} className="label-svg">{t("Bench")}</text>
              <g transform="translate(120,30)" className={`sq-player agent ${sel === 12 ? "on" : ""}`}
                onMouseEnter={() => phase !== "play" && setSel(12)} onClick={() => setSel(12)} role="button" aria-label={t(SUB.nick)}>
                <g transform="scale(0.8)"><Figure kind="agent" no={12} skin={SUB.skin} mood="happy" /></g>
                <g transform="translate(140,-14)">
                  <text className="sq-bench-t">{`12 ${t(SUB.nick)}`}</text>
                  <text y={18} className="sq-bench-s">{`${t(SUB.problem)}: ${t("solved by the Highlights reel")}`}</text>
                </g>
              </g>
            </g>
          </svg>
          {phase === "done" && (
            <div className="sq-final" role="status">
              <b>{t("Full time")}</b>
              <span>{t("11 problems. 11 agents. 0 made-up numbers.")}</span>
            </div>
          )}
        </div>

        <aside className="sq-card" aria-live="polite">
          {card ? (
            <>
              <div className="sq-card-top">
                <span className="sq-shirt">{card.no}</span>
                <div>
                  <h2>{t(card.nick)}</h2>
                  <span className="label">{card.agent} {t("agent")}</span>
                </div>
              </div>
              <p className="sq-does">{t(card.does)}</p>
              <div className="sq-vs">
                <span className="label">{t("Marks")}</span>
                <b>{t(card.problem)}</b>
                <p>{t(card.pain)}</p>
              </div>
              <div className="sq-where">
                <span className="label">{t("Where it plays")}</span>
                <div>
                  {card.where.map((w) => (
                    <a key={w.label} href={w.href}>{t(w.label)}</a>
                  ))}
                </div>
              </div>
              <div className="sq-live">
                <b className="num">{used}</b>
                <span>{t("model calls in this match so far")}</span>
              </div>
            </>
          ) : (
            <>
              <div className="sq-card-top">
                <span className="sq-shirt ref">VAR</span>
                <div>
                  <h2>{t(VAR.nick)}</h2>
                  <span className="label">{t("The Verifier")}</span>
                </div>
              </div>
              <p className="sq-does">{t(VAR.does)}</p>
              <div className="sq-var">
                <div><b className="num">{stats.pass}</b><span>{t("lines passed in this match")}</span></div>
                <div><b className="num">{stats.reject}</b><span>{t("sent back to their agent")}</span></div>
                {p && <div><b className="num">{p.caught.toLocaleString()}/{p.planted.toLocaleString()}</b><span>{t("planted errors caught in testing")}</span></div>}
                {p && <div><b className="num">{p.clean_passed}/{p.clean}</b><span>{t("clean lines passed")}</span></div>}
              </div>
              <a className="sq-evals" href="#/evals">{t("See the evals")}</a>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
