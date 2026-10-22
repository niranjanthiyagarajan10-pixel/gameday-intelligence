"""Same seed, same output. This test must always pass."""

from engine.hashing import stable_hash
from engine.league import build_league
from engine.live import LiveStats
from engine.models import MatchMeta
from engine.sim import MatchSimulator, SimConfig

CONFIG = SimConfig(mode="full", half_s=300.0)


def play(seed: int) -> tuple[str, str]:
    league = build_league()
    meta = MatchMeta(match_id="m001", home="KR", away="AV", seed=seed)
    live = LiveStats(meta, league)
    outputs, moments = [], []
    for item in MatchSimulator(meta, league, CONFIG).run():
        outputs.append(item)
        moments += live.push(item)
    return stable_hash(outputs), stable_hash(moments + [live.stats()])


def test_same_seed_gives_same_match_and_same_stats():
    assert play(7) == play(7)


def test_different_seed_gives_different_match():
    assert play(7)[0] != play(8)[0]
