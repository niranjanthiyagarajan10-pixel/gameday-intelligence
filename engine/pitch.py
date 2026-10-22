"""Pitch geometry. Units are meters.

Home always attacks toward x = PITCH_LENGTH and away toward x = 0, in both halves.
Metrics work in a team's attacking frame, where that team attacks toward x = 105.
"""

from __future__ import annotations

import math

import numpy as np

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
CENTER_X = PITCH_LENGTH / 2
CENTER_Y = PITCH_WIDTH / 2

GOAL_WIDTH = 7.32
GOAL_HEIGHT = 2.44
GOAL_Y_LOW = (PITCH_WIDTH - GOAL_WIDTH) / 2
GOAL_Y_HIGH = (PITCH_WIDTH + GOAL_WIDTH) / 2

PENALTY_SPOT_DISTANCE = 11.0
BOX_DEPTH = 16.5
BOX_WIDTH = 40.32

# The ball can leave the field of play. Players in the simulation cannot.
BALL_MARGIN = 3.0
PLAYER_MARGIN = 0.5

TRACKING_HZ = 5


def to_attacking(x: float, y: float, team: str) -> tuple[float, float]:
    """Pitch coordinates seen from a team that attacks toward x = 105. The transform is its own inverse."""
    if team == "home":
        return x, y
    return PITCH_LENGTH - x, PITCH_WIDTH - y


from_attacking = to_attacking


def goal_geometry(x_att: float, y_att: float) -> tuple[float, float]:
    """Distance to the centre of the goal being attacked, and the angle the goal mouth opens up (radians)."""
    dx = max(PITCH_LENGTH - x_att, 0.1)
    distance = math.hypot(dx, CENTER_Y - y_att)
    angle = abs(math.atan2(GOAL_Y_HIGH - y_att, dx) - math.atan2(GOAL_Y_LOW - y_att, dx))
    return distance, angle


def in_box(x_att: float, y_att: float) -> bool:
    return x_att >= PITCH_LENGTH - BOX_DEPTH and abs(y_att - CENTER_Y) <= BOX_WIDTH / 2


def clamp_to_pitch(x: float, y: float, margin: float = PLAYER_MARGIN) -> tuple[float, float]:
    return (
        min(max(x, margin), PITCH_LENGTH - margin),
        min(max(y, margin), PITCH_WIDTH - margin),
    )


def hull_area(points: np.ndarray) -> float:
    """Area of the convex hull of (n, 2) points, by the monotone chain method."""
    if len(points) < 3:
        return 0.0
    pts = sorted(map(tuple, points))

    def cross(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    area = 0.0
    for i in range(len(hull)):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % len(hull)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2
