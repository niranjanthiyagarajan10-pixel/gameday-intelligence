"""The Summarizer agent: "Catch me up". Three short points a fan who just joined can read in twenty seconds.

Code builds the facts from the live engine (score, chances, possession, scorers, red cards, who has had
the threat lately); the agent picks what matters and writes three bullets as templates over them.
"""

from __future__ import annotations

import json
from typing import Any

from agents import story

KEYS = ("bullets",)
LIMITS = {"bullets": 170}

INSTRUCTIONS = """You are the Summarizer for Gameday Intelligence. A fan has just joined the match. Catch them
up in three short points they can read in twenty seconds.

Rules:
1. Write TEMPLATES. Every number and every name is a fact in curly braces, using the fact's key, for example
   {leader}, {goal_1_player}, {last10_share}. Never type a digit, a player name or a club name.
2. Point one: the state of the match and why. Point two: the player or moment that shaped it. Point three:
   what is happening right now (who has had the threat lately, a red card, the win chance).
3. Use only the facts. Never mention injuries, managers, the crowd, penalties, headers, corners, assists,
   the season or records. Words such as lead, level, comeback, red card, dominate and late winner are claims:
   use one only when the facts support it.
4. Facts carry their units: {home_win} is already "74%". Never add % or a unit after a slot.
5. Each point one sentence, under 150 characters. No em dashes. Never use he, him, his, she or her.
   Never add 's to a slot.
6. Reply with JSON only: {"bullets": ["...", "...", "..."]}
"""


def prompt(facts: dict[str, str]) -> str:
    return json.dumps({"facts": facts}, ensure_ascii=False)


def parse(text: str | None) -> dict[str, Any] | None:
    parsed = story.parse(text, KEYS)
    if parsed is None or not isinstance(parsed["bullets"], list):
        return None
    return {"bullets": parsed["bullets"][:3]}


def check(parts: dict[str, Any], facts: dict[str, str], names: Any, truths: dict[str, Any]) -> list[str]:
    reasons = story.check(parts, facts, names, truths, LIMITS, story.MATCH_BANNED, story.MATCH_IMPLIED)
    if len(parts.get("bullets", [])) < 3:
        reasons.append("write three points")
    return reasons


def fallback(facts: dict[str, str], truths: dict[str, Any]) -> dict[str, list[str]]:
    """Three template points, words only, every value a fact."""
    first = ("{leader} lead {trailer} {score} at {minute}." if "leader" in facts
             else "It is {score} between {home} and {away} at {minute}.")
    goals = [int(k.split("_")[1]) for k in facts if k.startswith("goal_") and k.endswith("_player")]
    if goals:
        n = max(goals)
        second = (f"The latest goal: {{goal_{n}_player}} for {{goal_{n}_team}} on {{goal_{n}_minute}}, "
                  f"a chance worth {{goal_{n}_xg}} xG.")
    elif "top_player" in facts:
        second = "{top_player} of {top_player_team} has made the biggest difference so far, {top_player_leverage} leverage."
    else:
        second = "Expected goals so far: {home} {home_xg}, {away} {away_xg}."
    third = ("{last10_team} have had {last10_share} of the threat in the last ten minutes." if "last10_team" in facts
             else "Win chance now: {home} {home_win}, the draw {draw}, {away} {away_win}.")
    return {"bullets": [first, second, third]}
