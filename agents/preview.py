"""The Preview agent: the story before kickoff, from the table, form, head to head and the forecast.

Code picks the facts, the players to watch and the forecast; the agent writes a headline and a short
story around them as templates. Checked like every other agent; the template preview is the fallback.
"""

from __future__ import annotations

import json
from typing import Any

from agents import story

KEYS = ("headline", "story")
LIMITS = {"headline": 80, "story": 650}

INSTRUCTIONS = """You are the Preview writer for Gameday Intelligence. Before kickoff you tell a fan what to
expect from the match: a headline and a short story a broadcast presenter could read.

Rules:
1. Write TEMPLATES. Every number and every name is a fact in curly braces, using the fact's key, for example
   {home}, {home_position}, {forecast_home}. Never type a digit, a player name or a club name.
2. Use only the facts. Say why the match matters: table positions, form, how the two styles meet, the
   head to head, the forecast. Never mention injuries, suspensions, managers, transfers, the crowd, the
   weather, trophies, records or relegation.
3. Words such as unbeaten, winless, in form, top of the table, bottom, derby, rivals, favourites and
   underdogs are claims. Use one only when the facts support it: form is listed latest first.
4. Facts carry their units: {forecast_home} is already "56%". Form like "W W D W L" is for reading, not quoting.
5. Plain, vivid sentences. No em dashes. Never use he, him, his, she or her: use the slot or they.
   Never add 's to a slot. Headline under 70 characters, story 3 to 4 sentences.
6. Reply with JSON only: {"headline": "...", "story": "..."}
"""

BANNED = [r"injur", r"suspen", r"manager", r"\bcoach", r"transfer", r"crowd", r"weather", r"sold[- ]out",
          r"all[- ]time", r"\brecords?\b", r"troph", r"champions", r"relegat", r"promot", r"\bhead(s|er|ers)?\b"]


def _any(truths: dict[str, Any], key: str) -> bool:
    return bool(truths.get(f"home_{key}") or truths.get(f"away_{key}"))


IMPLIED: story.Implied = [
    (r"\bunbeaten\b", "a side is unbeaten in its last five", lambda t: _any(t, "unbeaten")),
    (r"\bwinless\b|without a win", "a side has not won in its last five", lambda t: _any(t, "winless")),
    (r"top of the (table|league)|league leaders|\btable[- ]toppers\b", "a side is top",
     lambda t: 1 in (t.get("home_position"), t.get("away_position"))),
    (r"bottom of the (table|league)|rock bottom|\bbottom side\b", "a side is bottom",
     lambda t: 10 in (t.get("home_position"), t.get("away_position"))),
    (r"\bderby\b|\brivals?\b|rivalry", "it is a derby", lambda t: bool(t.get("derby"))),
    (r"\bfavou?rites?\b|\bunderdogs?\b", "one side is the clear favourite", lambda t: t.get("favourite") is not None),
]


def prompt(facts: dict[str, str], watch: list[dict[str, Any]]) -> str:
    return json.dumps({"facts": facts, "players_to_watch_shown_beside_your_story": [p["name"] for p in watch]},
                      ensure_ascii=False)


def parse(text: str | None) -> dict[str, Any] | None:
    return story.parse(text, KEYS)


def check(parts: dict[str, Any], facts: dict[str, str], names: list[str] | set[str], truths: dict[str, Any]) -> list[str]:
    return story.check(parts, facts, names, truths, LIMITS, BANNED, IMPLIED)


def fallback(facts: dict[str, str], truths: dict[str, Any]) -> dict[str, str]:
    """The template preview: words only, every value a fact, correct by construction."""
    lines = ["{home} sit {home_position} on {home_points} points; {away} are {away_position} on {away_points}."]
    if "h2h_last" in facts:
        lines.append("Last time they met it finished {h2h_last}.")
    lines.append("The model gives {home} {forecast_home}, the draw {forecast_draw} and {away} {forecast_away}.")
    headline = "{home} v {away}: the derby" if truths.get("derby") else "{home} host {away}"
    return {"headline": headline, "story": " ".join(lines)}
