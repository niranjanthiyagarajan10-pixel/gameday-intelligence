import { useState } from "react";
import type { Audience, Card, Roster } from "../types";
import { KIND_LABEL, evidenceRows, sideColor } from "../format";

interface Props {
  card: Card;
  roster: Roster;
  depth: Audience;
  open: boolean;
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

export function MomentCard({ card, roster, depth, open: openByDefault }: Props) {
  const [open, setOpen] = useState(openByDefault);
  const [own, setOwn] = useState<Audience | null>(null);
  const audience = own ?? depth;
  const cue = card.cues[audience];
  const m = card.moment;
  const heroClass = card.hero.value.startsWith("+") ? "up" : card.hero.value.startsWith("-") ? "down" : "";

  return (
    <div className="card" style={{ borderLeftColor: sideColor(roster, m.team) }}>
      <div className="top">
        <span className="kind">{KIND_LABEL[m.kind] ?? m.kind}</span>
        <span className="min num">{m.minute}'</span>
      </div>
      <p>{cue.text}</p>
      <div className="big">
        <b className={`num ${heroClass}`}>{card.hero.value}</b>
        <span className="label">{card.hero.label}</span>
      </div>
      <div className="acts">
        <button onClick={() => setOpen(!open)}>{open ? "Hide evidence" : "Show evidence"}</button>
        <button onClick={() => setOwn(audience === "casual" ? "analyst" : "casual")}>
          {audience === "casual" ? "Go deeper" : "Explain simply"}
        </button>
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
