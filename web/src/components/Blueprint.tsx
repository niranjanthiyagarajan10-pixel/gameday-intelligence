import { AfterMatch } from "./AfterMatch";
import { useEffect, useState } from "react";
import type { BlueprintData, Highlight, LeverageSpot, MarkingSpot, Performer, Roster, ShotPageData } from "../types";
import { Crest } from "./Crest";
import { Jersey, KitAvatar } from "./Kit";
import { Replay } from "./Replay";
import { ShotExplorer } from "./ShotExplorer";
import { GravitySection } from "./GravityMap";
import { playerHref } from "../route";
import type { Lang } from "../prefs";
import { t } from "../i18n";

const REFRESH_MS = 5000;
const POSITION: Record<string, string> = { GK: "GK", DF: "DF", MF: "MF", FW: "FW" };

const signed = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function Header({ bp, roster }: { bp: BlueprintData; roster: Roster }) {
  const [h, a] = bp.score;
  const final = bp.status === "full_time";
  const team = (side: "home" | "away", score: number, other: number) => {
    const club = roster.clubs[side];
    return (
      <div className={`bp-team ${side}`}>
        <Crest club={club} size={84} />
        <div className="bp-team-name">
          <h2>{club.name}</h2>
          <span className="muted">
            {side === "home" ? t("Home") : t("Away")}, {club.formation}
            {bp.men[side === "home" ? 0 : 1] < 11 ? `, ${t("{n} men", { n: bp.men[side === "home" ? 0 : 1] })}` : ""}
          </span>
        </div>
        <b className={`bp-score num ${score >= other ? "" : "lost"}`}>{score}</b>
      </div>
    );
  };
  return (
    <section className="bp-head">
      {team("home", h, a)}
      <div className="bp-state">
        <b>{final ? t("Full time") : bp.status === "catching_up" ? t("Catching up") : `${t("Live")} ${Math.floor(bp.t / 60)}'`}</b>
        <a href="#/">&#9656; Back to the match</a>
      </div>
      {team("away", a, h)}
    </section>
  );
}

function Highlights({ room, items, roster }: { room: string; items: Highlight[]; roster: Roster }) {
  const [i, setI] = useState(0);
  const [data, setData] = useState<ShotPageData | null>(null);
  const item = items[Math.min(i, items.length - 1)];

  useEffect(() => {
    if (!item) return;
    let alive = true;
    setData(null);
    fetch(`/api/rooms/${room}/shots/${encodeURIComponent(item.event_id)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => alive && setData(d as ShotPageData | null));
    return () => {
      alive = false;
    };
  }, [room, item?.event_id]);

  if (!item) return null;
  const club = roster.clubs[item.team];
  return (
    <section className="bp-section bp-reel">
      <div className="bp-reel-stage">
        {data?.clip ? (
          <Replay key={item.event_id} clip={data.clip} shot={data.shot} roster={roster} />
        ) : (
          <div className="empty bp-reel-wait">{t("Loading the replay from tracking data.")}</div>
        )}
        <div className="bp-reel-caption" style={{ borderLeftColor: club.primary }}>
          <h3>{item.title}</h3>
          <p>{item.subtitle}</p>
        </div>
      </div>
      <div className="bp-dots">
        <button aria-label={t("Previous highlight")} onClick={() => setI((i - 1 + items.length) % items.length)}>&larr;</button>
        {items.map((h, k) => (
          <button key={h.event_id} className={k === i ? "on" : ""} aria-label={h.title} onClick={() => setI(k)} />
        ))}
        <button aria-label={t("Next highlight")} onClick={() => setI((i + 1) % items.length)}>&rarr;</button>
      </div>
    </section>
  );
}

function Performers({ items, roster }: { items: Performer[]; roster: Roster }) {
  return (
    <section className="bp-section">
      <h3 className="bp-h">{t("Top performers")}</h3>
      <div className="bp-performers">
        {items.map((p) => {
          const info = roster.players[p.player];
          const club = roster.clubs[p.team];
          if (!info) return null;
          const [first, ...rest] = info.name.split(" ");
          return (
            <a key={p.key} className="bp-perf" href={playerHref(p.player)}>
              <div className="bp-perf-name">
                <span>{first}</span>
                <span>{rest.join(" ")}</span>
                <i title={p.info} aria-label={p.info}>i</i>
              </div>
              <b className="num">{p.value}</b>
              <span className="label">{p.label}</span>
              <div className="bp-perf-foot">
                <Crest club={club} size={30} />
                <Jersey club={club} info={info} size={104} />
              </div>
            </a>
          );
        })}
      </div>
    </section>
  );
}

function Band({ roster, player, side, small }: { roster: Roster; player: string; side: "home" | "away"; small?: string }) {
  const club = roster.clubs[side];
  const info = roster.players[player];
  if (!info) return null;
  return (
    <div className="bp-band" style={{ background: club.primary, color: club.secondary }}>
      <div className="bp-band-mark">
        <Crest club={club} size={120} />
      </div>
      <div>
        <span className="bp-band-sub">{small ?? `${club.short} | #${info.number} | ${POSITION[info.position]}`}</span>
        <h4>{info.name}</h4>
      </div>
      <Jersey club={club} info={info} size={92} away />
    </div>
  );
}

function Marking({ items, roster }: { items: MarkingSpot[]; roster: Roster }) {
  if (!items.length) return null;
  return (
    <section className="bp-section">
      <h3 className="bp-h">{t("Marking spotlight")}</h3>
      <div className="bp-pair">
        {items.map((m) => {
          const att = roster.players[m.attacker];
          const def = roster.players[m.defender];
          if (!att || !def) return null;
          const attClub = roster.clubs[att.side];
          return (
            <div key={`${m.defender}-${m.attacker}`} className="bp-card flush">
              <Band roster={roster} player={m.defender} side={m.team} small={roster.clubs[m.team].short} />
              <div className="bp-time">
                <div className="bp-time-bar">
                  <i style={{ width: `${m.share * 100}%` }} />
                  <span className="num l">{mmss(m.seconds)}</span>
                  <span className="num r">{mmss(m.defending_s)}</span>
                </div>
                <p>{m.caption}</p>
              </div>
              <div className="bp-card-body">
                <div className="bp-who">
                  <KitAvatar club={attClub} info={att} size={48} />
                  <div>
                    <span className="label">{t("Attacker")}</span>
                    <b>{att.name}</b>
                    <span className="muted">{attClub.short}</span>
                  </div>
                </div>
                <div className="bp-tiles two">
                  <div><b className="num">{m.shots}</b><span>{t("Shots allowed")}</span></div>
                  <div><b className="num">{m.xg.toFixed(2)}</b><span>{t("xG allowed")}</span></div>
                  <div><b className="num">{m.goals}</b><span>{t("Goals allowed")}</span></div>
                  <div><b className="num">{m.received}</b><span>{t("Passes received")}</span></div>
                </div>
                <h5>
                  {def.name} on {att.name}
                </h5>
                <p>{m.text}</p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

const PARTS: [keyof LeverageSpot, string][] = [
  ["shot_making", "Shot making"],
  ["creation", "Creation"],
  ["defending", "Defending"],
  ["turnovers", "Turnovers"],
];

function LeverageCards({ items, roster }: { items: LeverageSpot[]; roster: Roster }) {
  if (!items.length) return null;
  return (
    <section className="bp-section">
      <h3 className="bp-h">{t("Leverage spotlight")}</h3>
      <div className="bp-pair">
        {items.map((l) => {
          const club = roster.clubs[l.team];
          const scale = Math.max(0.25, ...PARTS.map(([k]) => Math.abs(l[k] as number)));
          return (
            <div key={l.player} className="bp-card flush">
              <Band roster={roster} player={l.player} side={l.team} />
              <div className="bp-card-body">
                <span className="label">{t("Game leverage")}</span>
                <div className="bp-lev">
                  <b className={`num ${l.total >= 0 ? "up" : "down"}`}>{signed(l.total)}</b>
                  <span>{t("LVG")}</span>
                </div>
                <div className="bp-parts">
                  {PARTS.map(([k, label]) => {
                    const v = l[k] as number;
                    return (
                      <div key={k} className="bp-part">
                        <span>{t(label)}</span>
                        <div className="bp-part-bar">
                          <i
                            style={{
                              left: v >= 0 ? "50%" : `${50 - (Math.abs(v) / scale) * 50}%`,
                              width: `${(Math.abs(v) / scale) * 50}%`,
                              background: v >= 0 ? club.primary : "var(--down)",
                            }}
                          />
                        </div>
                        <b className="num">{signed(v)}</b>
                      </div>
                    );
                  })}
                </div>
                <p>{l.text}</p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** The Match Blueprint: one page that tells the story of the match. */
export function Blueprint({ room, roster, halfS, lang = "en" }: { room: string; roster: Roster; halfS: number; lang?: Lang }) {
  const [bp, setBp] = useState<BlueprintData | null>(null);
  const [writing, setWriting] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const r = await fetch(`/api/rooms/${room}/blueprint`);
      if (alive && r.ok) setBp((await r.json()) as BlueprintData);
    };
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [room]);

  if (!bp) return <div className="empty" style={{ padding: 24 }}>{t("Building the match blueprint.")}</div>;
  const translated = lang !== "en" ? bp.overview.langs?.[lang] : undefined;
  const story = translated ? { ...translated, lang } : { headline: bp.overview.headline, text: bp.overview.text, lang: "en" };

  return (
    <div className="bp">
      <Header bp={bp} roster={roster} />
      <section className="bp-overview">
        <span className="label">{t("Match overview")}</span>
        <h2 lang={story.lang}>{story.headline}</h2>
        <p lang={story.lang}>{story.text}</p>
        <span className="bp-fine">
          {bp.overview.source === "recap"
            ? "Written by the Recap agent over the engine's facts: every number and name is filled by code and checked."
            : "Written from verified match data: every number comes from the tracking and event engine."}
        </span>
        <button
          className="bp-recap"
          disabled={writing}
          onClick={async () => {
            setWriting(true);
            try {
              await fetch(`/api/rooms/${room}/recap`, { method: "POST" });
              const r = await fetch(`/api/rooms/${room}/blueprint`);
              if (r.ok) setBp((await r.json()) as BlueprintData);
            } finally {
              setWriting(false);
            }
          }}
        >
          {writing ? t("The Recap agent is writing") : bp.overview.source === "recap" ? t("Rewrite the recap") : t("Write the recap now")}
        </button>
      </section>
      <AfterMatch room={room} lang={lang} />
      <Highlights room={room} items={bp.highlights} roster={roster} />
      <Performers items={bp.performers} roster={roster} />
      <ShotExplorer shots={bp.shots} roster={roster} finishing={bp.finishing} halfS={halfS} />
      <GravitySection players={bp.gravity.players} maps={bp.gravity.maps} cellM={bp.gravity.cell_m} roster={roster} />
      <Marking items={bp.marking} roster={roster} />
      <LeverageCards items={bp.leverage} roster={roster} />
    </div>
  );
}
