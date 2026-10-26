"""Explain this moment: the facts the Explainer writes over, built from the beats found in code."""

from __future__ import annotations

from typing import Any

from engine.explain import find_beats

OUTCOME_WORD = {"goal": "goal", "saved": "save", "blocked": "block", "off_target": "miss"}
BIG_CHANCE_XG = 0.15  # goals and shots at least this good get "Explain this moment"
BIG_XG = 0.3  # "a big chance" from here
LOW_XG = 0.08  # under this, "a long shot"


def explainable(shot: dict[str, Any]) -> bool:
    return shot["outcome"] == "goal" or shot["xg"] >= BIG_CHANCE_XG


def _m(v: float | None) -> str:
    return f"{v:.0f} m" if v is not None and v >= 10 else f"{v:.1f} m"


def _defenders(n: int) -> str:
    return f"{n} defender" if n == 1 else f"{n} defenders"


# What each fact means, so the agent cannot read a distance as the wrong thing. b<N>_ keys belong to beat N.
MEANINGS = {
    "team": "the attacking club", "opponent": "the defending club", "minute": "minute of the shot",
    "xg": "expected goals of the shot", "chance": "how good the chance was, from its xG",
    "distance": "distance of the shot from goal", "angle": "how wide the goal mouth opened from the shot",
    "outcome": "what happened to the shot", "shooter": "who shot", "speed": "speed of the shot",
    "space": "distance from the shooter to the nearest defender when the shot was taken",
    "nearest_defender": "the defender nearest the shooter at the shot (not necessarily beaten)",
    "b_player": "who acts in this beat", "b_how": "how the ball was won", "b_to_goal": "where the ball was won, as distance from goal",
    "b_team": "the club awarded the set piece", "b_fouler": "who committed the foul", "b_restart": "the kind of restart",
    "b_to": "who received the pass", "b_distance": "length of the pass, or distance of the shot from goal",
    "b_bypassed": "defenders who were between the ball and goal before the pass and behind it after",
    "b_gain": "ground gained toward goal on the run", "b_tackler": "the defender whose tackle was ridden",
    "b_keeper": "the defending goalkeeper",
}


def pack(shot: dict[str, Any], events: list[dict[str, Any]], frames: list[dict[str, Any]],
         roster: dict[str, Any], names: dict[str, str], teams: dict[str, str]) -> dict[str, Any]:
    """Beats, facts and truths for one shot. Every value a fact; the agent types none of them."""
    players = roster["players"]
    side_of = {p: v["side"] for p, v in players.items()}
    keepers = {p for p, v in players.items() if v["position"] == "GK"}
    shot_ev = next((e for e in events if e.get("id") == shot["event_id"]), None)
    if shot_ev is not None:
        shot = {**shot, "end_x": shot_ev["end_x"], "end_y": shot_ev["end_y"]}
    beats = find_beats(shot, events, frames, side_of, keepers)
    team, other = shot["team"], "away" if shot["team"] == "home" else "home"
    name = lambda pid: names.get(pid or "", "")  # noqa: E731

    facts: dict[str, str] = {
        "team": teams[team], "opponent": teams[other], "minute": f"{shot['minute']}'",
        "xg": f"{shot['xg']:.2f} xG", "distance": _m(shot["distance_m"]), "angle": f"{shot['angle_deg']:.0f} degrees",
        "outcome": OUTCOME_WORD.get(shot["outcome"], shot["outcome"]), "shooter": name(shot["player"]),
    }
    if shot.get("speed_kmh"):
        facts["speed"] = f"{shot['speed_kmh']:.0f} km/h"
    if shot.get("defender_m") is not None:
        facts["space"] = _m(shot["defender_m"])
        if shot.get("defender"):
            facts["nearest_defender"] = name(shot["defender"])
    for i, b in enumerate(beats, start=1):
        p = f"b{i}_"
        bf = b["facts"]
        if b.get("player"):
            facts[p + "player"] = name(b["player"])
        if b["kind"] == "won":
            facts[p + "how"] = {"tackle": "a tackle", "interception": "an interception"}.get(bf["how"], "a loose ball")
            facts[p + "to_goal"] = f"{bf['to_goal_m']} m"
        elif b["kind"] == "foul_won":
            facts[p + "team"] = teams[team]
            if bf.get("fouler"):
                facts[p + "fouler"] = name(bf["fouler"])
        elif b["kind"] == "restart":
            facts[p + "restart"] = bf["restart"]
        elif b["kind"] == "pass":
            facts[p + "to"] = name(b["to"])
            facts[p + "distance"] = f"{bf['distance_m']} m"
            if bf["bypassed"] > 0:
                facts[p + "bypassed"] = _defenders(bf["bypassed"])
        elif b["kind"] == "carry":
            facts[p + "gain"] = f"{bf['gain_m']} m"
        elif b["kind"] == "tackle_beaten":
            facts[p + "tackler"] = name(bf["tackler"])
        elif b["kind"] == "shot":
            facts[p + "distance"] = _m(bf["distance_m"])
            if bf.get("keeper") and shot["outcome"] in ("goal", "saved"):  # a block or a miss is not the keeper's
                facts[p + "keeper"] = name(bf["keeper"])
    xg = shot["xg"]
    facts["chance"] = "a big chance" if xg >= BIG_XG else "a good chance" if xg >= 0.15 else "a half chance" if xg >= LOW_XG else "a long shot"
    truths = {"outcome": shot["outcome"], "beats": len(beats), "kinds": [b["kind"] for b in beats],
              "xg": xg, "space_m": shot.get("defender_m")}
    return {"beats": beats, "facts": {k: v for k, v in facts.items() if v}, "truths": truths, "shot": shot}
