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
            if re.search(r"\}['’]s\b", template):
                reasons.append(f"{where}: never add 's to a slot")
            if not unknown:
                filled = template.format(**{k: facts[k] for k in slots})
                if DOUBLE_UNIT.search(filled) or "%%" in filled:
                    reasons.append(f"{where}: a fact already carries its unit; do not add one after it")
                if len(filled) > limits.get(label, 600):
                    reasons.append(f"{where}: too long, keep it under {limits.get(label, 600)} characters")
    return reasons
