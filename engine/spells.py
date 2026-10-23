"""Spells of dominance: football's version of a scoring run. For each team, the stretch of play
(a fixed number of minutes) in which it added the most threat (xT) above its opponent."""

from __future__ import annotations

from dataclasses import dataclass

from engine.models import Side

SPELL_MINUTES = 10
MIN_SHARE = 0.6  # a spell must hold at least this share of the threat to count


@dataclass(frozen=True)
class Spell:
    team: Side
    start: int  # first minute, inclusive
    end: int  # last minute, exclusive
    share: float  # team's share of the threat added in the spell
    shots: int
    goals: int
    xg: float


@dataclass
class MinuteBucket:
    xt: list[float]
    shots: list[int]
    goals: list[int]
    xg: list[float]


def empty_bucket() -> MinuteBucket:
    return MinuteBucket([0.0, 0.0], [0, 0], [0, 0], [0.0, 0.0])


def best_spells(minutes: list[MinuteBucket], length: int = SPELL_MINUTES) -> dict[Side, Spell | None]:
    """For each team the window with the largest threat margin over the opponent, if it dominated."""
    out: dict[Side, Spell | None] = {"home": None, "away": None}
    if len(minutes) < length:
        return out
    for k, side in enumerate(("home", "away")):
        best: tuple[float, int] | None = None
        for start in range(0, len(minutes) - length + 1):
            window = minutes[start:start + length]
            margin = sum(b.xt[k] - b.xt[1 - k] for b in window)
            if best is None or margin > best[0] + 1e-12:
                best = (margin, start)
        if best is None or best[0] <= 0:
            continue
        start = best[1]
        window = minutes[start:start + length]
        mine = sum(b.xt[k] for b in window)
        theirs = sum(b.xt[1 - k] for b in window)
        share = mine / (mine + theirs) if mine + theirs > 0 else 0.0
        if share < MIN_SHARE:
            continue
        out[side] = Spell(side, start, start + length, round(share, 3), sum(b.shots[k] for b in window),
                          sum(b.goals[k] for b in window), round(sum(b.xg[k] for b in window), 3))
    return out
