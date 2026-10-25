"""The Newsdesk agent: a match report for every fixture of the matchday, written like a newspaper.

Code computes each match's facts from the engine (data/newsdesk.json, rebuilt by `python -m app.newsdesk`):
the score, every goal with its minute and xG, red cards, the chance battle, possession, the best spell and the
player who mattered most. The agent writes the headline, standfirst, body and pull quote as templates.
"""

from __future__ import annotations

import json
from typing import Any

from agents import story

KEYS = ("headline", "standfirst", "body", "pull")
LIMITS = {"headline": 80, "standfirst": 230, "body": 620, "pull": 110}

INSTRUCTIONS = """You are the Newsdesk writer for Gameday Intelligence. Write the match report a sports
newspaper would publish at full time: a headline, a standfirst, two or three body paragraphs and a pull quote.

Rules:
1. Write TEMPLATES. Every number and every name is a fact in curly braces, using the fact's key, for example
   {home}, {goal_2_player}, {home_xg}, {spell_share}. Never type a digit, a player name or a club name.
2. Use only the facts. Tell the story: who won and why, the goals in order, the chance battle, red cards,
   the best spell and the player who mattered most. The story_hint gives the angle of the match.
3. Never mention injuries, managers, the crowd or fans, penalties, headers, corners, assists, the season,
   records or the table. Words such as won, drew, comeback, late winner, upset, red card, dominated, derby
   and clean sheet are claims: use one only when the facts support it.
4. Facts carry their units: {spell_share} is already "93%". Never add % or a unit after a slot.
   Each number means only what its key says: {spell_share} is one team's share of the threat in that spell,
   never possession, chances or control; *_possession is the ball; *_xg is chance quality. Never relabel one.
5. Headline under 70 characters, punchy. Standfirst one sentence. Each body paragraph 2 to 4 sentences.
   Pull quote one short line a designer would print large. No em dashes. Never use he, him, his,
   she or her: use the player's slot or they. Never add 's to a slot.
6. Reply with JSON only: {"headline": "...", "standfirst": "...", "body": ["...", "..."], "pull": "..."}

Example of the form (slots only, never the values): {"headline": "{goal_1_player} sets {leader} on the way",
"standfirst": "{leader} beat {trailer} {score} on a day of {home_xg} expected goals to {away_xg}.",
"body": ["{goal_1_player} struck on {goal_1_minute} from a {goal_1_xg} xG chance, and ..."],
"pull": "{spell_share} of the threat in ten minutes"}
"""


def prompt(facts: dict[str, str], hint: str) -> str:
    return json.dumps({"story_hint": hint, "facts": facts}, ensure_ascii=False)


def parse(text: str | None) -> dict[str, Any] | None:
    parsed = story.parse(text, KEYS)
    if parsed is None or not isinstance(parsed["body"], list) or isinstance(parsed["pull"], list):
        return None
    return {**parsed, "body": parsed["body"][:3]}


def check(parts: dict[str, Any], facts: dict[str, str], names: Any, truths: dict[str, Any]) -> list[str]:
    return story.check(parts, facts, names, truths, LIMITS, story.MATCH_BANNED, story.MATCH_IMPLIED)


def fallback(facts: dict[str, str], truths: dict[str, Any]) -> dict[str, Any]:
    """The template report: words only, every value a fact, correct by construction."""
    if "leader" in facts:
        headline = "{leader} beat {trailer} {score}"
        stand = "{leader} took the points against {trailer}. Expected goals finished {home_xg} to {away_xg}."
    else:
        headline = "{home} and {away} draw {score}"
        stand = "Nothing to separate {home} and {away}. Expected goals finished {home_xg} to {away_xg}."
    n = sum(1 for k in facts if k.startswith("goal_") and k.endswith("_player"))
    goals = " ".join(f"{{goal_{i}_player}} scored for {{goal_{i}_team}} on {{goal_{i}_minute}} to make it {{goal_{i}_score}}."
                     for i in range(1, n + 1))
    body = [goals or "Neither side found a way through."]
    second = "{home} had {home_possession} of the ball and {home_shots} shots; {away} had {away_shots}."
    if "red_1_player" in facts:
        second += " {red_1_player} of {red_1_team} was sent off."
    body.append(second)
    if "top_player" in facts:
        body.append("{top_player} of {top_player_team} made the biggest difference, with {top_player_leverage} leverage.")
    pull = ("{spell_team} had {spell_share} of the threat from {spell_start} to {spell_end}" if "spell_team" in facts
            else "Expected goals: {home_xg} to {away_xg}")
    return {"headline": headline, "standfirst": stand, "body": body, "pull": pull}
