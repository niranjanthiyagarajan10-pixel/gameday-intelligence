"""Eight languages: translations made ahead of time pass the live checks, and a fan who picks a language
gets it everywhere, even when every agent falls back to its template."""

import asyncio
import json
import re
import time
from collections import Counter
from pathlib import Path

import pytest

from agents import fallback, i18n, personalizer
from agents.personalizer import LANGS
from app.room import MatchRoom, RoomConfig
from engine.league import build_league

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "web" / "src" / "i18n"


@pytest.fixture(scope="module")
def room():
    r = MatchRoom("i18n", build_league(), RoomConfig(half_s=600.0, scenario=None))
    r.fast_forward(900.0)
    return r


def test_every_template_translation_passes_the_personalizer_check(room):
    table = json.loads(i18n.TEMPLATES_FILE.read_text(encoding="utf-8"))
    assert set(table) == set(LANGS)
    names = list(room.names.values()) + list(room.teams.values())
    for lang, rows in table.items():
        assert rows, lang
        for src, out in rows.items():
            assert personalizer.check(src, out, names) == [], (lang, src, out)


def test_every_card_template_has_every_language():
    table = json.loads(i18n.TEMPLATES_FILE.read_text(encoding="utf-8"))
    for by_aud in fallback.TEMPLATES.values():
        for tpl in by_aud.values():
            assert all(tpl in table[lang] for lang in LANGS), tpl


def test_template_cards_arrive_in_every_language(room):
    card = room.cards[0]
    assert set(card["langs"]) == set(LANGS)
    for lang, by_aud in card["langs"].items():
        assert set(by_aud) == {"casual", "analyst"} and by_aud["casual"]["lang"] == lang
        assert "{" not in by_aud["casual"]["text"]


def test_a_template_story_is_in_every_language_without_a_model(room):
    brief = asyncio.run(room.brief("ja"))
    assert brief["source"] == "template"
    assert set(brief["langs"]) == set(LANGS)
    assert all(len(v["bullets"]) == 3 for v in brief["langs"].values())


def test_slot_words_are_translated():
    values = json.loads(i18n.VALUES_FILE.read_text(encoding="utf-8"))
    for lang in LANGS:
        assert i18n.localize({"shape": "low block", "player": "Dani Mensah"}, lang)["player"] == "Dani Mensah"
        assert i18n.localize({"shape": "low block"}, lang)["shape"] == values[lang]["low block"]


def test_languages_are_written_only_while_someone_watches(room):
    assert room.wanted_langs() == ()
    assert room.want("fr") and not room.want("xx")
    assert room.wanted_langs() == ("fr",)
    room._wanted["fr"] = time.monotonic() - 3600
    assert room.wanted_langs() == ()


def test_interface_translations_keep_placeholders_and_digits():
    from app.ui_strings import collect

    strings = set(collect())
    for lang in LANGS:
        table = json.loads((UI / f"{lang}.json").read_text(encoding="utf-8"))
        assert len(table) >= 0.9 * len(strings), (lang, len(table), len(strings))
        for src, out in table.items():
            assert Counter(re.findall(r"\{\w+\}", src)) == Counter(re.findall(r"\{\w+\}", out)), (lang, src, out)
            assert Counter(re.findall(r"\d", src)) == Counter(re.findall(r"\d", out)), (lang, src, out)
