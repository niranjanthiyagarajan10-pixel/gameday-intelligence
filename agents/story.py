"""Checks shared by the agents that write longer stories over a set of facts (Preview, Post-game).

The same rules as the Verifier, applied to facts instead of a moment: only known slots, no typed
numbers or names, no details the facts cannot support, and wording that implies a fact ("unbeaten",
"derby", "favourites") only when the facts say so.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from typing import Any

from agents.verifier import DOUBLE_UNIT, EM_DASH, GENDERED
from engine.models import template_slots

Implied = list[tuple[str, str, Callable[[dict[str, Any]], bool]]]


def parse(text: str | None, keys: tuple[str, ...]) -> dict[str, Any] | None:
    """The model's JSON reply, when it has every key as a non-empty string or list of strings."""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if start >= 0 else None
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, Any] = {}
    for k in keys:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
        elif isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v):
            out[k] = [x.strip() for x in v]
        else:
            return None
    return out


def fill(template: str, facts: dict[str, str]) -> str:
    """Fill a story's slots. A possessive after a name ending in s reads "Rovers'", not "Rovers's"."""
    text = template.format(**facts)
    return re.sub(r"(\w*s)'s\b", r"\1'", text)


def check(parts: dict[str, Any], facts: dict[str, str], names: Iterable[str], truths: dict[str, Any],
          limits: dict[str, int], banned: list[str], implied: Implied) -> list[str]:
    """Reasons the story cannot be used; empty when every part passes."""
    reasons: list[str] = []
    names = sorted({n for n in names if n and len(n) >= 3}, key=len, reverse=True)
    for label, value in parts.items():
        for i, template in enumerate(value if isinstance(value, list) else [value]):
            where = f"{label} {i + 1}" if isinstance(value, list) else label
            try:
                slots = template_slots(template)
            except ValueError as e:
                reasons.append(f"{where}: {e}")
                continue
            unknown = sorted(set(slots) - facts.keys())
            if unknown:
                reasons.append(f"{where}: unknown slots " + ", ".join(f"{{{s}}}" for s in unknown) + "; use only the facts")
            literal = re.sub(r"\{[^{}]*\}", " ", template)
            lower = literal.lower()
            if re.search(r"\d", literal):
                reasons.append(f"{where}: numbers must be slots, never typed")
            for name in names:
                if re.search(rf"\b{re.escape(name)}\b", literal):
                    reasons.append(f'{where}: names must be slots, remove "{name}"')
                    break
            for pattern in banned:
                if re.search(pattern, lower):
                    reasons.append(f'{where}: "{re.search(pattern, lower).group(0)}" is not in the facts')
                    break
            for pattern, meaning, test in implied:
                if re.search(pattern, lower) and not test(truths):
                    reasons.append(f"{where}: the wording says {meaning}, but the facts say otherwise")
            if EM_DASH in template:
                reasons.append(f"{where}: no em dashes")
            if GENDERED.search(literal):
                reasons.append(f"{where}: never use he, him, his, she or her for a player")
            if not unknown:
                filled = template.format(**{k: facts[k] for k in slots})
                if DOUBLE_UNIT.search(filled) or "%%" in filled:
                    reasons.append(f"{where}: a fact already carries its unit; do not add one after it")
                if len(filled) > limits.get(label, 600):
                    reasons.append(f"{where}: too long, keep it under {limits.get(label, 600)} characters")
    return reasons


# Wording about one match that is a claim, and the truth that must back it (see app/matchday.match_facts).
MATCH_IMPLIED: Implied = [
    (r"\bwon\b|\bwins\b|\bbeat\b|\bbeats\b|\bvictory\b|\bdefeat(ed)?\b|\blost\b|\bloses\b", "the match has a winner",
     lambda t: bool(t["finished"] and t["leader"])),
    (r"\bdraw(n|s)?\b|\bdrew\b|all square|\blevel\b|\bstalemate\b|share the points", "the scores are level",
     lambda t: t["score"][0] == t["score"][1]),
    # Live, a lead must exist now; in a finished match's story, "led 2-0" is true if anyone ever led.
    (r"\blead(s|ing)?\b|\bled\b|\bahead\b|\bin front\b", "a side is ahead",
     lambda t: bool(t["leader"]) or bool(t["finished"] and t.get("ever_led"))),
    (r"comeback|fight(s|ing)? back|fought back|came from behind|from behind|turn(ed|s)? it around",
     "a side came from behind", lambda t: bool(t["comeback"])),
    (r"late (winner|win|goal|strike)|last[- ]gasp|dying minutes|stoppage", "a late winner",
     lambda t: bool(t["late_winner"])),
    (r"hat[- ]trick", "a hat-trick", lambda t: bool(t["hat_trick"])),
    (r"early (red|sending[- ]off|dismissal)|(red card|sent off|sending[- ]off) early", "an early red card",
     lambda t: bool(t.get("early_red"))),
    (r"early (goal|opener|strike|lead|breakthrough)|(scored|struck|ahead) early", "an early goal",
     lambda t: bool(t.get("early_goal"))),
    (r"red card|sent off|ten men|down to ten|man down|ten-man", "a red card", lambda t: t["reds"] > 0),
    (r"clean sheet|shut ?out|\bnil\b", "a side did not score", lambda t: bool(t["clean_sheet"])),
    (r"dominat|on top|\bsiege\b|camped", "a side dominated", lambda t: bool(t["dominant"])),
    (r"\bupset\b|\bshock\b|giant[- ]kill", "the underdog won", lambda t: bool(t["upset"])),
    (r"\bderby\b|\brivals?\b|rivalry", "it is a derby", lambda t: bool(t["derby"])),
]
MATCH_BANNED = [r"injur", r"manager", r"\bcoach", r"crowd", r"\bfans\b", r"weather", r"transfer", r"penalt",
                r"\bhead(s|er|ers|ed)?\b", r"free[- ]kick", r"corner", r"volley", r"assist", r"\bseason\b", r"troph",
                r"relegat", r"\btitle\b", r"\brecords?\b", r"\bbrace\b", r"career", r"\bvar\b", r"offside"]
