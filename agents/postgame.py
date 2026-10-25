"""The Post-game agent: what to watch next time, for both clubs, once the match is over.

What decided the match is code: the three key moments that moved the win probability most, each with
the line the Narrator already had verified. The agent writes three look-ahead lines over the facts
(finishing against xG, styles, the next opponent and its forecast). Same checks as every agent.
"""

from __future__ import annotations

import json
from typing import Any

from agents import story

KEYS = ("look_ahead",)
LIMITS = {"look_ahead": 220}

INSTRUCTIONS = """You are the Post-game analyst for Gameday Intelligence. The match is over. Write three short
lines on what each club should watch for next time, for a fan reading after the final whistle.

Rules:
1. Write TEMPLATES. Every number and every name is a fact in curly braces, using the fact's key, for example
   {home_next_opponent}, {home_finishing}, {home_next_win}. Never type a digit, a player name or a club name.
2. Use only the facts: finishing against xG ({home_finishing} is goals minus xG), the styles, the next
   opponent, whether it is at home or away, and the forecast for it. One line about each club, one about either.
3. Never mention injuries, suspensions, managers, transfers, the crowd, trophies, records or the table.
4. Facts carry their units: {home_next_win} is already "38%". Do not add % or units after a slot.
5. Plain sentences, each under 200 characters. No em dashes. Never use he, him, his, she or her.
   Never add 's to a slot. Say "tends to settle" rather than predicting a result.
6. Reply with JSON only: {"look_ahead": ["...", "...", "..."]}
"""

BANNED = [r"injur", r"suspen", r"manager", r"\bcoach", r"transfer", r"crowd", r"troph", r"\brecords?\b",
          r"relegat", r"\btable\b", r"\bwill (win|lose|beat)\b", r"\bguarantee"]

IMPLIED: story.Implied = [
    (r"\bdraw(n|s)?\b|\bdrew\b|\blevel\b|all square", "the match was drawn", lambda t: t["score"][0] == t["score"][1]),
    (r"\bwon\b|\bbeat\b|\bvictory\b|\bdefeat(ed)?\b|\blost\b", "the match had a winner",
     lambda t: t["score"][0] != t["score"][1]),
]


def prompt(facts: dict[str, str]) -> str:
    return json.dumps({"facts": facts}, ensure_ascii=False)


def parse(text: str | None) -> dict[str, Any] | None:
    parsed = story.parse(text, KEYS)
    if parsed is None or not isinstance(parsed["look_ahead"], list):
        return None
    return {"look_ahead": parsed["look_ahead"][:3]}


def check(parts: dict[str, Any], facts: dict[str, str], names: list[str] | set[str], truths: dict[str, Any]) -> list[str]:
    reasons = story.check(parts, facts, names, truths, LIMITS, BANNED, IMPLIED)
    if len(parts.get("look_ahead", [])) < 2:
        reasons.append("write at least two look-ahead lines")
    return reasons


def fallback(facts: dict[str, str], truths: dict[str, Any] | None = None) -> dict[str, list[str]]:
    lines = []
    for side in ("home", "away"):
        if f"{side}_next_opponent" in facts:
            lines.append(f"{{{side}}} play {{{side}_next_opponent}} {{{side}_next_venue}} next, "
                         f"and the model gives them {{{side}_next_win}} to win it.")
    lines.append("Finishing against expected goals: {home} {home_finishing}, {away} {away_finishing}.")
    return {"look_ahead": lines}
