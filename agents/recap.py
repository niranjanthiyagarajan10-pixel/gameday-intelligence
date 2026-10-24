"""The Recap agent: writes the match report for the Match Blueprint (studio, broadcast or streaming).

It gets the facts the engine computed, each with a slot name, plus the plain word-template version of
the story for reference. It writes a headline and a paragraph as templates over those slots, so every
number and name in the recap is filled by code. The draft is checked before use; on any failure the
word-template overview stays.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from agents.verifier import EM_DASH, GENDERED, UNVERIFIABLE
from engine.models import template_slots

MAX_HEADLINE = 90
MAX_TEXT = 1100

INSTRUCTIONS = """You are the Recap writer for Gameday Intelligence. You write the match report a studio
presenter could read: a short headline and one paragraph that tells the story of the match, not a list.

Rules:
1. Write TEMPLATES. Every number and every name comes from the facts, as a slot in curly braces using
   the fact's key, for example {result_win_winner} or {top_scorer_xg}. Never type a digit or a name.
2. Use only the facts given. Say what mattered and why: the result, who decided it, the chance battle,
   the best spell, red cards, and the inside-the-game numbers.
3. Never mention headers, penalties, set pieces, assists, the season, careers, injuries or the crowd.
4. Facts carry their own units: {x_share} is already "93%" and {x_xg} is a plain number, so write
   "{x_share} of the threat", never "{x_share}%". Count facts are bare numbers: write "{x_goals} goals".
5. Plain, vivid sentences. No em dashes. Never use he, him, his, she or her for a player: use the player's slot or they. Headline under 70 characters, paragraph 3 to 6 sentences.
6. Reply with JSON only: {"headline": "...", "text": "..."}
"""


def prompt(facts: dict[str, str], reference: str, finished: bool) -> str:
    return json.dumps({"status": "full time" if finished else "in play", "facts": facts,
                       "reference_story": reference}, ensure_ascii=False)


def parse(text: str | None) -> tuple[str, str] | None:
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if start >= 0 else None
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    head, body = data.get("headline"), data.get("text")
    if not (isinstance(head, str) and isinstance(body, str) and head.strip() and body.strip()):
        return None
    return head.strip(), body.strip()


def check(headline: str, text: str, facts: dict[str, str], names: Iterable[str]) -> list[str]:
    reasons = []
    for label, template, limit in (("headline", headline, MAX_HEADLINE), ("text", text, MAX_TEXT)):
        try:
            slots = template_slots(template)
        except ValueError as e:
            reasons.append(f"{label}: {e}")
            continue
        unknown = sorted(set(slots) - facts.keys())
        if unknown:
            reasons.append(f"{label}: unknown slots " + ", ".join(f"{{{s}}}" for s in unknown))
        literal = re.sub(r"\{[^{}]*\}", " ", template)
        if re.search(r"\d", literal):
            reasons.append(f"{label}: numbers must be slots")
        for name in sorted({n for n in names if n and len(n) >= 3}, key=len, reverse=True):
            if re.search(rf"\b{re.escape(name)}\b", literal):
                reasons.append(f'{label}: names must be slots, remove "{name}"')
                break
        for pattern in UNVERIFIABLE:
            if re.search(pattern, literal.lower()):
                reasons.append(f"{label}: describe only the facts given")
                break
        if EM_DASH in template:
            reasons.append(f"{label}: no em dashes")
        if GENDERED.search(literal):
            reasons.append(f"{label}: never use he, him, his, she or her for a player")
        if not unknown and len(template.format(**{k: facts[k] for k in slots})) > limit:
            reasons.append(f"{label}: too long")
    return reasons
