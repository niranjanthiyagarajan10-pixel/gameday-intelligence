"""Team shape out of possession: low block, mid block or high press. See docs/SPEC.md section 8.

From tracking frames, per team while the opponent has the ball in its own half or midfield
(50 to 85 m from the defending goal, where a block is chosen rather than forced), over a
rolling 60 s window:
  line_height = mean distance from own goal of the four deepest outfield players
  compactness = convex hull area of the outfield players
  pressers    = defenders within 5 m of the ball
  low block:  line_height < 30 m and compactness below the baseline
  high press: line_height > 45 m and at least 0.6 pressers on average (calibrated on simulated matches)
  mid block:  otherwise
A change is confirmed only after the new state has held for 60 s.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from engine.models import Side, TrackingFrame
from engine.pitch import PITCH_LENGTH, hull_area

ShapeState = Literal["low_block", "mid_block", "high_press"]
SIDES: tuple[Side, Side] = ("home", "away")

WINDOW_S = 60.0
HOLD_S = 60.0
EVAL_EVERY_S = 5.0
MIN_SAMPLES_S = 10.0
LOW_LINE_M = 30.0
HIGH_LINE_M = 45.0
PRESS_RADIUS_M = 5.0
HIGH_PRESSERS = 0.6
COMPACT_BASELINE_M2 = 1000.0
BACK_LINE = 4
BALL_ZONE_M = (50.0, 85.0)  # ball distance from the defending team's goal


@dataclass(frozen=True)
class ShapeChange:
    team: Side
    t: float
    previous: ShapeState | None
    state: ShapeState
    line_height: float
    compactness: float
    pressers: float


@dataclass
class _TeamShape:
    samples: deque = field(default_factory=deque)  # (t, line_height, compactness, pressers)
    state: ShapeState | None = None
    candidate: ShapeState | None = None
    candidate_since: float = 0.0
    timeline: list[tuple[float, ShapeState]] = field(default_factory=list)


def classify(line_height: float, compactness: float, pressers: float) -> ShapeState:
    if line_height < LOW_LINE_M and compactness < COMPACT_BASELINE_M2:
        return "low_block"
    if line_height > HIGH_LINE_M and pressers >= HIGH_PRESSERS:
        return "high_press"
    return "mid_block"


def measure(frame: TrackingFrame, team: Side, keepers: set[str]) -> tuple[float, float, float] | None:
    """Line height, compactness and pressers for a defending team, or None when the frame says nothing.

    Only frames with the ball away from the defending goal count: a team pinned in its own box
    is deep by force, not by choice, and that is not a low block.
    """
    ball_from_goal = frame.ball.x if team == "home" else PITCH_LENGTH - frame.ball.x
    if not BALL_ZONE_M[0] <= ball_from_goal <= BALL_ZONE_M[1]:
        return None
    pts = np.array([(p.x, p.y) for p in frame.players if p.team == team and p.id not in keepers])
    if len(pts) < BACK_LINE + 2:
        return None
    from_goal = pts[:, 0] if team == "home" else PITCH_LENGTH - pts[:, 0]
    line_height = float(np.mean(np.sort(from_goal)[:BACK_LINE]))
    compactness = hull_area(pts)
    d = np.hypot(pts[:, 0] - frame.ball.x, pts[:, 1] - frame.ball.y)
    pressers = float(np.sum(d <= PRESS_RADIUS_M))
    return line_height, compactness, pressers


class ShapeTracker:
    def __init__(self, keepers: set[str]) -> None:
        self.keepers = keepers
        self.teams = {side: _TeamShape() for side in SIDES}
        self._next_eval = 0.0

    def update(self, frame: TrackingFrame, possession: Side | None) -> list[ShapeChange]:
        if possession is not None:
            defending = SIDES[1 - SIDES.index(possession)]
            m = measure(frame, defending, self.keepers)
            if m is not None:
                samples = self.teams[defending].samples
                samples.append((frame.t, *m))
        for team in self.teams.values():
            while team.samples and team.samples[0][0] < frame.t - WINDOW_S:
                team.samples.popleft()
        if frame.t < self._next_eval:
            return []
        self._next_eval = frame.t + EVAL_EVERY_S
        return [c for side in SIDES if (c := self._evaluate(side, frame.t)) is not None]

    def window(self, side: Side) -> tuple[float, float, float] | None:
        s = self.teams[side].samples
        if not s or s[-1][0] - s[0][0] < MIN_SAMPLES_S:
            return None
        arr = np.array([row[1:] for row in s])
        return float(arr[:, 0].mean()), float(arr[:, 1].mean()), float(arr[:, 2].mean())

    def _evaluate(self, side: Side, t: float) -> ShapeChange | None:
        team = self.teams[side]
        w = self.window(side)
        if w is None:
            return None
        current = classify(*w)
        if team.state is None:
            team.state = current
            team.timeline.append((t, current))
            return None
        if current == team.state:
            team.candidate = None
            return None
        if current != team.candidate:
            team.candidate = current
            team.candidate_since = t
            return None
        if t - team.candidate_since < HOLD_S:
            return None
        previous = team.state
        team.state = current
        team.candidate = None
        team.timeline.append((team.candidate_since, current))
        return ShapeChange(side, t, previous, current, *w)
