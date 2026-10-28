"""Gravity for football, the defensive attention a player draws beyond what
is normal for where they are on the pitch and whether they have the ball.

Every tracking frame while a team has the ball, each of its outfield players gets an attention score:
a soft count of outfield defenders around them, where a defender on top of the player counts 1 and
one at the edge of a 6 m radius counts 0. Gravity is that score minus the league-average attention
for the same zone and the same on-ball or off-ball role, times 100. So +50 means half a defender
more than usual, held over the time measured.

The league average comes from simulated matches with full tracking (`fit_baseline`, run by
`python -m engine.gravity` and by calibration) and is stored in `data/models/gravity.json`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from engine.models import Side, TrackingFrame
from engine.pitch import to_attacking

ATTENTION_RADIUS_M = 6.0
CARRIER_M = 2.0  # the attacker nearest a grounded ball within this distance has it
CARRIER_MAX_Z = 1.5
SCALE = 100.0
FINAL_THIRD_X = 70.0  # in attacking coordinates

ZONE_M = (7.5, 6.8)  # baseline zones: 14 along the pitch, 10 across
ZONE_X, ZONE_Y = 14, 10
MIN_ZONE_FRAMES = 60  # below this a zone falls back to the role's overall average

MAP_CELL_M = 3.0  # the heatmap grid
MAP_X, MAP_Y = 35, 23

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "gravity.json"

# Category index = 2 * on_ball + final_third
CATEGORIES = ("build_up_off_ball", "final_third_off_ball", "build_up_on_ball", "final_third_on_ball")


def attention(x: float, y: float, defenders: np.ndarray) -> float:
    """Soft count of defenders within the radius: 1 at the player, falling to 0 at the edge."""
    if defenders.size == 0:
        return 0.0
    d = np.hypot(defenders[:, 0] - x, defenders[:, 1] - y)
    return float(np.clip(1.0 - d / ATTENTION_RADIUS_M, 0.0, None).sum())


def zone(ax: float, ay: float) -> tuple[int, int]:
    return min(max(int(ax / ZONE_M[0]), 0), ZONE_X - 1), min(max(int(ay / ZONE_M[1]), 0), ZONE_Y - 1)


def cell(ax: float, ay: float) -> tuple[int, int]:
    return min(max(int(ax / MAP_CELL_M), 0), MAP_X - 1), min(max(int(ay / MAP_CELL_M), 0), MAP_Y - 1)


@dataclass(frozen=True)
class GravityBaseline:
    """League-average attention by zone (attacking coordinates) for off-ball [0] and on-ball [1] players."""

    expected: tuple[tuple[tuple[float, ...], ...], tuple[tuple[float, ...], ...]]

    def at(self, ax: float, ay: float, on_ball: bool) -> float:
        zx, zy = zone(ax, ay)
        return self.expected[int(on_ball)][zx][zy]

    def to_json(self) -> dict:
        return {"off_ball": [list(r) for r in self.expected[0]], "on_ball": [list(r) for r in self.expected[1]],
                "zone_m": list(ZONE_M), "radius_m": ATTENTION_RADIUS_M}

    @classmethod
    def from_json(cls, d: dict) -> GravityBaseline:
        rows = lambda key: tuple(tuple(float(v) for v in r) for r in d[key])  # noqa: E731
        return cls((rows("off_ball"), rows("on_ball")))

    @classmethod
    def flat(cls, off_ball: float = 0.5, on_ball: float = 1.0) -> GravityBaseline:
        grid = lambda v: tuple(tuple(v for _ in range(ZONE_Y)) for _ in range(ZONE_X))  # noqa: E731
        return cls((grid(off_ball), grid(on_ball)))

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> GravityBaseline:
        if path.exists():
            found = cls.from_json(json.loads(path.read_text(encoding="utf-8")))
            if len(found.expected[0]) == ZONE_X and len(found.expected[0][0]) == ZONE_Y:
                return found
        return cls.flat()  # no fit yet, or one made for a different zone grid

    def save(self, path: Path = DEFAULT_PATH) -> None:
        path.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")


@dataclass
class GravityRow:
    sums: list[float] = field(default_factory=lambda: [0.0] * 4)
    frames: list[int] = field(default_factory=lambda: [0] * 4)

    def mean(self, *idx: int) -> float | None:
        n = sum(self.frames[i] for i in idx)
        return None if n == 0 else sum(self.sums[i] for i in idx) / n

    @property
    def overall(self) -> float | None:
        return self.mean(0, 1, 2, 3)

    @property
    def total_frames(self) -> int:
        return sum(self.frames)


def _map() -> np.ndarray:
    return np.zeros((MAP_X, MAP_Y))


@dataclass
class TeamMap:
    """Gravity summed by pitch cell (attacking left to right), with frame counts, on and off the ball."""

    on_sum: np.ndarray = field(default_factory=_map)
    on_n: np.ndarray = field(default_factory=_map)
    off_sum: np.ndarray = field(default_factory=_map)
    off_n: np.ndarray = field(default_factory=_map)


class GravityTracker:
    def __init__(self, keepers: set[str], baseline: GravityBaseline | None = None) -> None:
        self.keepers = keepers
        self.baseline = baseline or GravityBaseline.load()
        self.rows: dict[str, GravityRow] = {}
        self.teams: dict[str, Side] = {}
        self.maps: dict[Side, TeamMap] = {"home": TeamMap(), "away": TeamMap()}
        # Raw attention by zone, for fitting the league baseline: [on_ball, zx, zy]
        self.zone_sum = np.zeros((2, ZONE_X, ZONE_Y))
        self.zone_n = np.zeros((2, ZONE_X, ZONE_Y))

    def update(self, frame: TrackingFrame, possession: Side | None) -> None:
        if possession is None:
            return
        attackers = [p for p in frame.players if p.team == possession and p.id not in self.keepers]
        defenders = np.array([[p.x, p.y] for p in frame.players if p.team != possession and p.id not in self.keepers])
        if not attackers:
            return
        carrier = None
        if frame.ball.z <= CARRIER_MAX_Z:
            near = min(attackers, key=lambda p: (p.x - frame.ball.x) ** 2 + (p.y - frame.ball.y) ** 2)
            if (near.x - frame.ball.x) ** 2 + (near.y - frame.ball.y) ** 2 <= CARRIER_M**2:
                carrier = near.id
        team_map = self.maps[possession]
        for p in attackers:
            on_ball = p.id == carrier
            ax, ay = to_attacking(p.x, p.y, possession)
            att = attention(p.x, p.y, defenders)
            g = SCALE * (att - self.baseline.at(ax, ay, on_ball))
            idx = 2 * int(on_ball) + int(ax >= FINAL_THIRD_X)
            row = self.rows.setdefault(p.id, GravityRow())
            self.teams[p.id] = possession
            row.sums[idx] += g
            row.frames[idx] += 1
            cx, cy = cell(ax, ay)
            if on_ball:
                team_map.on_sum[cx, cy] += g
                team_map.on_n[cx, cy] += 1
            else:
                team_map.off_sum[cx, cy] += g
                team_map.off_n[cx, cy] += 1
            zx, zy = zone(ax, ay)
            self.zone_sum[int(on_ball), zx, zy] += att
            self.zone_n[int(on_ball), zx, zy] += 1


def fit_baseline(parts: list[tuple[np.ndarray, np.ndarray]]) -> GravityBaseline:
    """League-average attention per zone and role from many matches' raw zone sums and counts."""
    total = sum(s for s, _ in parts)
    count = sum(n for _, n in parts)
    expected = []
    for role in (0, 1):
        n_role = count[role].sum()
        fallback = float(total[role].sum() / n_role) if n_role else (0.5, 1.0)[role]
        grid = np.where(count[role] >= MIN_ZONE_FRAMES, total[role] / np.maximum(count[role], 1), fallback)
        expected.append(tuple(tuple(round(float(v), 4) for v in row) for row in grid))
    return GravityBaseline((expected[0], expected[1]))


# Fitting from simulated tracked matches

FIT_SEED = 950
FIT_MATCHES = 8


def _fit_job(i: int) -> tuple[np.ndarray, np.ndarray]:
    from engine.league import build_league
    from engine.live import LiveStats
    from engine.models import MatchMeta
    from engine.sim import MatchSimulator, SimConfig

    clubs = ["KR", "AV", "CC", "EA", "NA", "BF", "RU", "TW", "WH", "SM"]
    league = build_league()
    meta = MatchMeta(match_id=f"g{i:03d}", home=clubs[i % 10], away=clubs[(i + 3) % 10], seed=FIT_SEED + i)
    sim = MatchSimulator(meta, league, SimConfig(mode="full"))
    live = LiveStats(meta, league, gravity=GravityBaseline.flat())  # raw attention does not use the baseline
    while not sim.finished:
        for item in sim.step():
            live.push(item)
    return live.gravity.zone_sum, live.gravity.zone_n


def main() -> None:
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor() as pool:
        parts = list(pool.map(_fit_job, range(FIT_MATCHES)))
    baseline = fit_baseline(parts)
    baseline.save()
    print(f"Gravity baseline fitted on {FIT_MATCHES} tracked matches, saved to {DEFAULT_PATH}")
    for role, name in ((0, "off the ball"), (1, "on the ball")):
        print(f"  {name}: " + ", ".join(f"{np.mean(row):.2f}" for row in baseline.expected[role]))


if __name__ == "__main__":
    main()
