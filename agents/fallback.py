"""Template cards for every kind of key moment, with no model involved.

These are what fans see before the agents answer, and whenever a model call fails or is slow.
Templates only hold words. Every number and name is a slot filled here from the moment's evidence,
so a fallback card is correct by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.models import Audience, CueKind, Moment, OverlayEvent, Side, template_slots

TEMPLATES: dict[str, dict[Audience, str]] = {
    "goal": {
        "casual": "{player} scores for {team}. It is {score}, and {team} win chance goes from {wp_before} to {wp_after}.",
        "analyst": "{player} converts a {xg} xG chance. {score}. {team} win probability {wp_before} to {wp_after}, leverage {leverage}.",
    },
    "low_xg_goal": {
        "casual": "What a finish from {player}. A chance worth only {xg} xG, and it is {score}.",
        "analyst": "{player} beats the model: a {xg} xG chance converted. {score}. {team} win probability {wp_before} to {wp_after}.",
    },
    "red_card": {
        "casual": "{player} is sent off. {team} win chance falls from {wp_before} to {wp_after}.",
        "analyst": "Red card for {player}. {team} play on a player short. Win probability {wp_before} to {wp_after}, leverage {leverage}.",
    },
    "big_chance": {
        "casual": "Big chance for {player}, worth {xg} xG, but no goal.",
        "analyst": "{player} misses a {xg} xG chance. A goal would have taken {team} to {wp_if_scored} win probability.",
    },
    "leverage_swing.tackle": {
        "casual": "{player} wins the ball. {team} win chance is {wp_after} now, against {wp_opposite} if the tackle had been lost.",
        "analyst": "Tackle by {player} worth {leverage} leverage. {team} win probability {wp_after} against {wp_opposite} had it gone the other way.",
    },
    "leverage_swing.interception": {
        "casual": "{player} reads it and steals the ball. {team} win chance is {wp_after}, against {wp_opposite} if the pass had arrived.",
        "analyst": "Interception by {player} worth {leverage} leverage. {team} win probability {wp_after} against {wp_opposite} had the pass arrived.",
    },
    "leverage_swing.pass": {
        "casual": "{player} finds a difficult pass. {team} win chance is {wp_after}, against {wp_opposite} if it had been cut out.",
        "analyst": "Pass by {player} worth {leverage} leverage, completed against the odds. {team} win probability {wp_after} against {wp_opposite}.",
    },
    "leverage_swing.misplaced_pass": {
        "casual": "{player} gives the ball away. {team} win chance moves to {wp_after}.",
        "analyst": "Misplaced pass by {player}. {team} gain {leverage} leverage: win probability {wp_after} against {wp_opposite} had it been kept.",
    },
    "top_speed": {
        "casual": "{player} hits {speed}, the fastest run of the match.",
        "analyst": "Match top speed: {player} at {speed}, measured from tracking frames.",
    },
    "control_flip": {
        "casual": "{team} take control of the game.",
        "analyst": "{team} now control the match. Control index {control}, chaos index {chaos}.",
    },
    "control_flip.chaos": {
        "casual": "The game has turned chaotic. The ball keeps changing hands.",
        "analyst": "Chaos index up to {chaos}: turnovers well above the league rate. Control index {control}.",
    },
    "shape_change": {
        "casual": "{team} switch to a {shape}. Their back line now sits {line} from goal.",
        "analyst": "{team} shape change from {shape_from} to {shape}. Line height {line}, compactness {compactness}, {pressers} pressers near the ball.",
    },
}

CUE_KIND: dict[str, CueKind] = {
    "goal": "goal",
    "low_xg_goal": "goal",
    "red_card": "red_card",
    "big_chance": "shot_quality",
    "leverage_swing": "key_moment",
    "top_speed": "player_milestone",
    "control_flip": "control_chaos",
    "shape_change": "shape_change",
}

SHAPES = {"low_block": "low block", "mid_block": "mid block", "high_press": "high press"}


@dataclass(frozen=True)
class Hero:
    """The one big number a card shows."""

    value: str
    label: str


def pct(p: float | int | str) -> str:
    return f"{round(float(p) * 100)}%"


def signed(v: float | int | str, digits: int = 2) -> str:
    return f"{float(v):+.{digits}f}"


def moment_time(m: Moment) -> float:
    return float(m.state_ref.rsplit("@", 1)[1])


def template_key(m: Moment) -> str:
    if m.kind == "leverage_swing":
        action = str(m.evidence.get("action", "tackle"))
        key = f"leverage_swing.{action}"
        return key if key in TEMPLATES else "leverage_swing.tackle"
    if m.kind == "control_flip" and m.evidence.get("now_in_control") == "nobody":
        return "control_flip.chaos"
    return m.kind


def slots_for(m: Moment, names: dict[str, str], teams: dict[Side, str]) -> dict[str, str]:
    """Every value a template may use, formatted by code. Unused ones are dropped later."""
    ev = m.evidence
    team_side = m.team or ("home" if ev.get("now_in_control") == "home" else "away")
    player_id = str(ev.get("player", m.players[0] if m.players else ""))
    slots = {
        "player": names.get(player_id, player_id),
        "team": teams.get(team_side, ""),
        "minute": f"{m.minute}'",
        "leverage": signed(m.leverage),
    }
    for key in ("wp_before", "wp_after", "wp_opposite", "wp_if_scored"):
        if key in ev:
            slots[key] = pct(ev[key])
    if "xg" in ev:
        slots["xg"] = f"{float(ev['xg']):.2f}"
    if "score" in ev:
        slots["score"] = str(ev["score"])
    if "speed_kmh" in ev:
        slots["speed"] = f"{float(ev['speed_kmh']):.1f} km/h"
    if "control_index" in ev:
        slots["control"] = f"{float(ev['control_index']):.2f}"
        slots["chaos"] = f"{float(ev['chaos_index']):.2f}"
    if "to" in ev:
        slots["shape"] = SHAPES.get(str(ev["to"]), str(ev["to"]))
        slots["shape_from"] = SHAPES.get(str(ev.get("from", "")), str(ev.get("from", "")))
        slots["line"] = f"{float(ev['line_height_m']):.0f} m"
        slots["compactness"] = f"{float(ev['compactness_m2']):.0f} sq m"
        slots["pressers"] = f"{float(ev['pressers']):.1f}"
    return slots


def hero_for(m: Moment) -> Hero:
    ev = m.evidence
    if m.kind in ("goal", "low_xg_goal", "red_card") and "wp_after" in ev:
        return Hero(f"{(float(ev['wp_after']) - float(ev['wp_before'])) * 100:+.0f}", "pts win chance")
    if m.kind == "leverage_swing" and "wp_opposite" in ev:
        return Hero(f"{(float(ev['wp_after']) - float(ev['wp_opposite'])) * 100:+.0f}", "pts win chance")
    if m.kind == "big_chance":
        return Hero(f"{float(ev['xg']):.2f}", "xG")
    if m.kind == "top_speed":
        return Hero(f"{float(ev['speed_kmh']):.1f}", "km/h")
    if m.kind == "shape_change":
        return Hero(f"{float(ev['line_height_m']):.0f} m", "line height")
    if m.kind == "control_flip":
        if ev.get("now_in_control") == "nobody":
            return Hero(f"{float(ev['chaos_index']):.2f}", "chaos index")
        return Hero(f"{float(ev['control_index']):.2f}", "control index")
    return Hero(signed(m.leverage), "leverage")


def fallback_cue(
    m: Moment,
    audience: Audience,
    names: dict[str, str],
    teams: dict[Side, str],
    match_id: str,
    lang: str = "en",
) -> OverlayEvent:
    template = TEMPLATES[template_key(m)][audience]
    available = slots_for(m, names, teams)
    used = {k: available[k] for k in template_slots(template)}
    return OverlayEvent(
        cue_id=m.moment_id.replace("-mo-", "-cue-") + f"-{audience}",
        match_id=match_id,
        t_start=moment_time(m) + 1.0,
        duration_s=8.0,
        kind=CUE_KIND[m.kind],
        audience=audience,
        club=m.team,
        lang=lang,  # type: ignore[arg-type]
        template=template,
        slots=used,
        verified=True,
        source_claims=[],
        evidence_ref=m.moment_id,
    )
