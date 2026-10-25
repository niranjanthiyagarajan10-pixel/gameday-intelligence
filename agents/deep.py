"""The In-depth Analyst: every fifteen minutes, and after a goal or a red card, one card that explains
why the match is going the way it is. Code measures the last fifteen minutes against the fifteen before,
each team's defensive shape and the player pulling defenders around; the agent writes the explanation.
"""

from __future__ import annotations

import json
from typing import Any

from agents import story

KEYS = ("headline", "text")
LIMITS = {"headline": 80, "text": 480}
EVERY_MINUTES = 15
AFTER_EVENT_GAP_MINUTES = 5

INSTRUCTIONS = """You are the In-depth Analyst for Gameday Intelligence. Every fifteen minutes you explain to a
data-hungry fan WHY the match is going the way it is. One headline and one short paragraph.

Rules:
1. Write TEMPLATES. Every number and every name is a fact in curly braces, using the fact's key, for example
   {home_threat_now}, {away_line}, {gravity_player}. Never type a digit, a player name or a club name.
2. Explain cause and effect: who has had the threat in this window and how it compares with the fifteen
   minutes before, how each team's shape (block, line height, compactness, pressers) explains it, and the
   player pulling defenders out of position (gravity). Two to four sentences.
3. Use only the facts. Never mention injuries, managers, the crowd, penalties, headers, corners, assists or
   the season. Words such as dominate, high press, low block, sitting deep, turned the tide, lead, level and
   red card are claims: use one only when the facts support it.
4. Facts carry their units: {home_line} is already "44 m", {home_threat_now} is already "62%". Never add
   a unit or % after a slot.
5. Each number belongs to the fact it names: {gravity_value} is the gravity of {gravity_player} only;
   *_threat_now is a share of the threat, never possession. Never pin a number on another player or measure.
6. No em dashes. Never use he, him, his, she or her: use the player's slot or they. Never add 's to a slot.
7. Reply with JSON only: {"headline": "...", "text": "..."}
"""


def _shape(t: dict[str, Any], state: str) -> bool:
    return state in (t.get("home_shape"), t.get("away_shape"))


IMPLIED: story.Implied = [
    *story.MATCH_IMPLIED,
    (r"high press|pressing high|press(es|ing)? high", "a side is in a high press", lambda t: _shape(t, "high_press")),
    (r"low block|sit(s|ting)? deep|deep block|park(ed|ing) the bus", "a side sits in a low block", lambda t: _shape(t, "low_block")),
    (r"mid block", "a side is in a mid block", lambda t: _shape(t, "mid_block")),
    (r"turn(ed|s)? the tide|swung|momentum (has )?shift|taken over|grown into", "a side's share of the threat has risen",
     lambda t: t.get("rising") is not None),
]


def prompt(facts: dict[str, str]) -> str:
    return json.dumps({"facts": facts}, ensure_ascii=False)


def parse(text: str | None) -> dict[str, Any] | None:
    return story.parse(text, KEYS)


def check(parts: dict[str, Any], facts: dict[str, str], names: Any, truths: dict[str, Any]) -> list[str]:
    return story.check(parts, facts, names, truths, LIMITS, story.MATCH_BANNED, IMPLIED)


def fallback(facts: dict[str, str], truths: dict[str, Any]) -> dict[str, str]:
    """The template card: words only, every value a fact."""
    lines = []
    if "home_threat_now" in facts:
        lines.append("From {window_start} to {window_end}, {home} had {home_threat_now} of the threat and "
                     "{away} {away_threat_now}.")
    if "home_threat_before" in facts:
        lines.append("In the fifteen minutes before it was {home_threat_before} to {away_threat_before}.")
    for side in ("home", "away"):
        if f"{side}_shape" in facts:
            lines.append(f"{{{side}}} are in a {{{side}_shape}}, back line {{{side}_line}} from goal.")
    if "gravity_player" in facts:
        lines.append("{gravity_player} pulls the most defenders out of position, gravity {gravity_value}.")
    return {"headline": "{home} v {away}, {window_start} to {window_end}", "text": " ".join(lines) or "Expected goals: {home} {home_xg}, {away} {away_xg}."}
