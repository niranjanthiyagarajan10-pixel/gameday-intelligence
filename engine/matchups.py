"""Marking matchups from tracking, adapted from the NBA defensive matchup data.

Every tracking frame while a team has the ball, each of its outfield players is marked by the
nearest outfield defender. Time is added to that pair, and what the attacker does while marked
(shots, their xG and goals, passes received) is charged to that defender, as are tackles the
defender wins from that attacker.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.models import Side, TrackingFrame

MAX_FRAME_GAP_S = 1.0


@dataclass
class Allowed:
    shots: int = 0
    xg: float = 0.0
    goals: int = 0
    received: int = 0
    tackles: int = 0


@dataclass(frozen=True)
class Matchup:
    defender: str
    attacker: str
    seconds: float  # time the defender was the attacker's nearest marker
    defending_s: float  # all the time the defender spent defending
    share: float  # seconds / defending_s
    allowed: Allowed


class MarkingTracker:
    def __init__(self, keepers: set[str]) -> None:
        self.keepers = keepers
        self.time: dict[tuple[str, str], float] = {}  # (defender, attacker) -> seconds
        self.defending: dict[str, float] = {}  # defender -> seconds the other team had the ball
        self.attacking: dict[str, float] = {}  # attacker -> seconds their team had the ball
        self.teams: dict[str, Side] = {}
        self.current: dict[str, str] = {}  # attacker -> defender marking them now
        self.allowed: dict[tuple[str, str], Allowed] = {}
        self._last_t: float | None = None

    def update(self, frame: TrackingFrame, possession: Side | None) -> None:
        dt = 0.0 if self._last_t is None else min(max(frame.t - self._last_t, 0.0), MAX_FRAME_GAP_S)
        self._last_t = frame.t
        if possession is None:
            return
        attackers = [p for p in frame.players if p.team == possession and p.id not in self.keepers]
        defenders = [p for p in frame.players if p.team != possession and p.id not in self.keepers]
        for d in defenders:
            self.defending[d.id] = self.defending.get(d.id, 0.0) + dt
            self.teams[d.id] = d.team
        self.current = {}
        if not defenders:
            return
        for a in attackers:
            self.teams[a.id] = a.team
            self.attacking[a.id] = self.attacking.get(a.id, 0.0) + dt
            d = min(defenders, key=lambda p: (p.x - a.x) ** 2 + (p.y - a.y) ** 2)
            self.current[a.id] = d.id
            self.time[(d.id, a.id)] = self.time.get((d.id, a.id), 0.0) + dt

    def _charge(self, attacker: str) -> Allowed | None:
        d = self.current.get(attacker)
        return None if d is None else self.allowed.setdefault((d, attacker), Allowed())

    def on_shot(self, attacker: str, xg: float, goal: bool) -> None:
        if (a := self._charge(attacker)) is not None:
            a.shots += 1
            a.xg += xg
            a.goals += int(goal)

    def on_received(self, attacker: str) -> None:
        if (a := self._charge(attacker)) is not None:
            a.received += 1

    def on_tackle(self, defender: str, attacker: str) -> None:
        self.allowed.setdefault((defender, attacker), Allowed()).tackles += 1

    def matchup(self, defender: str, attacker: str) -> Matchup:
        seconds = self.time.get((defender, attacker), 0.0)
        defending = self.defending.get(defender, 0.0)
        return Matchup(defender, attacker, round(seconds, 1), round(defending, 1),
                       round(seconds / defending, 3) if defending else 0.0,
                       self.allowed.get((defender, attacker), Allowed()))

    def main_marker(self, attacker: str) -> Matchup | None:
        """The defender who marked this attacker for the longest."""
        pairs = [(s, d) for (d, a), s in self.time.items() if a == attacker]
        if not pairs:
            return None
        _, defender = max(pairs)
        return self.matchup(defender, attacker)
