"""Same seed, same output. This test must always pass.

Until the simulator lands in M1 it runs on a small stand-in that draws events and
frames through engine.rng the same way the simulator will.
"""

from engine.hashing import stable_hash
from engine.models import MatchEvent, TrackingFrame
from engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from engine.rng import SeedTree


def stand_in_match(seed: int) -> list[MatchEvent | TrackingFrame]:
    tree = SeedTree(seed).child("m001")
    where = tree.generator("positions")
    pressure = tree.generator("pressure")
    out: list[MatchEvent | TrackingFrame] = []
    for i in range(50):
        x, y = where.uniform(0, PITCH_LENGTH), where.uniform(0, PITCH_WIDTH)
        out.append(
            MatchEvent(
                event_id=f"m001-{i:06d}",
                match_id="m001",
                t=i * 2.0,
                minute=int(i * 2.0 // 60),
                period=1,
                type="pass",
                team="home" if i % 2 else "away",
                player_id="H08",
                x=round(x, 2),
                y=round(y, 2),
                pressure=round(float(pressure.random()), 3),
            )
        )
        out.append(TrackingFrame(t=i * 2.0, ball={"x": round(x, 2), "y": round(y, 2)}, players=[]))
    return out


def test_same_seed_gives_same_hash():
    assert stable_hash(stand_in_match(7)) == stable_hash(stand_in_match(7))


def test_different_seed_gives_different_hash():
    assert stable_hash(stand_in_match(7)) != stable_hash(stand_in_match(8))
