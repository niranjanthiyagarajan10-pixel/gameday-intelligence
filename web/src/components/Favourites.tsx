import { useState } from "react";
import type { Roster, Side } from "../types";
import type { Prefs } from "../prefs";
import { t } from "../i18n";

/** Favourite clubs and players: a header button with a small panel of checkboxes. */
export function Favourites({ roster, prefs, update, onPitch }: { roster: Roster; prefs: Prefs; update: (p: Partial<Prefs>) => void; onPitch: string[] }) {
  const [open, setOpen] = useState(false);
  const count = prefs.clubs.length + prefs.players.length;
  const toggle = <T,>(list: T[], item: T) => (list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);

  return (
    <div className="favs">
      <button className={`set ${count ? "on" : ""}`} onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="label">{t("Favourites")}</span>
        <b>{count ? t("{n} picked", { n: count }) : t("None")}</b>
      </button>
      {open && (
        <div className="favs-panel" role="dialog" aria-label={t("Favourite clubs and players")}>
          <div className="label">{t("Clubs")}</div>
          <div className="favs-clubs">
            {(["home", "away"] as Side[]).map((side) => (
              <label key={side}>
                <input type="checkbox" checked={prefs.clubs.includes(side)} onChange={() => update({ clubs: toggle(prefs.clubs, side) })} />
                <i className="sw" style={{ background: roster.clubs[side].primary }} /> {roster.clubs[side].name}
              </label>
            ))}
          </div>
          <div className="label">{t("Players")}</div>
          <div className="favs-players">
            {(["home", "away"] as Side[]).map((side) => (
              <div key={side}>
                {onPitch
                  .filter((id) => roster.players[id]?.side === side)
                  .sort((a, b) => roster.players[a].number - roster.players[b].number)
                  .map((id) => (
                    <label key={id}>
                      <input type="checkbox" checked={prefs.players.includes(id)} onChange={() => update({ players: toggle(prefs.players, id) })} />
                      #{roster.players[id].number} {roster.players[id].short}
                    </label>
                  ))}
              </div>
            ))}
          </div>
          <button className="favs-done" onClick={() => setOpen(false)}>
            {t("Done")}
          </button>
        </div>
      )}
    </div>
  );
}
