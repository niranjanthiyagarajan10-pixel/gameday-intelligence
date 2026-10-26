"""The box score agrees with the simulator's own record of the match."""

import pytest

from engine.boxscore import BoxScore, leader
from engine.league import build_league
from engine.live import LiveStats
from engine.models import MatchEvent, MatchMeta
from engine.sim import MatchSimulator, SimConfig


@pytest.fixture(scope="module")
def played():
    league = build_league()
    meta = MatchMeta(match_id="m001", home="KR", away="AV", seed=11)
    sim = MatchSimulator(meta, league, SimConfig(mode="full", half_s=900.0))
    corners = [0, 0]
    original = sim._new_restart

    def counting(t, kind, team, x, y, out):
        if kind == "corner":
            corners[team] += 1
        return original(t, kind, team, x, y, out)

    sim._new_restart = counting
    live = LiveStats(meta, league)
    events = []
    for item in sim.run():
        if isinstance(item, MatchEvent):
            events.append(item)
        live.push(item)
    return live, events, corners


def _rows(live):
    return {r["key"]: r["values"] for r in live.box_score()["rows"]}


def test_counts_match_the_events(played):
    live, events, _ = played
    rows = _rows(live)
    for k, side in enumerate(("home", "away")):
        mine = [e for e in events if e.team == side]
        assert rows["shots"][k] == sum(e.type == "shot" for e in mine)
        assert rows["on_target"][k] == sum(e.type == "shot" and e.outcome in ("goal", "saved") for e in mine)
        assert rows["passes"][k] == live.passes[k]
        assert rows["fouls"][k] == sum(e.type == "foul" for e in mine)
        assert rows["yellows"][k] == sum(e.type == "card" and e.outcome == "yellow" for e in mine)
        assert rows["reds"][k] == sum(e.type == "card" and e.outcome == "red" for e in mine)
        assert rows["on_target"][k] <= rows["shots"][k]
        assert 0 <= rows["pass_accuracy"][k] <= 100


def test_corners_match_the_simulator(played):
    live, _, corners = played
    assert sum(corners) > 0
    assert _rows(live)["corners"] == corners


def test_possession_adds_to_about_100(played):
    live, _, _ = played
    assert 99 <= sum(_rows(live)["possession"]) <= 101


def test_leader():
    assert leader([3, 1]) == 0
    assert leader([1, 3]) == 1
    assert leader([2, 2]) is None
    assert leader([3, 1], lower_better=True) == 1


def test_empty_box_score():
    rows = BoxScore().to_dict((0.0, 0.0), (0.5, 0.5))["rows"]
    assert all(r["values"] in ([0, 0], [0.0, 0.0], [50, 50]) for r in rows)
