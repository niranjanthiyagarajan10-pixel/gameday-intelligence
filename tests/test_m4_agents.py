"""Personalizer, Recap and Analyst: their checks, and the Analyst's slot re-reading from the MCP tools."""

import pytest

from agents import analyst, personalizer, recap
from app.room import MatchRoom, RoomConfig
from engine.league import build_league

NAMES = {"Rafael Okafor", "Okafor", "Kingsport Rovers", "Ashford Vale"}
SOURCE = "{player} scores for {team}. It is {score}, and {team} win chance goes from {wp_before} to {wp_after}."


# Personalizer


def test_a_faithful_translation_passes():
    out = "{player} marca para {team}. Es {score}, y la probabilidad de {team} sube de {wp_before} a {wp_after}."
    assert personalizer.check(SOURCE, out, NAMES) == []


@pytest.mark.parametrize("out, reason", [
    ("{player} marca. Es {score}, de {wp_before} a {wp_after}.", "same slots"),
    ("{player} marca para {team} en el minuto 12. {team} {score} {wp_before} {wp_after}", "numbers"),
    ("{player} ने गोल किया १ {team} {team} {score} {wp_before} {wp_after}", "numbers"),
    ("Okafor marca para {team}. {player} {score} {team} {wp_before} {wp_after}", "names"),
])
def test_unsafe_translations_are_refused(out, reason):
    assert any(reason in r for r in personalizer.check(SOURCE, out, NAMES))


def test_a_name_already_in_the_source_may_stay():
    source = "Kingsport Rovers lead with {x}."
    assert personalizer.check(source, "Kingsport Rovers va ganando con {x}.", NAMES) == []


# Recap


FACTS = {"result_win_winner": "Kingsport Rovers", "result_win_score": "2-0", "top_scorer_player": "Rafael Okafor"}


def test_recap_over_facts_passes():
    assert recap.check("{result_win_winner} earn it", "{top_scorer_player} led the way as it ended {result_win_score}.",
                       FACTS, NAMES) == []


def test_recap_refuses_typed_numbers_names_and_unknown_facts():
    reasons = recap.check("Kingsport Rovers win 2-0", "{nobody} scored a header.", FACTS, NAMES)
    joined = " ".join(reasons)
    assert "numbers must be slots" in joined and "names must be slots" in joined
    assert "unknown slots" in joined and "describe only the facts" in joined


# Analyst


@pytest.fixture(scope="module")
def room():
    r = MatchRoom("ask", build_league(), RoomConfig(half_s=300.0, scenario=None))
    while not r.feed.finished:
        r.advance()
    return r


def test_analyst_slots_are_re_read_from_the_tools(room):
    slots = {
        "s1": {"tool": "get_match_state", "args": {}, "field": "score"},
        "s2": {"tool": "get_match_state", "args": {}, "field": "win_probability.home"},
        "s3": {"tool": "get_leverage_table", "args": {"limit": 1}, "field": "rows.0.name"},
    }
    values, evidence, problems = analyst.resolve(room, slots)
    h, a = room.live.score
    assert problems == [] and values["s1"] == f"{h}-{a}" and values["s2"].endswith("%")
    assert values["s3"] in {p["name"] for p in room.roster["players"].values()}
    assert [e["tool"] for e in evidence] == ["get_match_state", "get_match_state", "get_leverage_table"]


def test_analyst_cannot_point_at_missing_fields_or_write_tools(room):
    _, _, problems = analyst.resolve(room, {
        "s1": {"tool": "get_match_state", "args": {}, "field": "weather"},
        "s2": {"tool": "verify_claims", "args": {}, "field": "pass"},
    })
    assert len(problems) == 2


def test_analyst_answer_checks():
    slots = {"s1": {}, "s2": {}}
    assert analyst.check("{s1} has run {s2}.", slots, NAMES) == []
    assert any("numbers" in r for r in analyst.check("{s1} has run {s2} in 12 minutes.", slots, NAMES))
    assert any("names" in r for r in analyst.check("Okafor: {s1} {s2}", slots, NAMES))
    assert analyst.check("Okafor: {s1} {s2}", slots, NAMES, question="How is Okafor doing?") == []
    assert any("exactly one spec" in r for r in analyst.check("{s1} only.", slots, NAMES))


def test_ask_without_a_model_answers_politely(room):
    import asyncio

    out = asyncio.run(room.ask("Who is fastest?"))
    assert out["source"] == "fallback" and out["answer"] and out["steps"][-1]["agent"] == "Fallback"
