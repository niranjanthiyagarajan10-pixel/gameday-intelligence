import { useEffect, useRef, useState } from "react";
import type { Card, Roster } from "../types";
import { cardText, type Lang, type Prefs, type Voice } from "../prefs";
import { sideColor } from "../format";

export const STYLES: { id: Voice; name: string; initials: string; blurb: string; color: string }[] = [
  { id: "classic", name: "Classic", initials: "CL", blurb: "Calm broadcast voice", color: "var(--signal)" },
  { id: "hype", name: "Hype", initials: "HY", blurb: "Funny, loud, loves a goal", color: "#FF5A3C" },
  { id: "stats", name: "Stats", initials: "ST", blurb: "Every line carries a number", color: "#7FD1FF" },
  { id: "tactician", name: "Tactician", initials: "TA", blurb: "Strict, shape and pressing", color: "#F4F4F1" },
];
const BROWSER_LANG: Record<Lang, string> = { en: "en-GB", es: "es-ES", hi: "hi-IN" };
const SHOWN = 4;

interface Said {
  text: string;
  lang: Lang;
  source: "commentator" | "classic";
}

/** Plays one line: Azure AI Speech when it answers, the browser's own voice when it does not. */
async function speak(room: string, momentId: string, style: Voice, lang: Lang, audio: HTMLAudioElement): Promise<void> {
  const r = await fetch(`/api/rooms/${room}/speech`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ moment_id: momentId, style, lang }),
  });
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
  const body = await r.json().catch(() => null);
  if (!body?.text || !("speechSynthesis" in window)) return;
  await new Promise<void>((done) => {
    const u = new SpeechSynthesisUtterance(body.text);
    u.lang = BROWSER_LANG[(body.lang as Lang) ?? lang];
    u.onend = u.onerror = () => done();
    speechSynthesis.speak(u);
  });
}

/** The live commentary: the latest key moments, said in the fan's chosen style, with a voice. */
export function Commentator({ room, cards, roster, prefs, update }: {
  room: string;
  cards: Card[];
  roster: Roster;
  prefs: Prefs;
  update: (p: Partial<Prefs>) => void;
}) {
  const style = prefs.voice;
  const lang = prefs.lang;
  const [said, setSaid] = useState<Record<string, Said>>({});
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const queue = useRef<string[]>([]);
  const busy = useRef(false);
  const lastAuto = useRef<string | null>(null);
  const latest = cards.slice(-SHOWN).reverse();
  const key = (id: string) => `${id}|${style}|${lang}`;

  // Styled lines are written on request; classic lines come with the card itself.
  useEffect(() => {
    if (style === "classic") return;
    for (const c of latest) {
      const id = c.moment.moment_id;
      if (said[key(id)]) continue;
      setSaid((s) => ({ ...s, [key(id)]: { text: "", lang, source: "classic" } }));
      fetch(`/api/rooms/${room}/commentary/${encodeURIComponent(id)}?style=${style}&lang=${lang}`)
        .then((r) => r.json())
        .then((b: Said) => setSaid((s) => ({ ...s, [key(id)]: b })))
        .catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest.map((c) => c.moment.moment_id).join(), style, lang, room]);

  const lineFor = (c: Card): { text: string; styled: boolean } => {
    const s = said[key(c.moment.moment_id)];
    if (style !== "classic" && s?.source === "commentator" && s.text) return { text: s.text, styled: true };
    return { text: cardText(c, "casual", lang).text, styled: false };
  };

  const drain = async () => {
    if (busy.current) return;
    busy.current = true;
    audio.current ??= new Audio();
    while (queue.current.length) {
      const id = queue.current.shift()!;
      setPlaying(id);
      try {
        await speak(room, id, style, lang, audio.current);
      } catch {
        /* a voice that fails stays silent; the line is still on screen */
      }
    }
    setPlaying(null);
    busy.current = false;
  };

  const play = (id: string) => {
    if (playing === id) {
      audio.current?.pause();
      window.speechSynthesis?.cancel();
      return;
    }
    queue.current = [id];
    void drain();
  };

  // Voice on: each new moment is read out as it lands. A backlog is trimmed, never queued up.
  const newest = cards[cards.length - 1]?.moment.moment_id;
  useEffect(() => {
    if (!prefs.voiceOn || !newest || newest === lastAuto.current) return;
    if (lastAuto.current === null) {
      lastAuto.current = newest; // do not read out the past when the voice is switched on
      return;
    }
    lastAuto.current = newest;
    queue.current = [...queue.current, newest].slice(-2);
    void drain();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newest, prefs.voiceOn]);

  return (
    <div className="panel comm">
      <div className="ph">
        <h3>Commentator</h3>
        <button className={`voice-toggle ${prefs.voiceOn ? "on" : ""}`} onClick={() => {
          lastAuto.current = null;
          update({ voiceOn: !prefs.voiceOn });
        }}>
          <span className="spk" aria-hidden />
          {prefs.voiceOn ? "Voice on" : "Voice off"}
        </button>
      </div>
      <div className="comm-styles" role="radiogroup" aria-label="Commentator style">
        {STYLES.map((s) => (
          <button key={s.id} role="radio" aria-checked={style === s.id} className={style === s.id ? "on" : ""}
            onClick={() => update({ voice: s.id })} title={s.blurb}>
            <i style={{ background: s.color }}>{s.initials}</i>
            <b>{s.name}</b>
          </button>
        ))}
      </div>
      <div className="comm-feed">
        {latest.length === 0 && <div className="empty">The commentator speaks when the first key moment lands.</div>}
        {latest.map((c, i) => {
          const id = c.moment.moment_id;
          const line = lineFor(c);
          const waiting = style !== "classic" && !said[key(id)]?.text && said[key(id)] !== undefined;
          return (
            <div key={id} className={`comm-line ${i === 0 ? "big" : ""} ${playing === id ? "playing" : ""}`}
              style={{ borderLeftColor: sideColor(roster, c.moment.team) }}>
              <div className="min num">{c.moment.minute}'</div>
              <div className="say">
                <p lang={lang} className={waiting ? "dim" : ""}>{line.text}</p>
                <div className="meta">
                  <span className="verified">Verified</span>
                  <span className="label">{line.styled ? `Commentator · ${STYLES.find((s) => s.id === style)?.name}` : "Commentator · Classic"}</span>
                  {playing === id && (
                    <span className="wave" aria-hidden>
                      <i /><i /><i /><i /><i />
                    </span>
                  )}
                </div>
              </div>
              <button className="play" onClick={() => play(id)} aria-label={playing === id ? "Stop" : "Play this line"}>
                {playing === id ? (
                  <svg width="14" height="14" viewBox="0 0 14 14"><rect x="2" y="2" width="10" height="10" /></svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 1.5L12.5 7L3 12.5Z" /></svg>
                )}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
