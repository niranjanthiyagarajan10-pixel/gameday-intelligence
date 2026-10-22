"""The live stats engine on a real simulated match."""

import math

import pytest

from engine.league import build_league
from engine.live import LiveStats
from engine.models import MatchEvent, MatchMeta, Moment, StatsUpdate
from engine.sim import MatchSimulator, SimConfig


@pytest.fixture(scope="module")
def played():
    league = build_league()
    meta = MatchMeta(match_id="m001", home="KR", away="AV", seed=11)
    sim = MatchSimulator(meta, league, SimConfig(mode="full", half_s=900.0))
    live = LiveStats(meta, league)
    events, moments, stats = [], [], []
    for item in sim.run():
        if isinstance(item, MatchEvent):
            events.append(item)
        moments += live.push(item)
        if len(events) % 50 == 0:
            stats.append(live.stats())
    return sim, live, events, moments, stats


def test_stats_are_valid_contracts(played):
    _, live, _, _, stats = played
    for s in stats + [live.stats()]:
        StatsUpdate.model_validate(s.model_dump())


def test_score_and_shots_match_the_events(played):
    sim, live, events, _, _ = played
    assert live.score == sim.state.score
    assert len(live.shots) == sum(e.type == "shot" for e in events)
    assert live.xg[0] > 0 or live.xg[1] > 0


def test_every_goal_becomes_a_moment(played):
    sim, _, _, moments, _ = played
    goal_moments = [m for m in moments if m.kind in ("goal", "low_xg_goal")]
    assert len(goal_moments) == sum(sim.state.score)


def test_moments_are_valid_and_uniquely_numbered(played):
    _, live, _, moments, _ = played
    assert moments == live.moments
    for m in moments:
        Moment.model_validate(m.model_dump())
    assert len({m.moment_id for m in moments}) == len(moments)


def test_leverage_table_is_finite_and_sorted(played):
    _, live, _, _, _ = played
    table = live.leverage_table()
    assert table
    totals = [r.total for r in table]
    assert all(math.isfinite(t) for t in totals)
    assert totals == sorted(totals, reverse=True)


def test_physical_metrics_are_plausible(played):
    _, live, _, _, _ = played
    runs = live.kinematics.runs.values()
    assert max(r.top_speed_ms for r in runs) < 11.0
    measured = [s.speed_ms for s in live.shots if s.speed_ms is not None]
    assert all(5.0 < v < 40.0 for v in measured)
