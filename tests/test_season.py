from collections import Counter

import pytest

from engine.league import build_league
from engine.season import (
    CURRENT_MATCHDAY,
    MATCHDAY_FIXTURES,
    Result,
    Season,
    load_season,
    match_seed,
    play,
    schedule,
)


def _r(md, home, away, hg, ag, season="this"):
    return Result(season=season, matchday=md, home=home, away=away, score=(hg, ag), xg=(1.0, 1.0),
                  shots=(10, 10), on_target=(4, 4), reds=(0, 0), goals=[], players={})


def test_schedule_is_a_double_round_robin():
    rounds = schedule()
    assert len(rounds) == 18
    clubs = set(build_league().clubs)
    for fixtures in rounds:
        assert len(fixtures) == 5
        assert sorted(c for f in fixtures for c in f) == sorted(clubs)
    pairs = Counter(f for fixtures in rounds for f in fixtures)
    assert len(pairs) == 90 and set(pairs.values()) == {1}
    assert all((a, h) in pairs for h, a in pairs)


def test_matchday_nine_is_the_demo_round():
    assert schedule()[CURRENT_MATCHDAY - 1] == MATCHDAY_FIXTURES
    assert ("KR", "AV") in MATCHDAY_FIXTURES and ("RU", "TW") in MATCHDAY_FIXTURES


def test_table_points_goal_difference_and_order():
    season = Season([_r(1, "KR", "AV", 2, 0), _r(1, "NA", "BF", 1, 1), _r(2, "AV", "NA", 3, 1), _r(2, "BF", "KR", 0, 0)])
    table = season.table("this")
    rows = {r["club"]: r for r in table}
    assert rows["KR"] == {**rows["KR"], "played": 2, "won": 1, "drawn": 1, "lost": 0, "gf": 2, "ga": 0, "gd": 2, "points": 4}
    assert rows["AV"]["points"] == 3 and rows["AV"]["gd"] == 0
    assert rows["NA"]["points"] == 1 and rows["BF"]["points"] == 2
    assert [r["club"] for r in table][:2] == ["KR", "AV"]
    assert [r["position"] for r in table] == [1, 2, 3, 4]


def test_form_is_latest_first_and_capped_at_five():
    results = [_r(md, "KR", "AV", g, 1) for md, g in [(1, 2), (2, 1), (3, 0), (4, 3), (5, 3), (6, 0)]]
    assert Season(results).form("KR") == ["L", "W", "W", "L", "D"]
    assert Season(results).form("AV") == ["W", "L", "L", "W", "D"]


def test_head_to_head_covers_both_venues_and_seasons():
    season = Season([_r(3, "KR", "AV", 2, 0, "last"), _r(12, "AV", "KR", 1, 1, "last"), _r(4, "NA", "KR", 0, 1)])
    h2h = season.head_to_head("AV", "KR")
    assert [(m["season"], m["home"], m["score"]) for m in h2h] == [("last", "AV", [1, 1]), ("last", "KR", [2, 0])]


@pytest.fixture(scope="module")
def cached():
    return load_season()


def test_cached_season_has_last_season_and_eight_matchdays(cached):
    assert Counter(r.season for r in cached.results) == {"last": 90, "this": 40}
    assert max(r.matchday for r in cached.results if r.season == "this") == CURRENT_MATCHDAY - 1
    assert sum(r["played"] for r in cached.table("this")) == 80


def test_cached_numbers_add_up(cached):
    for r in cached.results:
        assert sum(1 for g in r.goals if g["team"] == "home") == r.score[0]
        assert sum(p["goals"] for p in r.players.values()) == sum(r.score)
        assert r.on_target[0] >= r.score[0] and r.shots[0] >= r.on_target[0]
    scorers = cached.players("this")
    assert scorers == sorted(scorers, key=lambda p: (-p["goals"], -p["xg"], p["player_id"]))
    assert sum(p["goals"] for p in scorers) == sum(sum(r.score) for r in cached.results if r.season == "this")


def test_a_cached_match_replays_exactly(cached):
    first = next(r for r in cached.results if r.season == "this" and r.matchday == 1)
    again = play(("this", 1, first.home, first.away))
    assert again == first
    assert match_seed("this", 1, 0) != match_seed("last", 1, 0)
