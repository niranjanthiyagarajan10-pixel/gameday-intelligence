"""Simulator invariants, determinism and snapshots. Short matches keep the suite fast."""

import pytest

from engine.hashing import stable_hash
from engine.league import build_league
from engine.models import MatchEvent, MatchMeta, TrackingFrame
from engine.sim import Incident, MatchSimulator, Scenario, SimConfig

SHORT = SimConfig(mode="full", half_s=300.0)


def meta(seed=7):
    return MatchMeta(match_id="m001", home="KR", away="AV", seed=seed)


@pytest.fixture(scope="module")
def short_match():
    sim = MatchSimulator(meta(), build_league(), SHORT)
    owners_ok = True
    out = []
    while not sim.finished:
        out += sim.step()
        o = sim.state.owner
        owners_ok &= o == -1 or bool(sim.state.active[o])
    return sim, out, owners_ok


def test_a_short_match_produces_frames_and_events(short_match):
    sim, out, _ = short_match
    frames = [o for o in out if isinstance(o, TrackingFrame)]
    events = [o for o in out if isinstance(o, MatchEvent)]
    assert len(frames) == 3000
    assert {"pass", "possession_change"} <= {e.type.value for e in events}


def test_time_never_goes_backwards(short_match):
    _, out, _ = short_match
    times = [o.t for o in out]
    assert times == sorted(times)


def test_frames_hold_at_most_22_players_on_the_pitch(short_match):
    _, out, _ = short_match
    for f in (o for o in out if isinstance(o, TrackingFrame)):
        assert len(f.players) <= 22
        TrackingFrame.model_validate(f.model_dump())  # bounds re-checked


def test_one_ball_holder_at_a_time(short_match):
    _, _, owners_ok = short_match
    assert owners_ok


def test_possession_changes_alternate(short_match):
    _, out, _ = short_match
    teams = [o.team for o in out if isinstance(o, MatchEvent) and o.type == "possession_change"]
    assert teams[0] == "home"
    assert all(a != b for a, b in zip(teams, teams[1:]))


def test_score_matches_goal_events(short_match):
    sim, out, _ = short_match
    goals = [o.team for o in out if isinstance(o, MatchEvent) and o.type == "goal"]
    assert sim.state.score == [goals.count("home"), goals.count("away")]


def test_snapshot_and_restore_are_exact():
    league = build_league()
    sim = MatchSimulator(meta(), league, SHORT)
    for _ in range(1000):
        sim.step()
    snap = sim.snapshot()
    rest_a = list(sim.run())
    sim.restore(snap)
    rest_b = list(sim.run())
    assert stable_hash(rest_a) == stable_hash(rest_b)


def test_scripted_red_card_removes_the_player():
    scenario = Scenario(name="test", incidents=[Incident(minute=2, kind="red_card", team="away", player_number=8)])
    out = list(MatchSimulator(meta(), build_league(), SHORT, scenario).run())
    cards = [o for o in out if isinstance(o, MatchEvent) and o.type == "card" and o.outcome == "red"]
    assert any(c.player_id == "AV08" and c.minute == 2 for c in cards)
    after = [o for o in out if isinstance(o, TrackingFrame) and o.t > cards[0].t]
    assert all("AV08" not in {p.id for p in f.players} for f in after)


def test_events_only_mode_has_no_frames():
    out = list(MatchSimulator(meta(), build_league(), SimConfig(mode="events_only", half_s=120.0)).run())
    assert out and not any(isinstance(o, TrackingFrame) for o in out)
