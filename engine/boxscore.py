"""The match box score: the team stats a fan expects from any results page.

Shots, shots on target, passes, pass accuracy, fouls, cards and corners, per side. Counted
from the event stream, except corners, which the simulator plays as a restart with no event
of their own. A corner is counted when the ball comes to rest on a corner spot.
"""

from __future__ import annotations

import math
from typing import Any

from engine.models import EventType, MatchEvent, Side, TrackingFrame
from engine.pitch import PITCH_LENGTH, PITCH_WIDTH

SIDES: tuple[Side, Side] = ("home", "away")
ON_TARGET = {"goal", "saved"}
CORNER_SPOT_M = 1.5  # the ball sits within this of the corner flag while a corner is set up
CORNER_STILL_FRAMES = 2  # and stays there for this many frames, so a ball rolling past is not one


class BoxScore:
    def __init__(self) -> None:
        self.shots = [0, 0]
        self.on_target = [0, 0]
        self.passes = [0, 0]
        self.completed = [0, 0]
        self.fouls = [0, 0]
        self.yellows = [0, 0]
        self.reds = [0, 0]
        self.corners = [0, 0]
        self._still = 0
        self._counted = False

    def event(self, e: MatchEvent) -> None:
        k = SIDES.index(e.team)
        if e.type == EventType.SHOT:
            self.shots[k] += 1
            if e.outcome in ON_TARGET:
                self.on_target[k] += 1
        elif e.type == EventType.PASS:
            self.passes[k] += 1
            if e.outcome == "complete":
                self.completed[k] += 1
        elif e.type == EventType.FOUL:
            self.fouls[k] += 1
        elif e.type == EventType.CARD:
            if e.outcome == "yellow":
                self.yellows[k] += 1
            elif e.outcome == "red":
                self.reds[k] += 1

    def frame(self, frame: TrackingFrame) -> None:
        b = frame.ball
        near_end = b.x <= CORNER_SPOT_M or b.x >= PITCH_LENGTH - CORNER_SPOT_M
        near_side = b.y <= CORNER_SPOT_M or b.y >= PITCH_WIDTH - CORNER_SPOT_M
        if not (near_end and near_side and b.z == 0.0):
            self._still = 0
            self._counted = False
            return
        self._still += 1
        if self._still >= CORNER_STILL_FRAMES and not self._counted:
            self._counted = True
            # Home attacks toward x = 105 in both halves, so a corner at that end is a home corner.
            self.corners[0 if b.x > PITCH_LENGTH / 2 else 1] += 1

    def to_dict(self, xg: tuple[float, float], possession: tuple[float, float]) -> dict[str, Any]:
        """Rows in the order a results page shows them. Values are per side: home, away."""
        accuracy = [round(100 * c / p) if p else 0 for c, p in zip(self.completed, self.passes)]
        return {
            "rows": [
                {"key": "xg", "label": "Expected goals (xG)", "values": [round(xg[0], 2), round(xg[1], 2)]},
                {"key": "shots", "label": "Shots", "values": list(self.shots)},
                {"key": "on_target", "label": "Shots on target", "values": list(self.on_target)},
                {"key": "possession", "label": "Possession", "values": [round(100 * possession[0]), round(100 * possession[1])], "unit": "%"},
                {"key": "passes", "label": "Passes", "values": list(self.passes)},
                {"key": "pass_accuracy", "label": "Pass accuracy", "values": accuracy, "unit": "%"},
                {"key": "fouls", "label": "Fouls", "values": list(self.fouls), "lower_better": True},
                {"key": "yellows", "label": "Yellow cards", "values": list(self.yellows), "lower_better": True},
                {"key": "reds", "label": "Red cards", "values": list(self.reds), "lower_better": True},
                {"key": "corners", "label": "Corners", "values": list(self.corners)},
            ]
        }


def leader(values: list[float], lower_better: bool = False) -> int | None:
    """Which side leads a row: 0 home, 1 away, None when level."""
    a, b = values
    if math.isclose(a, b):
        return None
    return int((b < a) if lower_better else (b > a))
