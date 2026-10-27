"""Translations written ahead of time, so a fan never falls back to English.

Template text (what fans see when an agent is slow or fails) is fixed code, so every template is
translated once, offline, by the Personalizer, and checked with the same slot check as live text
(`python -m app.i18n_build`). Words that code puts into slots ("low block", "a big chance",
"interception") are translated the same way. At run time this is a lookup: no model call, so it
works even when the model is down. A template with no translation stays in English.

Files: data/i18n/templates.json and data/i18n/values.json, both {lang: {english: translated}}.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from agents import story

ROOT = Path(__file__).resolve().parent.parent / "data" / "i18n"
TEMPLATES_FILE = ROOT / "templates.json"
VALUES_FILE = ROOT / "values.json"


@lru_cache(maxsize=1)
def _templates() -> dict[str, dict[str, str]]:
    try:
        return json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=1)
def _values() -> dict[str, dict[str, str]]:
    try:
        return json.loads(VALUES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def reload() -> None:
    _templates.cache_clear()
    _values.cache_clear()


def template(english: str, lang: str) -> str | None:
    """The checked translation of a template, or None."""
    return _templates().get(lang, {}).get(english)


def localize(facts: dict[str, Any], lang: str) -> dict[str, Any]:
    """Slot values in the fan's language: words code chose are translated; numbers and names stay."""
    table = _values().get(lang)
    if not table:
        return facts
    return {k: table.get(v, v) if isinstance(v, str) else v for k, v in facts.items()}


def fill(english_or_translated: str, facts: dict[str, Any], lang: str) -> str:
    return story.fill(english_or_translated, localize(facts, lang))


def parts(parts: dict[str, Any], facts: dict[str, Any], lang: str) -> dict[str, Any] | None:
    """A template story in another language, filled; None unless every part has a translation."""
    out: dict[str, Any] = {}
    for key, value in parts.items():
        items = value if isinstance(value, list) else [value]
        done = []
        for tpl in items:
            tr = template(tpl, lang)
            if tr is None:
                return None
            done.append(fill(tr, facts, lang))
        out[key] = done if isinstance(value, list) else done[0]
    return out


def cue(cue_dict: dict[str, Any], lang: str) -> dict[str, Any] | None:
    """A template card cue in another language, shaped like the English cue the UI reads."""
    tr = template(cue_dict["template"], lang)
    if tr is None:
        return None
    slots = localize(cue_dict.get("slots", {}), lang)
    return {**cue_dict, "template": tr, "slots": slots, "lang": lang, "text": story.fill(tr, slots),
            "cue_id": f"{cue_dict.get('cue_id', '')}-{lang}"}
