"""Expected threat (xT) on a 16 x 12 grid, fitted from event data by value iteration.

xT(z) = s(z) * g(z) + m(z) * SUM_w T(z -> w) * xT(w)

s: share of actions in zone z that are shots, g: goal rate of those shots,
m: share that are moves (passes, carries), T: chance a move from z ends safely in w.
All zones are in the acting team's attacking frame.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from engine.metrics import xg
from engine.models import EventType, MatchEvent
from engine.pitch import PITCH_LENGTH, PITCH_WIDTH, to_attacking

GRID_X = 16
GRID_Y = 12
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "xt.json"

# Pseudo counts so thinly sampled zones lean on the xG model instead of noise.
SHOT_PRIOR = 4.0


def zone(x_att: float, y_att: float) -> tuple[int, int]:
    ix = min(max(int(x_att / PITCH_LENGTH * GRID_X), 0), GRID_X - 1)
    iy = min(max(int(y_att / PITCH_WIDTH * GRID_Y), 0), GRID_Y - 1)
    return ix, iy


def zone_center(ix: int, iy: int) -> tuple[float, float]:
    return (ix + 0.5) * PITCH_LENGTH / GRID_X, (iy + 0.5) * PITCH_WIDTH / GRID_Y


@dataclass(frozen=True)
class XTGrid:
    values: np.ndarray  # shape (GRID_X, GRID_Y)

    def at(self, x_att: float, y_att: float) -> float:
        ix, iy = zone(x_att, y_att)
        return float(self.values[ix, iy])

    def to_json(self) -> str:
        return json.dumps({"grid_x": GRID_X, "grid_y": GRID_Y, "values": np.round(self.values, 6).tolist()})

    @classmethod
    def from_json(cls, text: str) -> XTGrid:
        data = json.loads(text)
        return cls(values=np.array(data["values"], dtype=float))

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> XTGrid:
        """The fitted grid if it has been generated, otherwise the xG-based fallback."""
        if path.exists():
            return cls.from_json(path.read_text(encoding="utf-8"))
        return fallback_xt()


def fallback_xt() -> XTGrid:
    """A rough grid from the xG model alone, used before a fitted grid exists."""
    values = np.zeros((GRID_X, GRID_Y))
    for ix in range(GRID_X):
        for iy in range(GRID_Y):
            x, y = zone_center(ix, iy)
            values[ix, iy] = 0.5 * xg(x, y) + 0.01 * (x / PITCH_LENGTH) ** 2
    return XTGrid(values)


def fit_xt(events: Iterable[MatchEvent], iterations: int = 40) -> XTGrid:
    shots = np.zeros((GRID_X, GRID_Y))
    goals = np.zeros((GRID_X, GRID_Y))
    moves = np.zeros((GRID_X, GRID_Y))
    transitions = np.zeros((GRID_X, GRID_Y, GRID_X, GRID_Y))

    for e in events:
        sx, sy = to_attacking(e.x, e.y, e.team)
        z = zone(sx, sy)
        if e.type == EventType.SHOT:
            shots[z] += 1
            goals[z] += e.outcome == "goal"
        elif e.type in (EventType.PASS, EventType.CARRY) and e.end_x is not None and e.end_y is not None:
            moves[z] += 1
            if e.outcome in (None, "complete"):
                ex, ey = to_attacking(e.end_x, e.end_y, e.team)
                transitions[z + zone(ex, ey)] += 1

    prior_g = np.array([[xg(*zone_center(ix, iy)) for iy in range(GRID_Y)] for ix in range(GRID_X)])
    g = (goals + SHOT_PRIOR * prior_g) / (shots + SHOT_PRIOR)
    actions = shots + moves
    s = np.divide(shots, actions, out=np.zeros_like(shots), where=actions > 0)
    m = np.divide(moves, actions, out=np.zeros_like(moves), where=actions > 0)
    t = np.divide(
        transitions,
        moves[:, :, None, None],
        out=np.zeros_like(transitions),
        where=moves[:, :, None, None] > 0,
    )

    value = np.zeros((GRID_X, GRID_Y))
    for _ in range(iterations):
        value = s * g + m * np.einsum("abcd,cd->ab", t, value)
    return XTGrid(value)
