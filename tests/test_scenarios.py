from concurrent.futures import ProcessPoolExecutor

from engine.scenarios import BY_ID, STORIES, library, play, running_scores
from engine.season import MATCHDAY_FIXTURES, Result


def _r(score, xg, goals):
    return Result(season="this", matchday=9, home="RU", away="TW", score=score, xg=xg, shots=(9, 9),
                  on_target=(4, 4), reds=(0, 0), goals=[{"minute": m, "team": t} for m, t in goals], players={})


def test_one_story_per_live_fixture():
    assert sorted((s.home, s.away) for s in STORIES) == sorted(MATCHDAY_FIXTURES)
    assert [sc.scenario_id for sc in library()] == [s.scenario_id for s in STORIES]


def test_story_checks():
    comeback = _r((2, 2), (1.0, 1.0), [(9, "home"), (26, "home"), (69, "away"), (73, "away")])
    assert running_scores(comeback)[-1] == (73, 2, 2)
    assert BY_ID["derby"].check(comeback)
    assert not BY_ID["derby"].check(_r((2, 1), (1.0, 1.0), [(9, "home"), (26, "home"), (69, "away")]))
    assert BY_ID["upset"].check(_r((0, 1), (1.4, 0.6), [(50, "away")]))
    assert not BY_ID["upset"].check(_r((0, 1), (0.4, 0.6), [(50, "away")]))
    assert BY_ID["fightback"].check(_r((2, 1), (1.0, 1.0), [(31, "away"), (53, "home"), (60, "home")]))
    assert not BY_ID["fightback"].check(_r((2, 1), (1.0, 1.0), [(20, "away"), (53, "home"), (60, "home")]))
    assert not BY_ID["chess"].check(_r((0, 0), (1.2, 0.9), []))


def test_every_stored_scenario_still_plays_its_story():
    scenarios = library()
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(play, scenarios))
    for sc, r in zip(scenarios, results):
        assert BY_ID[sc.scenario_id].check(r), (sc.scenario_id, r.score, r.xg)


def test_a_live_room_plays_the_same_match_the_search_checked():
    from app.room import MatchRoom, RoomConfig
    from engine.league import build_league
    from engine.scenarios import live_match_id, path_for

    for sc in library():
        room = MatchRoom("same", build_league(), RoomConfig.for_scenario(str(path_for(sc.scenario_id))))
        assert room.feed.meta.match_id == live_match_id(sc.home, sc.away, sc.seed)
