"""The ingest boundary: a recorded feed must replay a match exactly."""

from engine.feed import RecordedFeed, SimulatorFeed, record
from engine.hashing import stable_hash
from engine.league import build_league
from engine.live import LiveStats
from engine.models import MatchMeta
from engine.sim import MatchSimulator, SimConfig

META = MatchMeta(match_id="m001", home="KR", away="AV", seed=7)
CONFIG = SimConfig(mode="full", half_s=120.0)


def play(feed) -> tuple[str, str]:
    live = LiveStats(feed.meta, build_league())
    items, moments = [], []
    while not feed.finished:
        for item in feed.step():
            items.append(item)
            moments += live.push(item)
    return stable_hash(items), stable_hash(moments + [live.stats()])


def test_simulator_feed_exposes_match_and_lineups():
    feed = SimulatorFeed(MatchSimulator(META, build_league(), CONFIG))
    assert feed.meta == META and feed.dt == 0.2
    assert len(feed.lineups["home"]) == 11 and feed.lineups["home"][0] == "KR01"


def test_recorded_feed_replays_the_match_exactly(tmp_path):
    path = tmp_path / "match.jsonl"
    ticks = record(SimulatorFeed(MatchSimulator(META, build_league(), CONFIG)), path)
    assert ticks == 1201  # 1200 ticks of play, then the empty tick that marks full time
    live_run = play(SimulatorFeed(MatchSimulator(META, build_league(), CONFIG)))
    replay = RecordedFeed(path)
    assert replay.meta == META and replay.lineups["away"][0] == "AV01"
    assert play(replay) == live_run
