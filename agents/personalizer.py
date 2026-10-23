"""The Personalizer agent: takes a verified English template and writes it for a fan in Spanish or
Hindi, keeping every slot exactly. Code fills the slots after, so numbers and names stay correct in
every language. Its output is re-checked before use: same slots, no typed numbers or names.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable

from engine.models import template_slots

LANGS = {"es": "Spanish (neutral, as used on international sports broadcasts)", "hi": "Hindi, in Devanagari script"}
EM_DASH = chr(0x2014)
DIGITS = re.compile(r"[0-9०-९]")  # ASCII and Devanagari digits

INSTRUCTIONS = """You are the Personalizer for Gameday Intelligence, a live football match companion.
You rewrite one short on-screen line for a fan in another language.

Rules:
1. Keep every slot in curly braces exactly as it is, for example {player} or {wp_after}, the same
   number of times. Never translate, rename, add or drop a slot.
2. Never type a digit, a player name or a club name. They are in the slots.
3. Keep the meaning and every claim; add nothing. Never use he, him, his, she or her for a player: use the player's slot. Sound like a natural broadcast line in the language.
4. No em dashes. Reply with JSON only: {"template": "..."}
"""


def prompt(template: str, lang: str, audience: str) -> str:
    return json.dumps({"language": LANGS[lang], "audience": audience, "template": template}, ensure_ascii=False)


def parse(text: str | None) -> str | None:
    if not text:
        return None
    start, end = text.find("{\""), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if start >= 0 else None
    except json.JSONDecodeError:
        return None
    value = data.get("template") if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def check(source: str, out: str, names: Iterable[str]) -> list[str]:
    """Reasons the translation cannot be used; empty when it is safe."""
    reasons = []
    try:
        if Counter(template_slots(out)) != Counter(template_slots(source)):
            reasons.append("keep exactly the same slots as the source, each the same number of times")
    except ValueError as e:
        return [str(e)]
    literal = re.sub(r"\{[^{}]*\}", " ", out)
    source_literal = re.sub(r"\{[^{}]*\}", " ", source)
    names = [n for n in names if n not in source_literal]  # a name already in the verified source may stay
    if DIGITS.search(literal):
        reasons.append("numbers must stay in slots")
    for name in sorted({n for n in names if n and len(n) >= 3}, key=len, reverse=True):
        if name in literal:
            reasons.append(f'names must stay in slots: remove "{name}"')
            break
    if EM_DASH in out:
        reasons.append("no em dashes")
    if len(out) > 3 * len(source) + 40:
        reasons.append("too long")
    return reasons
