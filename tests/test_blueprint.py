"""The Match Blueprint payload: every section present, every sentence filled from engine state."""

import json
import re

import pytest

from agents.report import REPORT, count
from app.blueprint import MIN_MARKING_S, build_blueprint
from app.room import MatchRoom, RoomConfig
from engine.gravity import MAP_X, MAP_Y
from engine.league import build_league

EM_DASH = chr(0x2014)


@pytest.fixture(scope="module")
def room():
    r = MatchRoom("bp", build_league(), RoomConfig(half_s=600.0, scenario=None))
    while not r.feed.finished:
        r.advance()
    r.status = "full_time"
    return r


@pytest.fixture(scope="module")
def bp(room):
    return room.blueprint()


def texts(bp):
    yield bp["overview"]["headline"]
    yield bp["overview"]["text"]
    for h in bp["highlights"]:
        yield h["title"]
        yield h["subtitle"]
    yield from bp["finishing"].values()
    for g in bp["gravity"]["players"]:
        yield g["text"]
    for m in bp["marking"]:
        yield m["caption"]
        yield m["text"]
    for lev in bp["leverage"]:
        yield lev["text"]


def test_templates_hold_only_words():
    for key, template in REPORT.items():
        assert not re.search(r"\d", template), key
        assert EM_DASH not in template


def test_every_sentence_is_filled(bp):
    for t in texts(bp):
        assert t and "{" not in t and "}" not in t and EM_DASH not in t


def test_overview_states_the_result(room, bp):
    h, a = room.live.score
    assert f"{max(h, a)}-{min(h, a)}" in bp["overview"]["text"]
    assert room.roster["clubs"]["home"]["name"] in bp["overview"]["text"]


def test_highlights_point_at_real_shots(bp):
    ids = {s["event_id"] for s in bp["shots"]}
    assert 0 < len(bp["highlights"]) <= 5
    assert all(h["event_id"] in ids for h in bp["highlights"])


def test_shots_name_a_defender_from_the_other_team(room, bp):
    players = room.roster["players"]
    for s in bp["shots"]:
        if s["defender"]:
            assert players[s["defender"]]["side"] != s["team"]
        assert s["half"] in (1, 2)


def test_performers_are_four_different_players(bp):
    picked = [p["player"] for p in bp["performers"]]
    assert len(picked) == len(set(picked))
    assert {p["key"] for p in bp["performers"]} <= {"goals_above_xg", "creation", "defending", "gravity"}


def test_gravity_maps_and_marking_are_in_range(bp):
    for side in ("home", "away"):
        m = bp["gravity"]["maps"][side]
        assert len(m["on_sum"]) == MAP_X and len(m["on_sum"][0]) == MAP_Y
    for g in bp["gravity"]["players"]:
        assert g["frames"] > 0
    for m in bp["marking"]:
        assert 0 < m["share"] <= 1 and m["seconds"] >= MIN_MARKING_S


def test_payload_is_json_and_small(bp):
    assert len(json.dumps(bp)) < 200_000


def test_live_blueprint_says_lead_not_win(room):
    live_bp = build_blueprint(room.live, room.roster, "live", 600.0)
    assert "earn the win" not in live_bp["overview"]["headline"]


def test_count_plurals():
    assert count(1, "shot") == "1 shot" and count(2, "shot") == "2 shots" and count(3, "pass") == "3 passes"
