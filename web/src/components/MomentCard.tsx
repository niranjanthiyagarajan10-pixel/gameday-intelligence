import { useState } from "react";
import type { Audience, Card, Roster } from "../types";
import { KIND_LABEL, evidenceRows, sideColor } from "../format";
import { shotHref } from "../route";
import { cardText, type Lang } from "../prefs";

const SHOT_KINDS = new Set(["goal", "low_xg_goal", "big_chance"]);

interface Props {
  card: Card;
  roster: Roster;
  depth: Audience;
  open: boolean;
  lang?: Lang;
  mine?: "club" | "player" | null;
}

const FORMULAS: Record<string, string> = {
  leverage_swing: "leverage = (value actual - value opposite) x 10, value = P(win) + P(draw) / 2",
  goal: "shot leverage = (goal - xG) x swing x 10",
  low_xg_goal: "shot leverage = (goal - xG) x swing x 10",
  big_chance: "xG = sigmoid(b0 + b1 distance + b2 angle + b3 header + b4 pressure)",
  red_card: "value change with one player fewer, Poisson win model",
  shape_change: "line height = mean distance of the 4 deepest outfield players from own goal",
  control_flip: "control = possession share x pass completion, last 5 min",
  top_speed: "speed = distance between tracking frames / time, smoothed over 3 frames",
};

export function MomentCard({ card, roster, depth, open: openByDefault, lang = "en", mine = null }: Props) {
  const [open, setOpen] = useState(openByDefault);
  const [own, setOwn] = useState<Audience | null>(null);
  const audience = own ?? depth;
  const cue = card.cues[audience];
  const shown = cardText(card, audience, lang);
  const m = card.moment;
  const heroClass = card.hero.value.startsWith("+") ? "up" : card.hero.value.startsWith("-") ? "down" : "";

  return (
    <div className={`card${mine ? " mine" : ""}`} style={{ borderLeftColor: sideColor(roster, m.team) }}>
      <div className="top">
        <span className="kind">
          {KIND_LABEL[m.kind] ?? m.kind}
          {mine && <em className="mine-tag">{mine === "player" ? "Your player" : "Your club"}</em>}
        </span>
        <span className="min num">{m.minute}'</span>
      </div>
      <p lang={shown.lang}>{shown.text}</p>
      {lang !== "en" && shown.lang === "en" && <span className="written">English until the translation is verified</span>}
      <div className="big">
        <b className={`num ${heroClass}`}>{card.hero.value}</b>
        <span className="label">{card.hero.label}</span>
      </div>
      <div className="acts">
        <button onClick={() => setOpen(!open)}>{open ? "Hide evidence" : "Show evidence"}</button>
        <button onClick={() => setOwn(audience === "casual" ? "analyst" : "casual")}>
          {audience === "casual" ? "Go deeper" : "Explain simply"}
        </button>
        {SHOT_KINDS.has(m.kind) && m.event_ids[0] && (
          <a className="actlink" href={shotHref(m.event_ids[0])}>
            Watch replay
          </a>
        )}
        <span className="written" title={card.sources?.[audience] === "narrator" ? "Written by the Narrator agent, checked by the Verifier" : "Template text, filled from the evidence"}>
          {card.sources?.[audience] === "narrator" ? "Narrator" : "Template"}
        </span>
        {cue.verified && <span className="verified">Verified</span>}
      </div>
      {open && (
        <div className="evidence">
          <table>
            <tbody>
              {evidenceRows(m.evidence, roster).map(([k, v]) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td>{v}</td>
                </tr>
              ))}
              {m.event_ids.length > 0 && (
                <tr>
                  <td>Events</td>
                  <td>{m.event_ids.map((id) => id.split("-").pop()).join(", ")}</td>
                </tr>
              )}
            </tbody>
          </table>
          {FORMULAS[m.kind] && <div className="formula">{FORMULAS[m.kind]}</div>}
        </div>
      )}
    </div>
  );
}
