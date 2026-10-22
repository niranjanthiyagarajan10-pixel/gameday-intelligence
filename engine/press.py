"""Press resistance, inspired by Bundesliga Pressure Handling. See docs/SPEC.md section 8.

A pressured possession is a pass or carry made with event pressure of at least 0.6, or a duel
the player lost. It counts as retained if the player's team still has the ball 5 s later.
Rates based on fewer than 5 attempts are hidden.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from engine.models import EventType, MatchEvent, Side

PRESSURE_THRESHOLD = 0.6
RETAIN_WINDOW_S = 5.0
MIN_ATTEMPTS = 5


class PossessionTimeline:
    """Which team had the ball at any moment, from possession change events."""

    def __init__(self) -> None:
        self._t: list[float] = []
        self._team: list[Side] = []

    def change(self, t: float, team: Side) -> None:
        self._t.append(t)
        self._team.append(team)

    def at(self, t: float) -> Side | None:
        i = bisect.bisect_right(self._t, t) - 1
        return self._team[i] if i >= 0 else None

    @property
    def current(self) -> Side | None:
        return self._team[-1] if self._team else None

    def share(self, t0: float, t1: float) -> tuple[float, float]:
        """Fraction of [t0, t1] each team had the ball."""
        held = {"home": 0.0, "away": 0.0}
        if t1 <= t0:
            return 0.5, 0.5
        team = self.at(t0)
        cursor = t0
        i = bisect.bisect_right(self._t, t0)
        while i < len(self._t) and self._t[i] < t1:
            if team is not None:
                held[team] += self._t[i] - cursor
            cursor, team = self._t[i], self._team[i]
            i += 1
        if team is not None:
            held[team] += t1 - cursor
        total = held["home"] + held["away"]
        if total <= 0:
            return 0.5, 0.5
        return held["home"] / total, held["away"] / total


@dataclass
class PressRow:
    player_id: str
    team: Side
    attempts: int = 0
    retained: int = 0

    @property
    def rate(self) -> float | None:
        return self.retained / self.attempts if self.attempts >= MIN_ATTEMPTS else None


class PressResistance:
    def __init__(self) -> None:
        self.rows: dict[str, PressRow] = {}
        self._pending: list[tuple[float, str, Side]] = []

    def record(self, event: MatchEvent) -> None:
        if event.type in (EventType.PASS, EventType.CARRY) and event.pressure >= PRESSURE_THRESHOLD:
            if event.player_id:
                self._pending.append((event.t, event.player_id, event.team))
        elif event.type == EventType.TACKLE and event.outcome == "won":
            carrier = event.meta.get("carrier")
            if carrier:
                victim_team: Side = "away" if event.team == "home" else "home"
                self._pending.append((event.t, carrier, victim_team))

    def resolve(self, now: float, timeline: PossessionTimeline) -> None:
        still: list[tuple[float, str, Side]] = []
        for t, player, team in self._pending:
            if now < t + RETAIN_WINDOW_S:
                still.append((t, player, team))
                continue
            row = self.rows.setdefault(player, PressRow(player, team))
            row.attempts += 1
            row.retained += timeline.at(t + RETAIN_WINDOW_S) == team
        self._pending = still

    def table(self) -> list[PressRow]:
        return sorted(self.rows.values(), key=lambda r: (r.rate is None, -(r.rate or 0.0), -r.attempts))
