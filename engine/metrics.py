"""Public metric models. See docs/SPEC.md section 8.

These are the league-wide models a broadcaster would run. The simulator samples
outcomes from richer "true" functions that also use hidden player traits, so the
metrics here have to recover the truth from data, the way real models do.
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from engine.models import TrackingFrame
from engine.pitch import CENTER_Y, GOAL_Y_HIGH, GOAL_Y_LOW, PITCH_LENGTH, goal_geometry


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


# Expected goals: a logistic model of distance, goal-mouth angle, header, pressure and the
# distance to the nearest outfield defender (the NBA's "defender contest"). The coefficients
# are fitted by regression on simulated shots (engine/calibrate.py writes data/models/xg.json).
# PRIOR_XG is the hand-set starting point used until a fitted model exists.

XG_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "xg.json"
DEFENDER_CAP_M = 8.0  # a defender further than this does not affect the shot


@dataclass(frozen=True)
class XGModel:
    intercept: float
    distance: float
    angle: float
    header: float
    pressure: float
    defender: float = 0.0
    defender_default: float = 3.0  # used when a shot comes without defender positions

    def logit(
        self, x_att: float, y_att: float, header: bool = False, pressure: float = 0.0, defender_m: float | None = None
    ) -> float:
        distance, angle = goal_geometry(x_att, y_att)
        d = self.defender_default if defender_m is None else min(defender_m, DEFENDER_CAP_M)
        return (
            self.intercept
            + self.distance * distance
            + self.angle * angle
            + self.header * float(header)
            + self.pressure * pressure
            + self.defender * d
        )

    def prob(
        self, x_att: float, y_att: float, header: bool = False, pressure: float = 0.0, defender_m: float | None = None
    ) -> float:
        return sigmoid(self.logit(x_att, y_att, header, pressure, defender_m))

    def logit_array(self, x_att: np.ndarray, y_att: np.ndarray) -> np.ndarray:
        """Unpressured, footed shots from many spots at once."""
        dx = np.maximum(PITCH_LENGTH - x_att, 0.1)
        distance = np.hypot(dx, CENTER_Y - y_att)
        angle = np.abs(np.arctan2(GOAL_Y_HIGH - y_att, dx) - np.arctan2(GOAL_Y_LOW - y_att, dx))
        return self.intercept + self.distance * distance + self.angle * angle + self.defender * self.defender_default

    def to_json(self) -> str:
        return json.dumps({k: round(v, 5) for k, v in asdict(self).items()}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> XGModel:
        return cls(**json.loads(text))

    @classmethod
    def load(cls, path: Path = XG_PATH) -> XGModel:
        return cls.from_json(path.read_text(encoding="utf-8")) if path.exists() else PRIOR_XG


# Unpressured central shots: 6 m about 0.49, 11 m about 0.24, 16 m about 0.12, 25 m about 0.04.
PRIOR_XG = XGModel(intercept=-0.8, distance=-0.11, angle=1.3, header=-1.0, pressure=-0.8)
XG_MODEL = XGModel.load()


def xg_logit(
    x_att: float, y_att: float, header: bool = False, pressure: float = 0.0, defender_m: float | None = None
) -> float:
    return XG_MODEL.logit(x_att, y_att, header, pressure, defender_m)


def xg(
    x_att: float, y_att: float, header: bool = False, pressure: float = 0.0, defender_m: float | None = None
) -> float:
    """Probability that a shot from this spot, in the shooter's attacking frame, is a goal."""
    return XG_MODEL.prob(x_att, y_att, header, pressure, defender_m)


def nearest_defender(x: float, y: float, defenders: list[list[float]] | list[tuple[float, float]]) -> float | None:
    """Distance from a shot to the closest outfield defender, from a freeze frame or tracking frame."""
    if not defenders:
        return None
    return min(math.hypot(dx - x, dy - y) for dx, dy in defenders)


def shot_features(
    x_att: float, y_att: float, header: bool, pressure: float, defender_m: float | None, default_defender: float
) -> list[float]:
    distance, angle = goal_geometry(x_att, y_att)
    d = default_defender if defender_m is None else min(defender_m, DEFENDER_CAP_M)
    return [1.0, distance, angle, float(header), pressure, d]


def fit_xg(features: list[list[float]], goals: list[float], ridge: float = 1e-3, iterations: int = 30) -> XGModel:
    """Logistic regression by Newton's method (iteratively reweighted least squares) with a small ridge."""
    X = np.array(features, dtype=float)
    y = np.array(goals, dtype=float)
    beta = np.zeros(X.shape[1])
    beta[0] = math.log(max(y.mean(), 1e-6) / max(1 - y.mean(), 1e-6))
    penalty = ridge * np.eye(X.shape[1])
    penalty[0, 0] = 0.0
    for _ in range(iterations):
        p = 1.0 / (1.0 + np.exp(-X @ beta))
        w = p * (1.0 - p)
        gradient = X.T @ (y - p) - penalty @ beta
        hessian = (X * w[:, None]).T @ X + penalty
        step = np.linalg.solve(hessian, gradient)
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    defaults = np.median(X[:, 5])
    return XGModel(
        intercept=float(beta[0]), distance=float(beta[1]), angle=float(beta[2]), header=float(beta[3]),
        pressure=float(beta[4]), defender=float(beta[5]), defender_default=float(defaults),
    )


# Pass completion. Forward is the cosine of the pass direction against the attack
# direction: 1 straight forward, -1 straight back.
PASS = {"intercept": 3.9, "distance": -0.075, "forward": -0.65, "pressure": -1.5}


def pass_logit(sx: float, sy: float, ex: float, ey: float, pressure: float = 0.0) -> float:
    distance = math.hypot(ex - sx, ey - sy)
    forward = (ex - sx) / distance if distance > 0 else 0.0
    return PASS["intercept"] + PASS["distance"] * distance + PASS["forward"] * forward + PASS["pressure"] * pressure


def pass_completion(sx: float, sy: float, ex: float, ey: float, pressure: float = 0.0) -> float:
    """Probability a pass from start to end (attacking frame) is completed."""
    return sigmoid(pass_logit(sx, sy, ex, ey, pressure))


def pass_difficulty(sx: float, sy: float, ex: float, ey: float, pressure: float = 0.0) -> float:
    return 1.0 - pass_completion(sx, sy, ex, ey, pressure)


# Vectorized versions for the simulator, which scores every pass option at once.


def pass_logit_array(sx: float, sy: float, ex: np.ndarray, ey: np.ndarray, pressure: float) -> np.ndarray:
    distance = np.maximum(np.hypot(ex - sx, ey - sy), 1e-6)
    forward = (ex - sx) / distance
    return PASS["intercept"] + PASS["distance"] * distance + PASS["forward"] * forward + PASS["pressure"] * pressure


# Physical metrics, all derived from tracking frames.

SPRINT_MS = 7.0
HSR_MS = 5.5
SPRINT_MIN_S = 1.0
TELEPORT_MS = 13.0  # faster than any human: a substitution or restart, not a run
BALL_MAX_MS = 45.0
SMOOTHING_FRAMES = 3


HEAT_CELL_M = 5.0
HEAT_X = 21  # 105 m / 5 m
HEAT_Y = 14  # 68 m / 5 m, last row a little short


@dataclass
class RunStats:
    distance_m: float = 0.0
    hsr_m: float = 0.0
    top_speed_ms: float = 0.0
    sprints: int = 0
    speed_ms: float = 0.0
    heat: np.ndarray = field(default_factory=lambda: np.zeros((HEAT_X, HEAT_Y), dtype=np.int32))  # frames per 5 m cell
    _sprint_s: float = 0.0
    _sprint_counted: bool = False
    _recent: deque = field(default_factory=lambda: deque(maxlen=SMOOTHING_FRAMES))


class Kinematics:
    """Distance, high-speed running, sprints, top speed and ball speed, from frame to frame positions."""

    def __init__(self) -> None:
        self.runs: dict[str, RunStats] = {}
        self.ball_speed_ms = 0.0
        self._prev: dict[str, tuple[float, float]] = {}
        self._prev_ball: tuple[float, float, float] | None = None
        self._prev_t: float | None = None
        self._ball_history: deque[tuple[float, float]] = deque(maxlen=60)

    def update(self, frame: TrackingFrame) -> None:
        dt = None if self._prev_t is None else frame.t - self._prev_t
        for p in frame.players:
            run = self.runs.setdefault(p.id, RunStats())
            run.heat[min(int(p.x / HEAT_CELL_M), HEAT_X - 1), min(int(p.y / HEAT_CELL_M), HEAT_Y - 1)] += 1
            prev = self._prev.get(p.id)
            if dt and dt > 0 and prev is not None:
                step = math.hypot(p.x - prev[0], p.y - prev[1])
                raw = step / dt
                if raw <= TELEPORT_MS:
                    run.distance_m += step
                    run._recent.append(raw)
                    run.speed_ms = sum(run._recent) / len(run._recent)
                    if run.speed_ms >= HSR_MS:
                        run.hsr_m += step
                    run.top_speed_ms = max(run.top_speed_ms, run.speed_ms)
                    if run.speed_ms >= SPRINT_MS:
                        run._sprint_s += dt
                        if run._sprint_s >= SPRINT_MIN_S and not run._sprint_counted:
                            run.sprints += 1
                            run._sprint_counted = True
                    else:
                        run._sprint_s = 0.0
                        run._sprint_counted = False
                else:
                    run._recent.clear()
            self._prev[p.id] = (p.x, p.y)

        ball = (frame.ball.x, frame.ball.y, frame.ball.z)
        if dt and dt > 0 and self._prev_ball is not None:
            speed = math.dist(ball, self._prev_ball) / dt
            if speed <= BALL_MAX_MS:
                self.ball_speed_ms = speed
                self._ball_history.append((frame.t, speed))
        self._prev_ball = ball
        self._prev_t = frame.t

    def ball_speed_after(self, t0: float, frames: int = 2) -> float | None:
        """Ball speed over the first frames after t0, for example the moment a shot is struck.

        Only the first frames count, so a later restart that moves the ball does not inflate it.
        """
        speeds = [s for t, s in self._ball_history if t > t0][:frames]
        return sum(speeds) / len(speeds) if speeds else None
