import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { BoxRow, Card, Clip, Explanation, MatchState, Reel, Roster, Shot } from "../types";
import type { Prefs } from "../prefs";
import { KIND_LABEL } from "../format";
import { Crest } from "./Crest";
import { WinProbability } from "./WinProbability";
import type { Caption, ExplainRequest, Pitch3DApi } from "./Pitch3D";

const Pitch3D = lazy(() => import("./Pitch3D"));

const EXPLAIN_KINDS = new Set(["goal", "low_xg_goal", "big_chance"]);
const MARK_KINDS = new Set(["goal", "low_xg_goal", "big_chance", "red_card"]);
const BROWSER_LANG: Record<string, string> = { en: "en-GB", es: "es-ES", hi: "hi-IN" };

interface Props {
  state: MatchState;
  prefs: Prefs;
  start?: Card | null; // a moment to explain as soon as the theatre opens
  onClose: () => void;
  onFocus?: (id: string) => void;
  focus: string | null;
}

const momentT = (c: Card) => Number(c.moment.state_ref.split("@")[1]);

/** Where the Highlights reel is: its title card, a clip by index, or its closing card. */
type ReelStep = { phase: "intro" } | { phase: "clip"; i: number } | { phase: "outro" };

/** One line of an explanation, said by Azure AI Speech, or the browser's voice when Speech is unavailable.
 * Never takes longer than the line needs: a voice that stalls must not stall the replay. */
function sayLine(room: string, eventId: string, index: number, lang: string, audio: HTMLAudioElement, text: string): Promise<void> {
  const cap = new Promise<void>((done) => window.setTimeout(done, Math.min(12000, 2500 + text.length * 70)));
  return Promise.race([cap, voiceLine(room, eventId, index, lang, audio)]);
}

function voiceLine(room: string, eventId: string, index: number, lang: string, audio: HTMLAudioElement): Promise<void> {
  return speakVia(`/api/rooms/${room}/explain/${encodeURIComponent(eventId)}/speech`, { index, lang }, lang, audio);
}

/** The reel's intro or outro, read the same way, with the same time cap. */
function sayPart(room: string, part: "intro" | "outro", lang: string, audio: HTMLAudioElement, text: string): Promise<void> {
  const cap = new Promise<void>((done) => window.setTimeout(done, Math.min(12000, 2500 + text.length * 70)));
  return Promise.race([cap, speakVia(`/api/rooms/${room}/reel/speech`, { part, lang }, lang, audio)]);
}

async function speakVia(url: string, body: object, lang: string, audio: HTMLAudioElement): Promise<void> {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (r.ok && r.headers.get("content-type")?.startsWith("audio/")) {
    const url = URL.createObjectURL(await r.blob());
    audio.src = url;
    await new Promise<void>((done) => {
      audio.onended = audio.onerror = audio.onpause = () => {
        URL.revokeObjectURL(url);
        done();
      };
      audio.play().catch(() => done());
    });
    return;
  }
  const said = await r.json().catch(() => null);
  if (!said?.text || !("speechSynthesis" in window)) return;
  await new Promise<void>((done) => {
    const u = new SpeechSynthesisUtterance(said.text);
    u.lang = BROWSER_LANG[said.lang ?? lang] ?? "en-GB";
    u.onend = u.onerror = () => done();
    speechSynthesis.speak(u);
  });
}

/** Results-page team stats: each side's value, the leader's in a club-coloured pill, and a split bar. */
function BoxScore({ rows, roster }: { rows: BoxRow[]; roster: Roster }) {
  const colors = [roster.clubs.home.primary, roster.clubs.away.primary];
  return (
    <div className="mt-box">
      <div className="mt-box-head">
        <Crest club={roster.clubs.home} size={22} />
        <span className="label">Team stats</span>
        <Crest club={roster.clubs.away} size={22} />
      </div>
      {rows.map((r) => {
        const [a, b] = r.values;
        const lead = a === b ? -1 : (r.lower_better ? b < a : b > a) ? 1 : 0;
        const fmt = (v: number) => `${r.key === "xg" ? v.toFixed(2) : v}${r.unit ?? ""}`;
        const total = a + b;
        return (
          <div key={r.key} className="mt-row">
            <b className={`num ${lead === 0 ? "lead" : ""}`} style={lead === 0 ? ({ "--club": colors[0] } as CSSProperties) : undefined}>{fmt(a)}</b>
            <div className="mt-row-mid">
              <span>{r.label}</span>
              <div className="mt-split">
                <i style={{ width: `${total ? (100 * a) / total : 50}%`, background: colors[0] }} />
                <i style={{ width: `${total ? (100 * b) / total : 50}%`, background: colors[1] }} />
              </div>
            </div>
            <b className={`num ${lead === 1 ? "lead" : ""}`} style={lead === 1 ? ({ "--club": colors[1] } as CSSProperties) : undefined}>{fmt(b)}</b>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Match Theatre: the 3D pitch full screen with everything about the match around it. The scoreboard,
 * the team stats, win probability, a timeline of the moments that mattered, and Explain this moment:
 * the replay freezes on each beat of the move while its verified line is shown and read.
 */
export function MatchTheatre({ state, prefs, start, onClose, onFocus, focus }: Props) {
  const { roster, stats, frame } = state;
  const pitch = useRef<Pitch3DApi>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const [req, setReq] = useState<ExplainRequest | null>(null);
  const [story, setStory] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [caption, setCaption] = useState<Caption | null>(null);
  const [paused, setPaused] = useState(false);
  const [voice, setVoice] = useState(true);
  const voiceRef = useRef(voice);
  voiceRef.current = voice;
  const said = useRef<string>("");

  const hush = () => {
    audio.current?.pause();
    window.speechSynthesis?.cancel();
  };

  // The Highlights reel. `run` changes with every step, so a late voice or fetch never acts on a newer one.
  const [reel, setReel] = useState<Reel | null>(null);
  const [step, setStep] = useState<ReelStep | null>(null);
  const [cardDone, setCardDone] = useState(false);
  const [reelNote, setReelNote] = useState<string | null>(null);
  const reelRef = useRef<Reel | null>(null);
  const stepRef = useRef<ReelStep | null>(null);
  const run = useRef(0);
  reelRef.current = reel;
  stepRef.current = step;

  /** Plays one shot's replay; false when it has no replay to play. */
  const playShot = useCallback(async (id: string, title: string, compact = false): Promise<boolean> => {
    setLoading(id);
    hush();
    try {
      let body: { shot: Shot; clip: Clip | null } & Partial<Explanation>;
      const r = await fetch(`/api/rooms/${state.room}/explain/${encodeURIComponent(id)}?lang=${prefs.lang}`);
      if (r.ok) body = await r.json();
      else {
        // No story for this shot (still recording, or not a big chance): the replay explains it from the shot record.
        const s = await fetch(`/api/rooms/${state.room}/shots/${encodeURIComponent(id)}`);
        body = await s.json();
      }
      if (!body.clip || body.clip.frames.length < 2) return false;
      const ex = body.beats ? (body as Explanation) : null;
      setStory(ex);
      setPaused(false);
      said.current = "";
      setReq({
        key: `${id}@${performance.now()}`,
        title,
        shot: body.shot,
        clip: body.clip,
        story: ex ?? undefined,
        lang: prefs.lang,
        voice: voiceRef.current && !!ex,
        compact,
      });
      return true;
    } catch {
      return false;
    } finally {
      setLoading(null);
    }
  }, [state.room, prefs.lang]);

  const stopReel = useCallback(() => {
    run.current++;
    reelRef.current = null;
    stepRef.current = null;
    setReel(null);
    setStep(null);
    setCardDone(false);
  }, []);

  const explain = useCallback(async (card: Card) => {
    const id = card.moment.event_ids[0];
    if (!id) return;
    if (reelRef.current) stopReel();
    await playShot(id, KIND_LABEL[card.moment.kind] ?? "Chance");
  }, [playShot, stopReel]);

  const goTo = useCallback(async (next: ReelStep | null) => {
    const token = ++run.current;
    hush();
    setCardDone(false);
    setCaption(null);
    if (next === null) {
      stepRef.current = null;
      setReel(null);
      setStep(null);
      return;
    }
    stepRef.current = next;
    setStep(next);
    if (next.phase !== "clip") {
      setReq(null);
      setStory(null);
      return;
    }
    const clip = reelRef.current?.clips[next.i];
    const ok = clip ? await playShot(clip.event_id, clip.label, true) : false;
    // A clip with no replay is skipped rather than shown as an error.
    if (!ok && token === run.current) void goTo(after(next, reelRef.current));
  }, [playShot]);

  const startReel = useCallback(async () => {
    stopReel();
    hush();
    setReelNote(null);
    pitch.current?.stopExplain();
    try {
      const r = await fetch(`/api/rooms/${state.room}/reel?lang=${prefs.lang}`);
      if (!r.ok) {
        setReelNote("The reel appears after the first goal or big chance.");
        return;
      }
      const body: Reel = await r.json();
      reelRef.current = body;
      setReel(body);
      setPaused(false);
      void goTo({ phase: "intro" });
    } catch {
      setReelNote("The reel appears after the first goal or big chance.");
    }
  }, [state.room, prefs.lang, goTo, stopReel]);

  // A title card is read once; it moves on when the line has been said and the reel is not paused.
  useEffect(() => {
    if (!step || step.phase === "clip" || !reel) return;
    const token = run.current;
    const part = step.phase;
    const text = (prefs.lang !== "en" && reel.langs[prefs.lang]?.[part]) || reel[part];
    if (!voiceRef.current) {
      const timer = window.setTimeout(() => token === run.current && setCardDone(true), Math.min(9000, 1500 + text.length * 55));
      return () => window.clearTimeout(timer);
    }
    audio.current ??= new Audio();
    void sayPart(state.room, part, prefs.lang, audio.current, text).finally(() => {
      if (token === run.current) setCardDone(true);
    });
  }, [step, reel, state.room, prefs.lang]);

  useEffect(() => {
    if (step && step.phase !== "clip" && cardDone && !paused) void goTo(after(step, reel));
  }, [step, cardDone, paused, reel, goTo]);

  const startedWith = useRef<string | null>(null);
  useEffect(() => {
    const id = start?.moment.moment_id ?? null;
    if (start && id !== startedWith.current) {
      startedWith.current = id;
      void explain(start);
    }
  }, [start, explain]);

  const endExplain = useCallback(() => {
    hush();
    setReq(null);
    setStory(null);
    setCaption(null);
    // In the reel, a clip that ends (or is skipped) hands over to the next one.
    const at = stepRef.current;
    if (at?.phase === "clip") void goTo(after(at, reelRef.current));
  }, [goTo]);

  // Each story caption is read once; when the line has been said the replay moves on.
  useEffect(() => {
    if (!caption || caption.step === undefined || !story || !req?.voice) return;
    const key = `${req.key}:${caption.step}`;
    if (said.current === key) return;
    said.current = key;
    hush();
    if (!voiceRef.current) {
      // Voice switched off mid-replay: hold each beat long enough to read it.
      const timer = window.setTimeout(() => pitch.current?.release(), Math.min(9000, 1200 + caption.text.length * 55));
      return () => window.clearTimeout(timer);
    }
    audio.current ??= new Audio();
    void sayLine(state.room, story.event_id, caption.step, prefs.lang, audio.current, caption.text).finally(() => {
      if (said.current === key) pitch.current?.release();
    });
  }, [caption, story, req, state.room, prefs.lang]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === " " && (req || step)) {
        e.preventDefault();
        setPaused((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, req, step]);

  useEffect(() => {
    pitch.current?.pauseReplay(paused);
    if (paused) hush();
  }, [paused]);

  useEffect(() => () => hush(), []);

  if (!roster || !stats) return null;
  const home = roster.clubs.home;
  const away = roster.clubs.away;
  const total = 2 * state.halfS;
  const marks = state.cards.filter((c) => MARK_KINDS.has(c.moment.kind));
  const chances = [...state.cards].filter((c) => EXPLAIN_KINDS.has(c.moment.kind)).reverse();
  const minute = Math.floor(stats.t / 60);
  const name = (id: string | null | undefined) => (id ? roster.players[id]?.name ?? id : "");
  const active = caption?.step;
  const lines = story ? (prefs.lang !== "en" && story.langs[prefs.lang]?.lines) || story.beats.map((b) => b.line) : [];
  const why = story ? (prefs.lang !== "en" && story.langs[prefs.lang]?.why) || story.why : "";

  return (
    <div className="theatre" role="dialog" aria-label="Match Theatre">
      <header className="mt-top">
        <span className="mt-brand">Match Theatre</span>
        <div className="mt-score">
          <Crest club={home} size={30} />
          <b>{home.name}</b>
          <span className="mt-sc num" style={{ "--h": home.primary, "--a": away.primary } as CSSProperties}>
            <i>{stats.score[0]}</i>
            <i>{stats.score[1]}</i>
          </span>
          <b>{away.name}</b>
          <Crest club={away} size={30} />
          <span className="mt-clock num">{state.status === "full_time" ? "FT" : `${minute}'`}</span>
        </div>
        <button className="mt-close" onClick={onClose}>Close <kbd>Esc</kbd></button>
      </header>

      <div className="mt-body">
        <section className="mt-stage">
          <Suspense fallback={<div className="mt-loading label">Loading the 3D pitch</div>}>
            <Pitch3D ref={pitch} frame={frame} roster={roster} focus={focus} tagged={new Set(prefs.players)} speed={state.speed}
              fx={state.fx} onSelect={onFocus} explain={req} onExplainEnd={endExplain} onCaption={setCaption} hideCaption />
          </Suspense>
          {reel && step && step.phase !== "clip" && (
            <div className="mt-reel-card" style={{ "--h": home.primary, "--a": away.primary } as CSSProperties}>
              <span className="label">{step.phase === "intro" ? "Highlights" : reel.status === "full_time" ? "Full time" : `${reel.minute}'`}</span>
              <div className="mt-reel-score">
                <Crest club={home} size={56} />
                <b>{home.name}</b>
                <span className="num"><i>{reel.score[0]}</i><i>{reel.score[1]}</i></span>
                <b>{away.name}</b>
                <Crest club={away} size={56} />
              </div>
              <p>{(prefs.lang !== "en" && reel.langs[prefs.lang]?.[step.phase]) || reel[step.phase]}</p>
            </div>
          )}
          {caption && (
            <div key={`${caption.kind}${caption.text}`} className="mt-caption" style={{ "--club": caption.color } as CSSProperties}>
              <span className="kind">{caption.kind}</span>
              <p>{caption.text}</p>
            </div>
          )}
          <div className="mt-timeline" aria-label="Key moments">
            <div className="mt-tl-track">
              <i className="mt-tl-now" style={{ width: `${Math.min(100, (100 * stats.t) / total)}%` }} />
              <i className="mt-tl-ht" style={{ left: "50%" }} />
              {marks.map((c) => {
                const t = momentT(c);
                const can = EXPLAIN_KINDS.has(c.moment.kind);
                const club = roster.clubs[c.moment.team ?? "home"];
                return (
                  <button key={c.moment.moment_id} disabled={!can}
                    className={`mt-tl-mark ${c.moment.kind} ${req?.shot.event_id === c.moment.event_ids[0] ? "on" : ""}`}
                    style={{ left: `${(100 * t) / total}%`, "--club": c.moment.kind === "red_card" ? "var(--down)" : club.primary } as CSSProperties}
                    title={`${c.moment.minute}' ${KIND_LABEL[c.moment.kind] ?? c.moment.kind}`}
                    onClick={() => can && void explain(c)} />
                );
              })}
            </div>
            <div className="mt-tl-ends label"><span>0'</span><span>HT</span><span>90'</span></div>
          </div>
        </section>

        <aside className="mt-rail">
          {reel && step ? (
            <div className="mt-panel mt-explain">
              <div className="mt-ph">
                <h3>Highlights reel</h3>
                <span className="label">
                  {step.phase === "intro" ? "Intro" : step.phase === "outro" ? "Outro" : `Clip ${step.i + 1} of ${reel.clips.length}`}
                </span>
              </div>
              <div className="mt-dots" aria-label="Reel progress">
                {reel.clips.map((c, i) => {
                  const at = step.phase === "clip" ? step.i : step.phase === "outro" ? reel.clips.length : -1;
                  return (
                    <i key={c.event_id} className={i === at ? "on" : i < at ? "done" : ""}
                      style={{ "--club": roster.clubs[c.team].primary } as CSSProperties} title={`${c.minute}' ${c.label}`} />
                  );
                })}
              </div>
              {step.phase === "clip" && reel.clips[step.i] && (
                <div className="mt-who" style={{ "--club": roster.clubs[reel.clips[step.i].team].primary } as CSSProperties}>
                  <b>{reel.clips[step.i].player_name}</b>
                  <span className="num">{reel.clips[step.i].minute}'</span>
                  <span>{reel.clips[step.i].label}</span>
                  <span className="num">{reel.clips[step.i].xg.toFixed(2)} xG</span>
                </div>
              )}
              {step.phase === "clip" && story && (
                <ol className="mt-steps">
                  <li className={`why ${active === -1 ? "on" : ""}`}>
                    <div className="mt-step-text">
                      <span className="label">{story.shot.outcome === "goal" ? "Why it worked" : "The verdict"}</span>
                      <p>{why}</p>
                    </div>
                  </li>
                </ol>
              )}
              <div className="mt-ctrl">
                <button onClick={() => setPaused((p) => !p)}>{paused ? "Play" : "Pause"}</button>
                <button onClick={() => {
                  if (step.phase === "clip" && req) pitch.current?.stopExplain();
                  else void goTo(after(step, reel));
                }}>Skip</button>
                <button className={voice ? "on" : ""} aria-pressed={voice} onClick={() => {
                  setVoice((v) => !v);
                  if (voice) {
                    hush();
                    pitch.current?.release();
                  }
                }}>Voice {voice ? "on" : "off"}</button>
                <button onClick={() => {
                  stopReel();
                  hush();
                  pitch.current?.stopExplain();
                  setReq(null);
                  setStory(null);
                }}>Stop</button>
              </div>
            </div>
          ) : req ? (
            <div className="mt-panel mt-explain">
              <div className="mt-ph">
                <h3>Explain this moment</h3>
                <span className="label">{req.shot.minute}' {req.title}</span>
              </div>
              <div className="mt-who" style={{ "--club": roster.clubs[req.shot.team].primary } as CSSProperties}>
                <b>{name(req.shot.player)}</b>
                <span className="num">{req.shot.xg.toFixed(2)} xG</span>
                <span className="num">{req.shot.distance_m.toFixed(1)} m</span>
                {req.shot.speed_kmh !== null && <span className="num">{Math.round(req.shot.speed_kmh)} km/h</span>}
              </div>
              {story ? (
                <ol className="mt-steps">
                  {story.beats.map((_, i) => (
                    <li key={i} className={active === i ? "on" : active !== undefined && (active === -1 || active > i) ? "done" : ""}>
                      <button onClick={() => pitch.current?.jumpTo(i)}>
                        <span className="num">{i + 1}</span>
                        <p>{lines[i]}</p>
                      </button>
                    </li>
                  ))}
                  <li className={`why ${active === -1 ? "on" : ""}`}>
                    <button onClick={() => pitch.current?.jumpTo(-1)}>
                      <span className="label">{req.shot.outcome === "goal" ? "Why it worked" : "The verdict"}</span>
                      <p>{why}</p>
                    </button>
                  </li>
                </ol>
              ) : (
                <p className="mt-note">The replay explains this shot from its tracking and the shot record.</p>
              )}
              <div className="mt-ctrl">
                <button onClick={() => setPaused((p) => !p)}>{paused ? "Play" : "Pause"}</button>
                <button onClick={() => {
                  const id = req.shot.event_id;
                  const card = state.cards.find((c) => c.moment.event_ids[0] === id);
                  if (card) void explain(card);
                }}>Replay</button>
                <button className={voice ? "on" : ""} aria-pressed={voice} onClick={() => {
                  setVoice((v) => !v);
                  if (voice) {
                    hush();
                    pitch.current?.release();
                  }
                }}>Voice {voice ? "on" : "off"}</button>
                <button onClick={() => pitch.current?.stopExplain()}>Back to live</button>
              </div>
            </div>
          ) : (
            <div className="mt-panel">
              <div className="mt-ph">
                <h3>Explain a moment</h3>
                <span className="label">{chances.length} so far</span>
              </div>
              <button className="mt-reel-go" onClick={() => void startReel()}>
                <b>Highlights reel</b>
                <span>Every goal and the best chances, explained in order</span>
              </button>
              {reelNote && <p className="mt-note">{reelNote}</p>}
              <div className="mt-list">
                {chances.length === 0 && <p className="mt-note">Goals and big chances appear here. Pick one to see how it happened.</p>}
                {chances.map((c) => {
                  const club = roster.clubs[c.moment.team ?? "home"];
                  const id = c.moment.event_ids[0];
                  return (
                    <button key={c.moment.moment_id} className="mt-chance" style={{ "--club": club.primary } as CSSProperties}
                      onClick={() => void explain(c)} disabled={loading === id}>
                      <span className="num">{c.moment.minute}'</span>
                      <b>{KIND_LABEL[c.moment.kind] ?? c.moment.kind}</b>
                      <span>{name(c.moment.players[0])}</span>
                      <em>{loading === id ? "Loading" : "Explain"}</em>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="mt-panel">
            <div className="mt-ph">
              <h3>Match stats</h3>
              <span className="label">From the event feed</span>
            </div>
            {stats.box ? <BoxScore rows={stats.box} roster={roster} /> : <p className="mt-note">Stats appear once the match starts.</p>}
          </div>

          <div className="mt-panel">
            <div className="mt-ph">
              <h3>Win probability</h3>
            </div>
            <div className="mt-wp">
              <WinProbability stats={stats} history={state.history} cards={state.cards} roster={roster} halfS={state.halfS} />
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

/** The reel's next step: the clips in order, then the closing card, then the end. */
function after(at: ReelStep, reel: Reel | null): ReelStep | null {
  const n = reel?.clips.length ?? 0;
  if (at.phase === "intro") return n ? { phase: "clip", i: 0 } : { phase: "outro" };
  if (at.phase === "clip") return at.i + 1 < n ? { phase: "clip", i: at.i + 1 } : { phase: "outro" };
  return null;
}
