"""The Explainer agent: "Explain this moment". One line for each beat of the move, then why it worked.

Code finds the beats from tracking and events (engine/explain.py) and turns them into facts, each beat's
keys starting b1_, b2_ and so on. The agent writes one line per beat as a template over that beat's
facts, in order, and a closing line on why the chance came about. The replay freezes on each beat
while its line is read.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agents import story

KEYS = ("lines", "why")
LIMITS = {"lines": 150, "why": 190}

INSTRUCTIONS = """You are the Explainer for Gameday Intelligence. A fan has asked how a chance came about. The
replay will freeze on each beat of the move while your line for that beat is read aloud, like a TV analyst
drawing on the screen.

Rules:
1. Write TEMPLATES. Every number and every name is a fact in curly braces, using the fact's key, for example
   {b1_player}, {b2_bypassed}, {xg}. Never type a digit, a player name or a club name.
2. Write exactly one line per beat, in the order given. The line for beat N uses only the b<N>_ facts and the
   shared facts (no b prefix). Never mention a later beat early.
3. Then one line, "why": what made the chance what it was (the space, the defenders taken out, the angle,
   the distance), ending with how good it was using {chance}. "meanings" says what each fact measures; b_ keys
   apply to every beat. Use a fact only for what it means. Never claim one thing caused another: no gave,
   created, led to, allowed, set up, thanks to or because. State each fact on its own, for example
   "{shooter} has {space} to the nearest defender and an angle of {angle}: {chance}, worth {xg}." Write in full grammatical sentences.
4. Use only the facts. Each beat has a "kind": won (ball won), foul_won, restart, pass, carry (a run with the
   ball), tackle_beaten, shot. Describe only that. Never mention injuries, managers, the crowd, penalties,
   headers, volleys, the season or records. Say scored, goal or finish only when {outcome} is a goal; saved only
   when it was saved.
5. Facts carry their units: {b2_distance} is already "24 m", {xg} is already "0.31 xG". Never add a unit after a slot.
6. Each line one short spoken sentence, under 130 characters. Present tense, like live analysis. No em dashes.
   Never use he, him, his, she or her. Never add 's to a slot.
7. Reply with JSON only: {"lines": ["...", "..."], "why": "..."}
"""


def prompt(facts: dict[str, str], kinds: list[str], meanings: dict[str, str]) -> str:
    return json.dumps({"beats": [{"beat": i + 1, "kind": k} for i, k in enumerate(kinds)], "facts": facts,
                       "meanings": meanings}, ensure_ascii=False)


def parse(text: str | None) -> dict[str, Any] | None:
    parsed = story.parse(text, KEYS)
    if parsed is None or not isinstance(parsed["lines"], list) or not isinstance(parsed["why"], str):
        return None
    return parsed


BANNED = story.MATCH_BANNED + [r"\bgoalkeeper error\b", r"\bdeflect"]


def _implied(t: dict[str, Any]) -> story.Implied:
    return [
        (r"\bscor(e|es|ed|ing)\b|\ba goal\b|\bfinish(es|ed)\b|\bnet(s|ted)?\b|back of the net|\bfind(s)? the (net|corner)\b",
         "the shot went in", lambda _: t["outcome"] == "goal"),
        (r"\bsav(e|es|ed)\b|\bstop(s|ped)?\b|\bdenie(s|d)\b", "the keeper saved it", lambda _: t["outcome"] == "saved"),
        (r"\bblock(s|ed)?\b", "the shot was blocked", lambda _: t["outcome"] == "blocked"),
        (r"\bclear(-cut)? chance|\bbig chance|\bgreat chance|\bsitter\b|\bgilt|\beasy\b|\bsimple\b",
         "a big chance", lambda _: t["xg"] >= 0.3),
        (r"hopeful|speculative|\bunlikely\b|long odds|low odds|\bdifficult\b|\btough\b|\bhalf[- ]chance|long shot",
         "a poor chance", lambda _: t["xg"] < 0.15),
        (r"plenty of (space|room|time)|\bunmarked\b|\bfree\b|time and space|all alone|\bopen\b",
         "the shooter had space", lambda _: (t["space_m"] or 0) >= 3.0),
        (r"\btight\b|crowded|closed down|under pressure|no space|little space|\bsmall\b|\bnarrow\b",
         "the shooter had little space", lambda _: t["space_m"] is not None and t["space_m"] < 2.0),
        (r"\bmiss(es|ed)?\b|\bwide\b|\bover the bar\b|\boff target\b", "the shot missed", lambda _: t["outcome"] == "off_target"),
    ]


def check(parts: dict[str, Any], facts: dict[str, str], names: Any, truths: dict[str, Any]) -> list[str]:
    reasons = story.check(parts, facts, names, truths, LIMITS, BANNED, _implied(truths))
    lines = parts.get("lines", [])
    n = truths["beats"]
    if len(lines) != n:
        reasons.append(f"write exactly {n} lines, one per beat")
    # Time order: the line for beat N may not use another beat's facts.
    for i, line in enumerate(lines):
        other = sorted({int(m) for m in re.findall(r"\{b(\d+)_", line)} - {i + 1})
        if other:
            reasons.append(f"line {i + 1}: uses beat {other[0]} facts; each line tells only its own beat")
    # Cause and effect: the facts say what happened, never that one thing caused another.
    texts = [("why", parts.get("why", ""))] + [(f"line {i + 1}", x) for i, x in enumerate(lines)]
    for where, text in texts:
        found = CAUSAL.search(re.sub(r"\{[^{}]*\}", " ", text).lower())
        if found:
            reasons.append(f'{where}: "{found.group(0)}" claims one thing caused another, which the facts do not say; '
                           "state each fact on its own")
    return reasons


CAUSAL = re.compile(
    r"\b(gave|gives|giving|created|creates|creating|led to|leads to|leading to|resulted in|results in|resulting in"
    r"|allowed|allows|allowing|enabled|enables|enabling|thanks to|because|due to|as a result|which meant|meaning"
    r"|opened up|opens up|opening up|set up|sets up|setting up|earned|earns|forced|forces|forcing|caused|causes"
    r"|helped|helps|helping|paved)\b")


def _line(kind: str, n: int, facts: dict[str, str]) -> str:
    b = f"b{n}_"
    has = lambda k: b + k in facts  # noqa: E731
    if kind == "won":
        return f"{{{b}player}} wins the ball with {{{b}how}}, {{{b}to_goal}} from goal."
    if kind == "foul_won":
        return f"{{{b}player}} is fouled and {{{b}team}} get a set piece."
    if kind == "restart":
        return f"It starts from a {{{b}restart}} taken by {{{b}player}}."
    if kind == "pass":
        if has("bypassed"):
            return f"{{{b}player}} finds {{{b}to}} with a {{{b}distance}} pass that takes {{{b}bypassed}} out of the game."
        return f"{{{b}player}} plays it to {{{b}to}}, {{{b}distance}}."
    if kind == "carry":
        return f"{{{b}player}} carries it {{{b}gain}} toward goal."
    if kind == "tackle_beaten":
        return f"{{{b}player}} rides the challenge from {{{b}tackler}}."
    return f"{{{b}player}} shoots from {{{b}distance}}, a chance worth {{xg}}."


def fallback(facts: dict[str, str], truths: dict[str, Any]) -> dict[str, Any]:
    lines = [_line(k, i + 1, facts) for i, k in enumerate(truths["kinds"])]
    why = ("With {space} to the nearest defender and an angle of {angle}, it was {chance}, worth {xg}."
           if "space" in facts else "From {distance} with an angle of {angle}, it was {chance}, worth {xg}.")
    return {"lines": lines, "why": why}
