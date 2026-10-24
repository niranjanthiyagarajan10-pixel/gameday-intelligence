"""Before and after the match: the forecast, the facts, the Preview and Post-game agents' checks and
fallbacks, and the league tools on the MCP server."""

import asyncio
import json
import re

import pytest

from agents import postgame, preview
from agents.desk import name_list
from app import matchday
from app.league import season
from app.room import MatchRoom, RoomConfig
from engine.forecast import pre_match
from engine.league import build_league
from engine.season import MATCHDAY_FIXTURES
from mcp_server import tools

LEAGUE = build_league()


def names_for(home, away):
    names = {p.player_id: p.name for c in (home, away) for p in LEAGUE.squads[c]}
    return name_list(names, {"home": LEAGUE.clubs[home].name, "away": LEAGUE.clubs[away].name})


def test_ordinals_and_forecast():
    assert [matchday.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21)] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st"]
    ph, pd, pa = pre_match("KR", "AV")
    assert abs(ph + pd + pa - 1) < 1e-9 and ph > pa
    assert pre_match("KR", "AV") == pre_match("KR", "AV")


@pytest.mark.parametrize("home, away", MATCHDAY_FIXTURES)
def test_preview_facts_and_the_template_preview_pass_the_checks(home, away):
    pack = matchday.preview(LEAGUE, season(), home, away)
    facts = pack["facts"]
    assert facts["home"] == LEAGUE.clubs[home].name and facts["forecast_home"].endswith("%")
    assert len(facts["home_form"].split()) == 5
    assert all(isinstance(v, str) for v in facts.values())
    watch = pack["watch"]
    assert 2 <= len(watch) <= 3 and all(p["club"] in (home, away) and p["number"] for p in watch)
    template = preview.fallback(facts, pack["truths"])
    assert preview.check(template, facts, names_for(home, away), pack["truths"]) == []


def test_the_derby_is_a_derby_and_nothing_else_is():
    derby = matchday.preview(LEAGUE, season(), "RU", "TW")["truths"]
    other = matchday.preview(LEAGUE, season(), "WH", "SM")["truths"]
    assert derby["derby"] and not other["derby"]


@pytest.fixture(scope="module")
def kr():
    pack = matchday.preview(LEAGUE, season(), "KR", "AV")
    return pack["facts"], pack["truths"], names_for("KR", "AV")


@pytest.mark.parametrize("story, reason", [
    ("{home} have won 3 of their last five.", "numbers must be slots"),
    ("Dani Mensah leads the line for {home}.", "names must be slots"),
    ("{home} welcome {away} in the local derby.", "the facts say otherwise"),
    ("{home} are boosted by an injury to a rival.", "is not in the facts"),
    ("The model gives {home} {forecast_home} percent.", "already carries its unit"),
    ("{home} go in at {home_position} with {attendance} watching.", "unknown slots"),
    ("{home_scorer} is in form; his finishing is sharp.", "never use he"),
])
def test_planted_errors_in_a_preview_are_caught(kr, story, reason):
    facts, truths, names = kr
    reasons = preview.check({"headline": "{home} v {away}", "story": story}, facts, names, truths)
    assert any(reason in r for r in reasons), reasons


def test_unbeaten_is_allowed_only_when_the_form_says_so(kr):
    facts, truths, names = kr
    story = {"headline": "{home} v {away}", "story": "{home} arrive unbeaten."}
    expect_ok = truths["home_unbeaten"] or truths["away_unbeaten"]
    assert (preview.check(story, facts, names, truths) == []) == expect_ok


def test_next_fixture_is_on_matchday_ten():
    opp, at_home = matchday.next_fixture("KR")
    assert opp != "KR" and isinstance(at_home, bool)


@pytest.fixture(scope="module")
def room():
    r = MatchRoom("pg", LEAGUE, RoomConfig(half_s=300.0, scenario=None))
    r.fast_forward(600.0)
    return r


def test_postgame_decided_and_next(room):
    pack = matchday.postgame(room, LEAGUE)
    levs = [abs(d["leverage"]) for d in pack["decided"]]
    assert 1 <= len(levs) <= 3 and levs == sorted(levs, reverse=True)
    assert {n["club"] for n in pack["next"]} == {"KR", "AV"}
    lines = postgame.fallback(pack["facts"])
    assert postgame.check(lines, pack["facts"], room.desk.forbidden, pack["truths"]) == []
    won = {"look_ahead": ["{home} won it and {home_next_opponent} are next.", "{away} play {away_next_opponent} next."]}
    drawn = pack["truths"]["score"][0] == pack["truths"]["score"][1]
    assert bool(postgame.check(won, pack["facts"], room.desk.forbidden, pack["truths"])) == drawn


def test_room_serves_template_preview_and_postgame_offline(room):
    pv = asyncio.run(room.preview())
    assert pv["source"] == "template" and "Kingsport Rovers" in pv["story"] and pv["watch"]
    words = re.sub(r"\{[^{}]*\}", " ", preview.fallback(pv["facts"], {})["story"])
    assert not any(ch.isdigit() for ch in words)
    pg = asyncio.run(room.postgame())
    assert pg["source"] == "template" and pg["decided"] and len(pg["look_ahead"]) >= 2
    assert any(s["agent"] == "Fallback" for s in room.trace)


def test_league_tools(room):
    table = tools.get_league_table(room)["rows"]
    assert len(table) == 10 and table[0]["position"] == 1 and len(table[0]["form"]) == 5
    club = tools.get_club_season(room, "Ashford")
    assert club["club"] == "AV" and club["results"] and club["scorers"]
    assert tools.get_head_to_head(room, "home", "away")["meetings"]
    fc = tools.get_fixture_forecast(room, "home", "away")
    assert abs(sum(fc["win_probability"].values()) - 1) < 0.01
    with pytest.raises(ValueError):
        tools.get_club_season(room, "Nowhere Town")
    json.dumps([table, club, fc])


class ScriptedWriters:
    """Stands in for Foundry: the Preview's first draft types a number, its second is clean;
    the Post-game writes clean lines; the Personalizer passes templates through."""

    name = "foundry"

    def __init__(self):
        self.preview_drafts = 0

    async def complete(self, *, agent, instructions, prompt, model):
        if agent == "Personalizer":
            return json.dumps({"template": json.loads(prompt)["template"]})
        if agent == "Preview":
            self.preview_drafts += 1
            story = ("{home} have won 3 of the last five." if self.preview_drafts == 1
                     else "{home} sit {home_position}; {away} are {away_position}. The model gives {home} {forecast_home}.")
            return json.dumps({"headline": "{home} v {away}", "story": story})
        return json.dumps({"look_ahead": ["{home} face {home_next_opponent} {home_next_venue} next.",
                                          "{away} face {away_next_opponent} {away_next_venue} next."]})


def test_agents_retry_on_a_rejected_draft_and_write_every_language():
    from agents.llm import LLM

    backend = ScriptedWriters()
    r = MatchRoom("writers", LEAGUE, RoomConfig(half_s=300.0, scenario=None), LLM(backend))
    r.fast_forward(300.0)
    pv = asyncio.run(r.preview())
    assert backend.preview_drafts == 2 and pv["source"] == "agent"
    assert pv["story"].startswith("Kingsport Rovers sit 2nd") and set(pv["langs"]) == {"es", "hi"}
    checks = [s["status"] for s in r.trace if s["agent"] == "Verifier"]
    assert checks == ["reject", "pass"]
    pg = asyncio.run(r.postgame())
    assert pg["source"] == "agent" and len(pg["look_ahead"]) == 2
