"""Gravity, marking matchups and spells: the tracking metrics behind the Match Blueprint page."""

import numpy as np
import pytest

from engine.gravity import (
    ATTENTION_RADIUS_M,
    MIN_ZONE_FRAMES,
    SCALE,
    ZONE_X,
    ZONE_Y,
    GravityBaseline,
    GravityTracker,
    attention,
    fit_baseline,
)
from engine.league import build_league
from engine.live import LiveStats
from engine.matchups import MarkingTracker
from engine.models import BallPos, MatchMeta, PlayerPos, TrackingFrame
from engine.sim import MatchSimulator, SimConfig
from engine.spells import MinuteBucket, best_spells, empty_bucket


def frame(t, ball, players):
    return TrackingFrame(
        t=t, ball=BallPos(x=ball[0], y=ball[1], z=ball[2] if len(ball) > 2 else 0.0),
        players=[PlayerPos(id=i, team=side, x=x, y=y, speed_ms=0.0) for i, side, x, y in players],
    )


# Gravity


def test_attention_is_a_soft_count_of_nearby_defenders():
    assert attention(50, 30, np.array([[50.0, 30.0]])) == pytest.approx(1.0)
    assert attention(50, 30, np.array([[50.0 + ATTENTION_RADIUS_M / 2, 30.0]])) == pytest.approx(0.5)
    assert attention(50, 30, np.array([[50.0 + ATTENTION_RADIUS_M + 1, 30.0]])) == 0.0
    assert attention(50, 30, np.empty((0, 2))) == 0.0


def test_gravity_is_attention_above_the_baseline_by_role():
    tracker = GravityTracker(keepers={"H1", "A1"}, baseline=GravityBaseline.flat(off_ball=0.2, on_ball=0.5))
    players = [
        ("H1", "home", 5, 34), ("H9", "home", 80, 34), ("H7", "home", 40, 10),  # H9 has the ball
        ("A1", "away", 100, 34), ("A4", "away", 80, 35), ("A5", "away", 83, 34),
    ]
    tracker.update(frame(0.0, (80.5, 34.0), players), "home")
    h9 = tracker.rows["H9"]
    expected = SCALE * (attention(80, 34, np.array([[80.0, 35.0], [83.0, 34.0]])) - 0.5)
    assert h9.sums[3] == pytest.approx(expected)  # final third, on the ball
    assert h9.frames == [0, 0, 0, 1]
    assert tracker.rows["H7"].frames == [1, 0, 0, 0]  # build-up, off the ball
    assert tracker.rows["H7"].overall == pytest.approx(-SCALE * 0.2)  # nobody near: below the average
    assert "H1" not in tracker.rows and "A4" not in tracker.rows  # keepers and defenders are not measured
    assert tracker.maps["home"].on_n.sum() == 1 and tracker.maps["home"].off_n.sum() == 1


def test_gravity_mirrors_the_away_team_so_maps_attack_left_to_right():
    tracker = GravityTracker(keepers=set(), baseline=GravityBaseline.flat())
    tracker.update(frame(0.0, (10.5, 34.0), [("A9", "away", 10, 34), ("H4", "home", 12, 34)]), "away")
    assert tracker.rows["A9"].frames[3] == 1  # x = 10 for the away side is deep in its final third
    assert tracker.maps["away"].on_n[-4:].sum() == 1


def test_no_gravity_without_possession():
    tracker = GravityTracker(keepers=set(), baseline=GravityBaseline.flat())
    tracker.update(frame(0.0, (50, 34), [("H9", "home", 50, 34), ("A4", "away", 51, 34)]), None)
    assert tracker.rows == {}


def test_fit_baseline_averages_by_zone_and_falls_back_when_thin():
    s1, n1 = np.zeros((2, ZONE_X, ZONE_Y)), np.zeros((2, ZONE_X, ZONE_Y))
    s1[0, 3, 1], n1[0, 3, 1] = 60.0, 100
    s2, n2 = s1.copy(), n1.copy()
    s2[0, 3, 1], n2[0, 3, 1] = 20.0, 100
    s2[1, 5, 2], n2[1, 5, 2] = 5.0, MIN_ZONE_FRAMES - 1  # too few frames to trust
    base = fit_baseline([(s1, n1), (s2, n2)])
    assert base.expected[0][3][1] == pytest.approx(0.4)
    assert base.expected[1][5][2] == pytest.approx(5.0 / (MIN_ZONE_FRAMES - 1), abs=1e-4)  # role average used
    assert GravityBaseline.from_json(base.to_json()) == base


# Marking


def test_nearest_defender_marks_and_is_charged_for_shots():
    m = MarkingTracker(keepers=set())
    players = [("H9", "home", 80, 34), ("H7", "home", 60, 10), ("A4", "away", 81, 34), ("A2", "away", 62, 12)]
    for i in range(6):
        m.update(frame(i * 0.2, (80, 34), players), "home")
    m.on_shot("H9", 0.3, goal=True)
    m.on_received("H7")
    m.on_tackle("A4", "H9")
    top = m.main_marker("H9")
    assert top.defender == "A4" and top.seconds == pytest.approx(1.0)
    assert top.share == pytest.approx(1.0)  # A4 marked H9 for all of its 1.0 s defending
    assert (top.allowed.shots, top.allowed.goals, top.allowed.tackles) == (1, 1, 1)
    assert top.allowed.xg == pytest.approx(0.3)
    assert m.main_marker("H7").defender == "A2" and m.main_marker("H7").allowed.received == 1


def test_marking_counts_only_when_the_other_team_has_the_ball():
    m = MarkingTracker(keepers=set())
    players = [("H9", "home", 80, 34), ("A4", "away", 81, 34)]
    for i in range(3):
        m.update(frame(i * 0.2, (80, 34), players), "away")
    assert m.main_marker("H9") is None and m.defending.get("H9", 0.0) == pytest.approx(0.4)


# Spells


def test_best_spell_finds_the_dominant_stretch():
    minutes = [empty_bucket() for _ in range(40)]
    for b in minutes:
        b.xt = [0.01, 0.01]
    for m in range(20, 30):
        minutes[m] = MinuteBucket([0.05, 0.005], [1, 0], [0, 0], [0.1, 0.0])
    minutes[25].goals = [1, 0]
    spells = best_spells(minutes, length=10)
    home = spells["home"]
    assert (home.start, home.end, home.shots, home.goals) == (20, 30, 10, 1)
    assert home.share == pytest.approx(0.5 / 0.55, abs=1e-3)
    assert spells["away"] is None  # never dominated


def test_no_spell_in_a_short_match():
    assert best_spells([empty_bucket()] * 3, length=10) == {"home": None, "away": None}


# On a simulated match


@pytest.fixture(scope="module")
def live():
    league = build_league()
    meta = MatchMeta(match_id="g001", home="KR", away="AV", seed=21)
    sim = MatchSimulator(meta, league, SimConfig(mode="full", half_s=600.0))
    stats = LiveStats(meta, league)
    for item in sim.run():
        stats.push(item)
    return stats


def test_live_match_has_gravity_marking_and_named_defenders(live):
    keepers = live._keepers
    assert live.gravity.rows and not (set(live.gravity.rows) & keepers)
    frames = sum(r.total_frames for r in live.gravity.rows.values())
    maps = sum(m.on_n.sum() + m.off_n.sum() for m in live.gravity.maps.values())
    assert frames == maps
    for shot in live.shots:
        if shot.defender_m is not None:
            assert shot.defender_id and live.marking.teams.get(shot.defender_id, None) != shot.team
    attacker = max(live.shots, key=lambda s: s.xg).player_id
    top = live.marking.main_marker(attacker)
    assert top is not None and 0 < top.share <= 1
    assert sum(b.shots[0] + b.shots[1] for b in live.by_minute) == len(live.shots)
