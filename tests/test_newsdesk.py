"""Catch me up and the Newsdesk: match facts from the live engine, the Summarizer's and Newsdesk's checks
and templates, and the newsdesk data agreeing with each scenario's story."""

import asyncio
import json

import pytest

from agents import newsdesk, summarizer
from agents.desk import name_list
from app import matchday
from app.newsdesk import matches
from app.room import MatchRoom, RoomConfig
from engine.league import build_league
from engine.scenarios import BY_ID

LEAGUE = build_league()


def names_for(m):
    return name_list({p.player_id: p.name for c in (m["home"], m["away"]) for p in LEAGUE.squads[c]},
                     {"home": m["facts"]["home"], "away": m["facts"]["away"]})


@pytest.mark.parametrize("m", matches(), ids=lambda m: m["scenario"])
def test_every_report_template_and_brief_template_pass_the_checks(m):
    names = names_for(m)
    assert newsdesk.check(newsdesk.fallback(m["facts"], m["truths"]), m["facts"], names, m["truths"]) == []
    assert summarizer.check(summarizer.fallback(m["facts"], m["truths"]), m["facts"], names, m["truths"]) == []


def test_the_newsdesk_matches_tell_their_stories():
    t = {m["scenario"]: m["truths"] for m in matches()}
    assert t["derby"]["derby"] and t["derby"]["comeback"] and t["derby"]["score"][0] == t["derby"]["score"][1]
    assert t["upset"]["leader"] == "away" and t["upset"]["upset"]
    assert t["chess"]["score"] == [0, 0]
    assert t["fightback"]["leader"] == "home" and t["fightback"]["reds"] >= 1 and t["fightback"]["comeback"]
    assert t["demo"]["reds"] >= 1
    assert {m["scenario"] for m in matches()} == set(BY_ID)


@pytest.fixture(scope="module")
def chess():
    m = next(x for x in matches() if x["scenario"] == "chess")
    return m["facts"], m["truths"], names_for(m)


@pytest.mark.parametrize("line, reason", [
    ("{home} won it late.", "the facts say otherwise"),
    ("A late winner settled it.", "the facts say otherwise"),
    ("{away} were down to ten men.", "the facts say otherwise"),
    ("A huge upset at {ground}.", "the facts say otherwise"),
    ("Westholt and {away} drew {score}.", "names must be slots"),
    ("It finished 0-0.", "numbers must be slots"),
    ("A header nearly won it.", "is not in the facts"),
    ("{home} had {home_possession} percent of the ball.", "already carries its unit"),
])
def test_planted_errors_in_a_report_are_caught(chess, line, reason):
    facts, truths, names = chess
    parts = {"headline": "{home} and {away} draw", "standfirst": "Level.", "body": [line], "pull": "Level"}
    reasons = newsdesk.check(parts, facts, names, truths)
    assert any(reason in r for r in reasons), reasons


def test_live_match_facts_and_a_template_brief_from_the_room():
    room = MatchRoom("brief", LEAGUE, RoomConfig(half_s=600.0, scenario=None))
    room.fast_forward(900.0)
    pack = matchday.match_facts(room.live, room.names, room.teams, False)
    assert pack["facts"]["minute"] == f"{int(room.live.t // 60)}'" and pack["truths"]["finished"] is False
    assert not pack["truths"]["late_winner"] and not pack["truths"]["upset"]
    b = asyncio.run(room.brief())
    assert b["source"] == "template" and len(b["bullets"]) == 3 and b["stats"]["xg"]
    again = asyncio.run(room.brief())
    assert again is b  # nothing moved on, so the brief is not rewritten


def test_api_serves_the_brief_and_every_report():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(RoomConfig(half_s=60.0, speed=30.0, scenario=None))) as c:
        brief = c.get("/api/rooms/main/brief").json()
        assert len(brief["bullets"]) == 3
        news = c.get("/api/newsdesk").json()
        assert news["matchday"] == 9 and len(news["articles"]) == 5
        a = news["articles"][0]
        assert a["headline"] and a["standfirst"] and a["body"] and a["pull"] and a["source"] == "template"
        json.dumps(news)
