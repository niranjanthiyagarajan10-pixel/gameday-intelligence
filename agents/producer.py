"""The Producer agent: the Highlights reel. Code picks and orders the clips; the agent writes the intro and outro.

Code chooses the clips (app/producer.py): every goal, then the best other big chances by xG and win
probability swing, in match order. Each clip is then told by the Explainer's verified story. The Producer
writes two lines over the match facts: an intro before the first clip and an outro after the last. Both
are templates; code fills every number and name, and the same checks as every match story apply.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agents import story
from agents.explainer import CAUSAL

KEYS = ("intro", "outro")
LIMITS = {"intro": 170, "outro": 200}

INSTRUCTIONS = """You are the Producer for Gameday Intelligence. You open and close a highlights reel of one
match. The reel plays the clips in match order; you write only the line before them and the line after them.
Both are read aloud over a title card.

Rules:
1. Write TEMPLATES. Every number and every name is a fact in curly braces, using the fact's key, for example
   {home}, {score}, {goal_1_player}, {swing}. Never type a digit, a player name or a club name.
2. "intro": one sentence that sets the scene: the clubs, the score and how many clips follow using {clips}.
3. "outro": one or two sentences that close the reel: the expected goals for each side and the biggest win
   probability swing ({swing}, by {swing_player} in {swing_minute}) when those facts exist.
4. Use only the facts. Say won, lead, comeback, late winner, red card or derby only when the facts support it.
   Never claim one thing caused another: no gave, created, led to, allowed, set up, thanks to or because.
   Never mention injuries, managers, the crowd, penalties, headers, the season or records.
5. Facts carry their units. Never add a unit after a slot. No em dashes. Never use he, him, his, she or her.
   Never add 's to a slot.
6. Reply with JSON only: {"intro": "...", "outro": "..."}
"""


def prompt(facts: dict[str, str]) -> str:
    return json.dumps({"facts": facts}, ensure_ascii=False)


def parse(text: str | None) -> dict[str, Any] | None:
    parsed = story.parse(text, KEYS)
    if parsed is None or not all(isinstance(parsed[k], str) for k in KEYS):
        return None
    return parsed


def check(parts: dict[str, Any], facts: dict[str, str], names: Any, truths: dict[str, Any]) -> list[str]:
    reasons = story.check(parts, facts, names, truths, LIMITS, story.MATCH_BANNED, story.MATCH_IMPLIED)
    for where in KEYS:
        found = CAUSAL.search(re.sub(r"\{[^{}]*\}", " ", parts.get(where, "")).lower())
        if found:
            reasons.append(f'{where}: "{found.group(0)}" claims one thing caused another, which the facts do not say; '
                           "state each fact on its own")
    return reasons


def fallback(facts: dict[str, str], truths: dict[str, Any]) -> dict[str, Any]:
    when = "at full time" if truths["finished"] else "after {minute}"
    intro = "{home} {home_goals}, {away} {away_goals} " + when + ". The reel has {clips} from the match."
    outro = "Expected goals: {home} {home_xg}, {away} {away_xg}."
    if "swing" in facts:
        outro += " The biggest swing in win probability was {swing}, from {swing_player} in {swing_minute}."
    return {"intro": intro, "outro": outro}
