"""Seeded football match simulator with full player tracking. See docs/SPEC.md section 7.

Each tick (0.2 s) every player moves toward a target shaped by the team's formation,
the ball, the team's block (high press, mid block, low block) and short off-ball runs.
The ball carrier decides every 0.7 to 2.6 seconds whether to shoot, pass, carry or
hold. Outcomes are sampled from "true" functions that use hidden team strengths and
player traits, which the public metrics in engine/metrics.py then try to recover.

Home attacks toward x = 105 in both halves. Same seed, same match.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from engine import metrics
from engine.league import League, formation_lines
from engine.models import (
    MAX_PLAYER_SPEED_MS,
    BallPos,
    Club,
    EventType,
    MatchEvent,
    MatchMeta,
    Player,
    PlayerPos,
    TrackingFrame,
)
from engine.pitch import (
    BALL_MARGIN,
    CENTER_X,
    CENTER_Y,
    GOAL_HEIGHT,
    GOAL_Y_HIGH,
    GOAL_Y_LOW,
    PITCH_LENGTH,
    PITCH_WIDTH,
    PLAYER_MARGIN,
    from_attacking,
    to_attacking,
)
from engine.rng import Generator, SeedTree
from engine.sim.scenario import Incident, Scenario

SIDES = ("home", "away")
Output = MatchEvent | TrackingFrame

# The simulated world's own shooting physics. Frozen on purpose: the public xG model in
# engine/metrics.py is refitted on simulated shots, and must never feed back into the world it measures.
TRUE_XG = metrics.XGModel(intercept=-0.8, distance=-0.11, angle=1.3, header=-1.0, pressure=-0.8)

# Timing (seconds)
DECISION_S = (0.7, 1.9)
CARRY_S = (1.2, 2.6)
HOLD_S = (0.5, 1.1)
HEADER_WINDOW_S = 0.6

# Movement
ACCEL = 4.0
JOG_MS = 3.4
DRIBBLE_MS = 5.2

# Duels and discipline
TACKLE_REACH = 1.2
TACKLE_RATE = 0.055
FOUL_P = 0.3
YELLOW_P = 0.16
STRAIGHT_RED_P = 0.008
PRESSURE_EVENT_M = 2.0

# Shooting and passing behaviour
SHOT_XG_PIVOT = 0.24
SHOT_XG_SLOPE = 22.0
FINISHING_OFFSET = 0.0
LONG_SHOT_P = 0.05
BOX_TACKLE_BOOST = 1.8

# How hidden team strengths shape outcomes. Calibrated so attack and defence drive the chances a
# team creates and concedes, while press and tempo are styles with smaller effects.
ATTACK_PASS_W = 1.0
DEFENCE_PASS_W = 1.6
FINISH_QUALITY_W = 0.5
DUEL_QUALITY_W = 1.0
INTERCEPT_SHARE = 0.4
SOFTMAX_T = 0.07
PROGRESS_W = 9.0

# Out of possession blocks: base line height, block length, block width, max line height
BLOCKS = {
    "high": (50.0, 26.0, 50.0, 58.0),
    "mid": (33.0, 26.0, 48.0, 44.0),
    "low": (21.0, 18.0, 36.0, 28.0),
}
PRESSERS = {"high": 1, "mid": 1, "low": 1}
# Out of possession, defenders shift toward the nearest attacker: 0.1 to 0.5 of the gap by defence quality.
MARKING_BASE = 0.1
MARKING_W = 0.4
# Good defending teams also keep a narrower, tighter block.
DEFENCE_WIDTH_W = 20.0


@dataclass(frozen=True)
class SimConfig:
    mode: Literal["full", "events_only"] = "full"
    half_s: float = 2700.0
    dt: float = 0.2


@dataclass
class Flight:
    kind: Literal["pass", "shot", "loose"]
    sx: float
    sy: float
    ex: float
    ey: float
    t0: float
    t1: float
    peak: float
    team: int
    passer: int
    receiver: int
    result: str
    other: int = -1


@dataclass
class Restart:
    kind: Literal["kickoff", "throw_in", "goal_kick", "free_kick", "corner", "keeper"]
    team: int
    x: float
    y: float
    taker: int


@dataclass
class MatchState:
    tick: int
    period: int
    score: list[int]
    pid: list[str]
    team: np.ndarray
    role: list[str]
    depth: np.ndarray
    lat: np.ndarray
    x: np.ndarray
    y: np.ndarray
    vx: np.ndarray
    vy: np.ndarray
    pace: np.ndarray
    passing: np.ndarray
    finishing: np.ndarray
    stamina: np.ndarray
    fatigue: np.ndarray
    active: np.ndarray
    yellows: np.ndarray
    cooldown: np.ndarray
    run_dx: np.ndarray
    run_dy: np.ndarray
    run_until: np.ndarray
    run_sprint: np.ndarray
    bench: list[list[Player]]
    sub_times: list[list[float]]
    owner: int = -1
    possession: int = -1
    bx: float = CENTER_X
    by: float = CENTER_Y
    bz: float = 0.0
    flight: Flight | None = None
    restart: Restart | None = None
    dead_until: float = 0.0
    next_decision: float = 0.0
    received_t: float = 0.0
    aerial: bool = False
    pressed: bool = False
    corner_cross: bool = False
    carry_target: tuple[float, float] | None = None
    carry_start: tuple[int, float, float] | None = None
    momentum: np.ndarray | None = None
    block: list[str] | None = None
    press_override: list[float | None] | None = None
    next_block_eval: float = 0.0
    incidents: list[Incident] | None = None
    seq: int = 0
    finished: bool = False
    rng: dict[str, Generator] | None = None


class MatchSimulator:
    def __init__(
        self,
        meta: MatchMeta,
        league: League,
        config: SimConfig = SimConfig(),
        scenario: Scenario | None = None,
    ) -> None:
        self.meta = meta
        self.config = config
        self.clubs: tuple[Club, Club] = (league.clubs[meta.home], league.clubs[meta.away])
        self.players: dict[str, Player] = {
            p.player_id: p for club in self.clubs for p in league.squads[club.club_id]
        }
        self.lineups: dict[str, list[Player]] = {}
        self.state = self._initial_state(league, scenario)
        # Slot roles and teams never change (substitutes take over a slot), so these masks are fixed.
        self._home_mask = self.state.team == 0
        self._gk_mask = np.array([r == "GK" for r in self.state.role])
        self._pending: list[Output] = []
        self._kickoff(0, self._pending)

    # Setup

    def _initial_state(self, league: League, scenario: Scenario | None) -> MatchState:
        tree = SeedTree(self.meta.seed).child(self.meta.match_id)
        rng = {name: tree.generator(name) for name in ("decide", "outcome", "move", "discipline", "subs")}
        slots: list[tuple[int, Player, str, float, float]] = []
        bench: list[list[Player]] = [[], []]
        for k, club in enumerate(self.clubs):
            squad = league.squads[club.club_id]
            by_pos = {pos: [p for p in squad if p.position == pos] for pos in ("GK", "DF", "MF", "FW")}
            lines = formation_lines(club.formation)
            starters: list[Player] = [by_pos["GK"][0]]
            slots.append((k, by_pos["GK"][0], "GK", -1.0, 0.0))
            mids_needed = sum(lines[1:-1])
            pools = {"DF": list(by_pos["DF"]), "MF": list(by_pos["MF"]), "FW": list(by_pos["FW"])}
            taken_mf = 0
            for li, count in enumerate(lines):
                role = "DF" if li == 0 else "FW" if li == len(lines) - 1 else "MF"
                depth = li / (len(lines) - 1)
                width = {1: 0.0, 2: 0.35, 3: 0.65, 4: 0.85, 5: 0.9}[count]
                lats = np.linspace(-width, width, count) if count > 1 else np.array([0.0])
                for lat in lats:
                    player = pools[role].pop(0)
                    if role == "MF":
                        taken_mf += 1
                    starters.append(player)
                    slots.append((k, player, role, depth, float(lat)))
            assert taken_mf == mids_needed
            self.lineups[SIDES[k]] = starters
            bench[k] = [p for p in squad if p not in starters]

        n = len(slots)
        state = MatchState(
            tick=0,
            period=1,
            score=[0, 0],
            pid=[p.player_id for _, p, _, _, _ in slots],
            team=np.array([k for k, _, _, _, _ in slots], dtype=np.int8),
            role=[r for _, _, r, _, _ in slots],
            depth=np.array([d for _, _, _, d, _ in slots]),
            lat=np.array([lat for _, _, _, _, lat in slots]),
            x=np.full(n, CENTER_X),
            y=np.full(n, CENTER_Y),
            vx=np.zeros(n),
            vy=np.zeros(n),
            pace=np.array([p.traits.pace for _, p, _, _, _ in slots]),
            passing=np.array([p.traits.passing for _, p, _, _, _ in slots]),
            finishing=np.array([p.traits.finishing for _, p, _, _, _ in slots]),
            stamina=np.array([p.traits.stamina for _, p, _, _, _ in slots]),
            fatigue=np.zeros(n),
            active=np.ones(n, dtype=bool),
            yellows=np.zeros(n, dtype=np.int8),
            cooldown=np.zeros(n),
            run_dx=np.zeros(n),
            run_dy=np.zeros(n),
            run_until=np.zeros(n),
            run_sprint=np.zeros(n, dtype=bool),
            bench=bench,
            sub_times=[sorted(rng["subs"].uniform(58, 82, size=3) * 60) for _ in range(2)],
            momentum=np.zeros(2),
            block=[self._block_level(k, 0.0, None) for k in range(2)],
            press_override=[None, None],
            next_block_eval=60.0,
            incidents=sorted(scenario.incidents, key=lambda i: i.minute) if scenario else [],
            rng=rng,
        )
        return state

    # Public API

    @property
    def t(self) -> float:
        return round(self.state.tick * self.config.dt, 2)

    @property
    def finished(self) -> bool:
        return self.state.finished

    def snapshot(self) -> MatchState:
        return copy.deepcopy(self.state)

    def restore(self, state: MatchState) -> None:
        self.state = copy.deepcopy(state)

    def run(self) -> Iterator[Output]:
        while not self.state.finished:
            yield from self.step()

    def step(self) -> list[Output]:
        s = self.state
        out: list[Output] = self._pending
        self._pending = []
        t = self.t
        half = self.config.half_s
        if t >= 2 * half:
            s.finished = True
            return out
        if s.period == 1 and t >= half:
            s.period = 2
            s.flight = None
            self._kickoff(1, out)

        self._scenario(t, out)
        self._substitutions(t, out)
        self._evaluate_blocks(t)
        self._update_momentum()
        self._update_runs(t)
        self._move_players(t)
        self._move_ball(t, out)

        live = t >= s.dead_until
        if not live and s.restart is not None and t + self.config.dt >= s.dead_until:
            self._take_restart(t)
        if live and s.flight is None:
            if s.owner >= 0:
                self._pressure_event(t, out)
                if not self._tackle(t, out) and t >= s.next_decision:
                    self._decide(t, out)
            else:
                self._loose_pickup(t, out)

        if self.config.mode == "full":
            out.append(self._frame(t))
        s.tick += 1
        return out

    # Events

    def _event(self, t: float, kind: EventType, team: int, slot: int | None, x: float, y: float, **kw) -> MatchEvent:
        s = self.state
        s.seq += 1
        end_x, end_y = kw.pop("end", (None, None))
        if end_x is not None:
            end_x = min(max(end_x, -BALL_MARGIN), PITCH_LENGTH + BALL_MARGIN)
            end_y = min(max(end_y, -BALL_MARGIN), PITCH_WIDTH + BALL_MARGIN)
        return MatchEvent(
            event_id=f"{self.meta.match_id}-{s.seq:06d}",
            match_id=self.meta.match_id,
            t=t,
            minute=min(int(t // 60), 130),
            period=s.period,
            type=kind,
            team=SIDES[team],
            player_id=s.pid[slot] if slot is not None and slot >= 0 else None,
            x=round(min(max(x, 0.0), PITCH_LENGTH), 2),
            y=round(min(max(y, 0.0), PITCH_WIDTH), 2),
            end_x=None if end_x is None else round(end_x, 2),
            end_y=None if end_y is None else round(end_y, 2),
            **kw,
        )

    def _set_possession(self, t: float, team: int, slot: int, reason: str, out: list[Output]) -> None:
        s = self.state
        if team != s.possession:
            out.append(
                self._event(t, EventType.POSSESSION_CHANGE, team, slot, s.bx, s.by, meta={"reason": reason})
            )
        s.possession = team

    def _give_ball(self, t: float, slot: int, out: list[Output], reason: str, aerial: bool = False) -> None:
        s = self.state
        self._set_possession(t, int(s.team[slot]), slot, reason, out)
        s.owner = slot
        s.flight = None
        s.bx, s.by, s.bz = float(s.x[slot]), float(s.y[slot]), 0.0
        s.received_t = t
        s.aerial = aerial
        s.pressed = False
        s.carry_target = None
        s.carry_start = None
        r = s.rng["decide"]
        side = SIDES[s.team[slot]]
        xa, _ = to_attacking(s.x[slot], s.y[slot], side)
        if aerial and xa > 85:
            s.next_decision = t + r.uniform(0.15, 0.35)
        else:
            s.next_decision = t + r.uniform(*DECISION_S) * (1.15 - 0.3 * self.clubs[s.team[slot]].truth.tempo)

    # Restarts

    def _kickoff_targets(self, k: int, idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        s = self.state
        ax = np.minimum(20.0 + s.depth[idx] * 26.0, 50.0)
        ay = CENTER_Y + s.lat[idx] * 24.0
        gk = np.array([s.role[i] == "GK" for i in idx])
        ax = np.where(gk, 4.0, ax)
        ay = np.where(gk, CENTER_Y, ay)
        return from_attacking(ax, ay, SIDES[k])

    def _kickoff(self, team: int, emit: list[Output]) -> None:
        s = self.state
        t = self.t
        for k in range(2):
            idx = np.flatnonzero((s.team == k) & s.active)
            s.x[idx], s.y[idx] = self._kickoff_targets(k, idx)
        s.vx[:] = 0.0
        s.vy[:] = 0.0
        taker = self._kickoff_taker(team)
        s.x[taker], s.y[taker] = CENTER_X, CENTER_Y
        s.bx, s.by, s.bz = CENTER_X, CENTER_Y, 0.0
        s.restart = None
        s.dead_until = t
        self._give_ball(t, taker, emit, "kickoff")
        s.next_decision = t + 0.6

    def _kickoff_taker(self, team: int) -> int:
        s = self.state
        candidates = [i for i in range(len(s.pid)) if s.team[i] == team and s.active[i] and s.role[i] != "GK"]
        return min(candidates, key=lambda i: (-s.depth[i], abs(s.lat[i])))

    def _new_restart(self, t: float, kind: str, team: int, x: float, y: float, out: list[Output]) -> None:
        s = self.state
        x, y = min(max(x, PLAYER_MARGIN), PITCH_LENGTH - PLAYER_MARGIN), min(max(y, PLAYER_MARGIN), PITCH_WIDTH - PLAYER_MARGIN)
        if kind in ("goal_kick", "keeper"):
            taker = self._keeper(team)
        elif kind == "kickoff":
            taker = self._kickoff_taker(team)
            x, y = CENTER_X, CENTER_Y
        else:
            idx = np.flatnonzero((s.team == team) & s.active)
            outfield = [i for i in idx if s.role[i] != "GK"] or list(idx)
            taker = min(outfield, key=lambda i: math.hypot(s.x[i] - x, s.y[i] - y))
        r = s.rng["outcome"]
        dead = {
            "kickoff": (40, 55),
            "throw_in": (6, 13),
            "goal_kick": (10, 18),
            "free_kick": (8, 16),
            "corner": (18, 26),
            "keeper": (4, 8),
        }[kind]
        s.restart = Restart(kind=kind, team=team, x=x, y=y, taker=taker)
        s.dead_until = t + r.uniform(*dead)
        s.owner = -1
        s.flight = None
        s.carry_target = None
        s.carry_start = None
        s.bx, s.by, s.bz = x, y, 0.0
        self._set_possession(t, team, taker, kind, out)

    def _take_restart(self, t: float) -> None:
        s = self.state
        rs = s.restart
        assert rs is not None
        if rs.kind == "kickoff":
            for k in range(2):
                idx = np.flatnonzero((s.team == k) & s.active)
                ax, ay = to_attacking(s.x[idx], s.y[idx], SIDES[k])
                s.x[idx], s.y[idx] = from_attacking(np.minimum(ax, 51.0), ay, SIDES[k])
        s.x[rs.taker], s.y[rs.taker] = rs.x, rs.y
        s.vx[rs.taker] = s.vy[rs.taker] = 0.0
        s.owner = rs.taker
        s.bx, s.by, s.bz = rs.x, rs.y, 0.0
        s.received_t = s.dead_until
        s.aerial = False
        s.pressed = False
        s.corner_cross = rs.kind == "corner"
        s.next_decision = s.dead_until + 0.3
        s.restart = None

    def _keeper(self, team: int) -> int:
        s = self.state
        for i in range(len(s.pid)):
            if s.team[i] == team and s.active[i] and s.role[i] == "GK":
                return i
        idx = [i for i in range(len(s.pid)) if s.team[i] == team and s.active[i]]
        own_x = 0.0 if team == 0 else PITCH_LENGTH
        return min(idx, key=lambda i: abs(s.x[i] - own_x))

    # Scenario, substitutions, discipline

    def _scenario(self, t: float, out: list[Output]) -> None:
        s = self.state
        while s.incidents and s.incidents[0].minute * 60 <= t:
            inc = s.incidents.pop(0)
            k = SIDES.index(inc.team)
            if inc.kind == "tactic":
                s.press_override[k] = inc.press
                s.next_block_eval = t
                continue
            slot = self._slot_by_number(k, inc.player_number)
            if slot is None:
                continue
            if inc.kind == "red_card":
                out.append(self._event(t, EventType.CARD, k, slot, s.x[slot], s.y[slot], outcome="red"))
                self._send_off(t, slot, out)
            else:
                self._substitute(t, k, slot, out)

    def _slot_by_number(self, team: int, number: int | None) -> int | None:
        s = self.state
        for i, pid in enumerate(s.pid):
            if s.team[i] == team and s.active[i] and self.players[pid].number == number:
                return i
        return None

    def _send_off(self, t: float, slot: int, out: list[Output]) -> None:
        s = self.state
        k = int(s.team[slot])
        had_ball = s.owner == slot
        s.active[slot] = False
        s.vx[slot] = s.vy[slot] = 0.0
        if had_ball:
            self._new_restart(t, "free_kick", 1 - k, s.x[slot], s.y[slot], out)
        s.next_block_eval = t

    def _substitutions(self, t: float, out: list[Output]) -> None:
        s = self.state
        for k in range(2):
            while s.sub_times[k] and s.sub_times[k][0] <= t:
                s.sub_times[k].pop(0)
                idx = [
                    i for i in range(len(s.pid))
                    if s.team[i] == k and s.active[i] and s.role[i] != "GK" and i != s.owner
                ]
                if idx:
                    off = max(idx, key=lambda i: s.fatigue[i])
                    self._substitute(t, k, off, out)

    def _substitute(self, t: float, k: int, slot: int, out: list[Output]) -> None:
        s = self.state
        if not s.bench[k]:
            return
        role = s.role[slot]
        bench = s.bench[k]
        same = [p for p in bench if p.position == role]
        outfield = [p for p in bench if p.position != "GK"]
        candidate = (same or outfield or bench)[0]
        bench.remove(candidate)
        off_pid = s.pid[slot]
        if s.owner == slot:
            s.owner = -1
        s.pid[slot] = candidate.player_id
        s.pace[slot] = candidate.traits.pace
        s.passing[slot] = candidate.traits.passing
        s.finishing[slot] = candidate.traits.finishing
        s.stamina[slot] = candidate.traits.stamina
        s.fatigue[slot] = 0.0
        s.yellows[slot] = 0
        s.y[slot] = PLAYER_MARGIN
        s.vx[slot] = s.vy[slot] = 0.0
        out.append(
            self._event(t, EventType.SUBSTITUTION, k, slot, s.x[slot], s.y[slot], meta={"off": off_pid})
        )

    def _block_level(self, k: int, t: float, s: MatchState | None) -> str:
        club = self.clubs[k]
        pref = club.truth.press
        if s is not None:
            if s.press_override[k] is not None:
                pref = s.press_override[k]
            pref += 0.12 * float(s.momentum[k])
            men_down = int(np.sum((s.team == k) & ~s.active))
            pref -= 0.34 * men_down
            lead = s.score[k] - s.score[1 - k]
            if t > 70 * 60 and lead > 0:
                pref -= 0.15
            if t > 60 * 60 and lead < 0:
                pref += 0.12
        if pref >= 0.62:
            return "high"
        if pref <= 0.25:  # mostly reached by game state: down to ten, or protecting a late lead
            return "low"
        return "mid"

    def _evaluate_blocks(self, t: float) -> None:
        s = self.state
        if t >= s.next_block_eval:
            s.block = [self._block_level(k, t, s) for k in range(2)]
            s.next_block_eval = t + 60.0

    def _update_momentum(self) -> None:
        """Hidden rhythm: a slow random walk per team, nudged by goals. Updated once per match second."""
        s = self.state
        step = round(1.0 / self.config.dt)
        if s.tick % step:
            return
        noise = s.rng["move"].normal(0.0, 0.03, size=2)
        for k in range(2):
            s.momentum[k] = min(max(s.momentum[k] * (1.0 - 0.012) + noise[k], -1.0), 1.0)

    # Movement

    def _update_runs(self, t: float) -> None:
        s = self.state
        r = s.rng["move"]
        dt = self.config.dt
        n = len(s.pid)
        start = (s.run_until <= t) & s.active & (r.random(n) < dt / 4.0)
        for i in np.flatnonzero(start):
            attacking = s.possession == s.team[i] and s.role[i] in ("MF", "FW")
            attack = self.clubs[s.team[i]].truth.attack
            if attacking and r.random() < 0.2 + 0.5 * attack:
                s.run_dx[i] = r.uniform(3.0, 6.0 + 10.0 * attack)
                s.run_dy[i] = r.uniform(-7.0, 7.0)
                s.run_until[i] = t + r.uniform(2.0, 4.5)
                s.run_sprint[i] = True
            else:
                s.run_dx[i] = r.uniform(-5.0, 5.0)
                s.run_dy[i] = r.uniform(-6.0, 6.0)
                s.run_until[i] = t + r.uniform(2.0, 5.0)
                s.run_sprint[i] = False

    def _targets(self, t: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Where every player wants to be this tick, and how fast they may go. Vectorized over all 22."""
        s = self.state
        dead = t < s.dead_until
        rs = s.restart
        home = self._home_mask

        if rs is not None and rs.kind == "kickoff":
            tx, ty = s.x.copy(), s.y.copy()
            for k in range(2):
                idx = np.flatnonzero((s.team == k) & s.active)
                tx[idx], ty[idx] = self._kickoff_targets(k, idx)
            sprinting = np.zeros(len(s.pid), dtype=bool)
        else:
            # Per team block parameters, then broadcast to players by team index.
            lines, lengths, widths, shifts = [], [], [], []
            for k in range(2):
                bxa = s.bx if k == 0 else PITCH_LENGTH - s.bx
                bya = s.by if k == 0 else PITCH_WIDTH - s.by
                if s.possession == k:
                    line = min(max(bxa - 30.0, 16.0), 50.0)
                    length, width, shift = 36.0, 58.0, 0.25
                else:
                    base, length, width, top = BLOCKS[s.block[k]]
                    width -= DEFENCE_WIDTH_W * (self.clubs[k].truth.defence - 0.5)
                    line = min(max(base + 0.25 * (bxa - CENTER_X), 10.0), top)
                    # Stay goal-side of the ball and squeeze the block as it nears goal.
                    line = min(line, max(bxa - 7.0, 5.0))
                    length = min(length, max(bxa - line + 6.0, 10.0))
                    shift = 0.4
                lines.append(line)
                lengths.append(length)
                widths.append(width)
                shifts.append(min(max(shift * (bya - CENTER_Y), -11.0), 11.0))
            team = s.team
            line = np.array(lines)[team]
            length = np.array(lengths)[team]
            width = np.array(widths)[team]
            shift = np.array(shifts)[team]
            bxa = np.where(home, s.bx, PITCH_LENGTH - s.bx)
            bya = np.where(home, s.by, PITCH_WIDTH - s.by)

            running = s.run_until > t
            ax = line + s.depth * length + np.where(running, s.run_dx, 0.0)
            ay = CENTER_Y + s.lat * width / 2 + shift + np.where(running, s.run_dy, 0.0)
            gk = self._gk_mask
            if s.possession >= 0:
                attackers = (team == s.possession) & ~gk
                ax = np.where(attackers, np.minimum(ax, self._offside_line(s.possession) - 0.5), ax)
            ax = np.where(gk, 3.5 + 0.06 * bxa, ax)
            ay = np.where(gk, CENTER_Y + np.clip(0.15 * (bya - CENTER_Y), -5.0, 5.0), ay)
            if rs is not None and rs.kind == "corner":
                for k in range(2):
                    idx = np.flatnonzero((s.team == k) & s.active)
                    ax[idx], ay[idx] = self._corner_shape(k, rs, idx, ax[idx], ay[idx])
            np.clip(ax, PLAYER_MARGIN, PITCH_LENGTH - PLAYER_MARGIN, out=ax)
            np.clip(ay, PLAYER_MARGIN, PITCH_WIDTH - PLAYER_MARGIN, out=ay)
            tx = np.where(home, ax, PITCH_LENGTH - ax)
            ty = np.where(home, ay, PITCH_WIDTH - ay)
            if s.possession >= 0 and rs is None:
                self._mark(tx, ty)
            sprinting = running & s.run_sprint

        if rs is not None:
            tx[rs.taker], ty[rs.taker] = rs.x, rs.y
        if not dead:
            self._chasers(tx, ty, sprinting)

        sprint_cap = (6.6 + 2.8 * s.pace) * (1.0 - 0.18 * s.fatigue)
        dist = np.hypot(tx - s.x, ty - s.y)
        cap = np.minimum(JOG_MS + 2.8 * np.minimum(dist / 18.0, 1.0), sprint_cap)
        cap = np.where(sprinting, sprint_cap, cap)
        if s.owner >= 0 and not dead:
            o = s.owner
            if s.carry_target is not None:
                tx[o], ty[o] = s.carry_target
                cap[o] = DRIBBLE_MS * (0.7 + 0.3 * s.pace[o]) * (1.0 - 0.15 * s.fatigue[o])
            else:
                tx[o], ty[o] = s.x[o], s.y[o]
        return tx, ty, cap

    def _corner_shape(self, k: int, rs: Restart, idx: np.ndarray, ax: np.ndarray, ay: np.ndarray):
        s = self.state
        r = s.rng["move"]
        attacking = rs.team == k
        roles = [s.role[i] for i in idx]
        ax, ay = ax.copy(), ay.copy()
        for j, i in enumerate(idx):
            if i == rs.taker or roles[j] == "GK":
                continue
            if attacking:
                if roles[j] == "DF" and j % 2 == 0:
                    continue  # two defenders stay back
                ax[j] = 93.0 + r.uniform(0, 6)
                ay[j] = CENTER_Y + r.uniform(-9, 9)
            else:
                ax[j] = 2.0 + r.uniform(0, 10)
                ay[j] = CENTER_Y + r.uniform(-10, 10)
        return ax, ay

    def _chasers(self, tx: np.ndarray, ty: np.ndarray, sprinting: np.ndarray) -> None:
        s = self.state
        if s.flight is not None:
            f = s.flight
            if f.kind == "pass" and f.receiver >= 0:
                tx[f.receiver], ty[f.receiver] = f.ex, f.ey
                sprinting[f.receiver] = True
            if f.other >= 0 and f.result == "intercept":
                tx[f.other], ty[f.other] = f.ex, f.ey
                sprinting[f.other] = True
            if f.result == "loose" or f.kind == "loose":
                for k in range(2):
                    c = self._nearest(k, f.ex, f.ey, outfield=True)
                    if c is not None:
                        tx[c], ty[c] = f.ex, f.ey
                        sprinting[c] = True
            return
        if s.owner < 0:
            for k in range(2):
                c = self._nearest(k, s.bx, s.by, outfield=False)
                if c is not None:
                    tx[c], ty[c] = s.bx, s.by
                    sprinting[c] = True
            return
        defending = 1 - int(s.team[s.owner])
        level = s.block[defending]
        n = PRESSERS[level]
        if level == "low":
            bxa, _ = to_attacking(s.bx, s.by, SIDES[defending])
            n = 1 if bxa < 38.0 else 0
        idx = [i for i in range(len(s.pid)) if s.team[i] == defending and s.active[i] and s.role[i] != "GK"]
        idx.sort(key=lambda i: math.hypot(s.x[i] - s.bx, s.y[i] - s.by))
        for i in idx[:n]:
            tx[i], ty[i] = s.bx, s.by
            sprinting[i] = True

    def _mark(self, tx: np.ndarray, ty: np.ndarray) -> None:
        """Pull each defending outfield player's target toward the nearest attacker."""
        s = self.state
        k = 1 - s.possession
        defenders = np.flatnonzero((s.team == k) & s.active & ~self._gk_mask)
        attackers = np.flatnonzero((s.team != k) & s.active & ~self._gk_mask)
        if len(defenders) == 0 or len(attackers) == 0:
            return
        dx = s.x[attackers][None, :] - tx[defenders][:, None]
        dy = s.y[attackers][None, :] - ty[defenders][:, None]
        nearest = np.argmin(dx * dx + dy * dy, axis=1)
        pull = MARKING_BASE + MARKING_W * self.clubs[k].truth.defence
        rows = np.arange(len(defenders))
        tx[defenders] += pull * dx[rows, nearest]
        ty[defenders] += pull * dy[rows, nearest]

    def _offside_line(self, k: int) -> float:
        """Furthest a team k attacker may stand, in k's attacking frame: the last outfield defender or the ball."""
        s = self.state
        opp = (s.team != k) & s.active & ~self._gk_mask
        if not np.any(opp):
            return PITCH_LENGTH
        deepest = float(np.max(s.x[opp] if k == 0 else PITCH_LENGTH - s.x[opp]))
        ball = s.bx if k == 0 else PITCH_LENGTH - s.bx
        return max(deepest, ball, CENTER_X)

    def _nearest(self, k: int, x: float, y: float, outfield: bool) -> int | None:
        s = self.state
        idx = [i for i in range(len(s.pid)) if s.team[i] == k and s.active[i] and (not outfield or s.role[i] != "GK")]
        if not idx:
            return None
        return min(idx, key=lambda i: math.hypot(s.x[i] - x, s.y[i] - y))

    def _move_players(self, t: float) -> None:
        s = self.state
        dt = self.config.dt
        tx, ty, cap = self._targets(t)
        dx, dy = tx - s.x, ty - s.y
        dist = np.hypot(dx, dy)
        desired = np.minimum(cap, dist / 0.7)
        with np.errstate(invalid="ignore", divide="ignore"):
            ux = np.where(dist > 1e-6, dx / dist, 0.0)
            uy = np.where(dist > 1e-6, dy / dist, 0.0)
        dvx, dvy = ux * desired - s.vx, uy * desired - s.vy
        dv = np.hypot(dvx, dvy)
        scale = np.minimum(1.0, ACCEL * dt / np.maximum(dv, 1e-9)) * s.active
        s.vx = (s.vx + dvx * scale) * s.active
        s.vy = (s.vy + dvy * scale) * s.active
        speed = np.hypot(s.vx, s.vy)
        s.x = np.clip(s.x + s.vx * dt, PLAYER_MARGIN, PITCH_LENGTH - PLAYER_MARGIN)
        s.y = np.clip(s.y + s.vy * dt, PLAYER_MARGIN, PITCH_WIDTH - PLAYER_MARGIN)
        s.fatigue += dt * (0.00005 + 0.000018 * speed**2) / (0.45 + s.stamina)

    # Ball

    def _move_ball(self, t: float, out: list[Output]) -> None:
        s = self.state
        f = s.flight
        if f is not None:
            span = max(f.t1 - f.t0, 1e-6)
            u = min(max((t - f.t0) / span, 0.0), 1.0)
            s.bx = f.sx + (f.ex - f.sx) * u
            s.by = f.sy + (f.ey - f.sy) * u
            s.bz = 4.0 * f.peak * u * (1.0 - u)
            if u >= 1.0:
                self._land(t, f, out)
        elif s.owner >= 0 and t >= s.dead_until:
            o = s.owner
            speed = math.hypot(s.vx[o], s.vy[o])
            if speed > 0.5:
                s.bx = s.x[o] + 0.5 * s.vx[o] / speed
                s.by = s.y[o] + 0.5 * s.vy[o] / speed
            else:
                s.bx, s.by = float(s.x[o]), float(s.y[o])
            s.bz = 0.0
            if s.carry_target is not None and math.hypot(s.x[o] - s.carry_target[0], s.y[o] - s.carry_target[1]) < 1.0:
                s.carry_target = None

    def _land(self, t: float, f: Flight, out: list[Output]) -> None:
        s = self.state
        r = s.rng["outcome"]
        s.flight = None
        s.bz = 0.0
        attack, defend = f.team, 1 - f.team
        if f.kind == "pass":
            if f.result == "complete" and s.active[f.receiver]:
                self._give_ball(t, f.receiver, out, "pass", aerial=f.peak > 2.0)
            elif f.result == "intercept" and f.other >= 0 and s.active[f.other]:
                out.append(
                    self._event(t, EventType.INTERCEPTION, defend, f.other, f.ex, f.ey, outcome="won",
                                meta={"passer": s.pid[f.passer]})
                )
                self._give_ball(t, f.other, out, "interception")
            elif f.result == "out":
                self._out_of_play(t, f.ex, f.ey, last_touch=attack, out=out)
            else:
                s.owner = -1
                s.bx, s.by = f.ex, f.ey
        elif f.kind == "shot":
            if f.result == "goal":
                s.score[attack] += 1
                out.append(self._event(t, EventType.GOAL, attack, f.passer, f.sx, f.sy))
                s.momentum[attack] = min(1.0, s.momentum[attack] + 0.3)
                s.momentum[defend] = max(-1.0, s.momentum[defend] - 0.2)
                s.next_block_eval = t
                self._new_restart(t, "kickoff", defend, CENTER_X, CENTER_Y, out)
            elif f.result == "saved":
                if r.random() < 0.7:
                    self._new_restart(t, "keeper", defend, *self._keeper_spot(defend), out)
                else:
                    self._corner(t, attack, f.ey, out)
            elif f.result == "off_target":
                gx, gy = from_attacking(5.5, CENTER_Y, SIDES[defend])
                self._new_restart(t, "goal_kick", defend, gx, gy, out)
            else:  # blocked: the ball runs loose
                ang = r.uniform(0, 2 * math.pi)
                d = r.uniform(3.0, 7.0)
                ex = min(max(f.ex + d * math.cos(ang), 1.0), PITCH_LENGTH - 1.0)
                ey = min(max(f.ey + d * math.sin(ang), 1.0), PITCH_WIDTH - 1.0)
                s.flight = Flight("loose", f.ex, f.ey, ex, ey, t, t + d / 9.0, 0.3, attack, -1, -1, "loose")
        else:
            s.owner = -1
            s.bx, s.by = f.ex, f.ey

    def _keeper_spot(self, team: int) -> tuple[float, float]:
        return from_attacking(8.0, CENTER_Y, SIDES[team])

    def _corner(self, t: float, attack: int, y_hint: float, out: list[Output]) -> None:
        side = SIDES[attack]
        _, ya = to_attacking(0.0, y_hint, side)
        cy = PLAYER_MARGIN if ya < CENTER_Y else PITCH_WIDTH - PLAYER_MARGIN
        cx, cy = from_attacking(PITCH_LENGTH - PLAYER_MARGIN, cy, side)
        self._new_restart(t, "corner", attack, cx, cy, out)

    def _out_of_play(self, t: float, x: float, y: float, last_touch: int, out: list[Output]) -> None:
        other = 1 - last_touch
        if 0.0 < x < PITCH_LENGTH:
            self._new_restart(t, "throw_in", other, x, y, out)
            return
        xa, _ = to_attacking(x, y, SIDES[last_touch])
        if xa >= PITCH_LENGTH:
            gx, gy = from_attacking(5.5, CENTER_Y, SIDES[other])
            self._new_restart(t, "goal_kick", other, gx, gy, out)
        else:
            self._corner(t, other, y, out)

    def _loose_pickup(self, t: float, out: list[Output]) -> None:
        s = self.state
        d = np.hypot(s.x - s.bx, s.y - s.by)
        d[~s.active] = np.inf
        i = int(np.argmin(d))
        if d[i] <= 1.0:
            self._give_ball(t, i, out, "loose_ball")

    # On the ball

    def _pressure(self, slot: int) -> float:
        s = self.state
        opp = (s.team != s.team[slot]) & s.active
        if not np.any(opp):
            return 0.0
        d = float(np.min(np.hypot(s.x[opp] - s.x[slot], s.y[opp] - s.y[slot])))
        return min(max(1.0 - (d - 0.5) / 4.0, 0.0), 1.0)

    def _pressure_event(self, t: float, out: list[Output]) -> None:
        s = self.state
        if s.pressed:
            return
        o = s.owner
        opp = np.flatnonzero((s.team != s.team[o]) & s.active)
        d = np.hypot(s.x[opp] - s.x[o], s.y[opp] - s.y[o])
        j = int(np.argmin(d))
        if d[j] <= PRESSURE_EVENT_M:
            s.pressed = True
            out.append(
                self._event(t, EventType.PRESSURE, int(s.team[opp[j]]), int(opp[j]), s.x[o], s.y[o],
                            pressure=round(self._pressure(o), 3), meta={"carrier": s.pid[o]})
            )

    def _tackle(self, t: float, out: list[Output]) -> bool:
        s = self.state
        o = s.owner
        k = int(s.team[o])
        opp = np.flatnonzero((s.team != k) & s.active & (s.cooldown <= t))
        if len(opp) == 0:
            return False
        d = np.hypot(s.x[opp] - s.x[o], s.y[opp] - s.y[o])
        j = int(np.argmin(d))
        if d[j] > TACKLE_REACH or s.role[opp[j]] == "GK":
            return False
        defender = int(opp[j])
        defending = 1 - k
        rate = TACKLE_RATE * (0.85 + 0.3 * self.clubs[defending].truth.press)
        own_goal_dist, _ = to_attacking(float(s.x[o]), float(s.y[o]), SIDES[defending])
        if own_goal_dist < 20.0:
            rate *= BOX_TACKLE_BOOST
        r = s.rng["outcome"]
        if r.random() >= 1.0 - math.exp(-rate * self.config.dt):
            return False
        if r.random() < FOUL_P:
            self._foul(t, defender, o, out)
            return True
        def_quality = (s.pace[defender] + DUEL_QUALITY_W * self.clubs[defending].truth.defence) / (1 + DUEL_QUALITY_W)
        att_quality = (s.pace[o] + s.passing[o] + DUEL_QUALITY_W * self.clubs[k].truth.attack) / (2 + DUEL_QUALITY_W)
        p_won = metrics.sigmoid(0.2 + 2.0 * (def_quality - att_quality) - 0.3 * float(s.momentum[k]))
        if r.random() < p_won:
            out.append(
                self._event(t, EventType.TACKLE, defending, defender, s.x[o], s.y[o], outcome="won",
                            meta={"carrier": s.pid[o]})
            )
            s.carry_target = None
            if r.random() < 0.7:
                self._give_ball(t, defender, out, "tackle")
            else:
                ang = r.uniform(0, 2 * math.pi)
                dist = r.uniform(2.0, 4.0)
                ex = min(max(s.bx + dist * math.cos(ang), 1.0), PITCH_LENGTH - 1.0)
                ey = min(max(s.by + dist * math.sin(ang), 1.0), PITCH_WIDTH - 1.0)
                s.owner = -1
                s.flight = Flight("loose", s.bx, s.by, ex, ey, t, t + dist / 6.0, 0.2, defending, -1, -1, "loose")
        else:
            out.append(
                self._event(t, EventType.TACKLE, defending, defender, s.x[o], s.y[o], outcome="lost",
                            meta={"carrier": s.pid[o]})
            )
            s.cooldown[defender] = t + 1.5
        return True

    def _foul(self, t: float, defender: int, victim: int, out: list[Output]) -> None:
        s = self.state
        r = s.rng["discipline"]
        k = int(s.team[defender])
        out.append(self._event(t, EventType.FOUL, k, defender, s.x[victim], s.y[victim], meta={"fouled": s.pid[victim]}))
        roll = r.random()
        if roll < STRAIGHT_RED_P:
            out.append(self._event(t, EventType.CARD, k, defender, s.x[defender], s.y[defender], outcome="red"))
            self._send_off(t, defender, out)
        elif roll < YELLOW_P:
            s.yellows[defender] += 1
            if s.yellows[defender] >= 2:
                out.append(self._event(t, EventType.CARD, k, defender, s.x[defender], s.y[defender], outcome="red",
                                       meta={"second_yellow": True}))
                self._send_off(t, defender, out)
            else:
                out.append(self._event(t, EventType.CARD, k, defender, s.x[defender], s.y[defender], outcome="yellow"))
        self._new_restart(t, "free_kick", 1 - k, s.x[victim], s.y[victim], out)

    def _decide(self, t: float, out: list[Output]) -> None:
        s = self.state
        c = s.owner
        k = int(s.team[c])
        side = SIDES[k]
        club = self.clubs[k]
        r = s.rng["decide"]
        xa, ya = to_attacking(float(s.x[c]), float(s.y[c]), side)
        pressure = self._pressure(c)

        if s.carry_start is not None:
            carrier, sx, sy = s.carry_start
            if carrier == c:
                out.append(self._event(t, EventType.CARRY, k, c, sx, sy, end=(float(s.x[c]), float(s.y[c])),
                                       outcome="complete", pressure=round(pressure, 3)))
            s.carry_start = None
            s.carry_target = None

        if s.corner_cross:
            s.corner_cross = False
            self._pass(t, c, self._cross_target(c), pressure, out, cross=True)
            return

        header = s.aerial and (t - s.received_t) <= HEADER_WINDOW_S
        if xa > 70.0 and s.role[c] != "GK":
            xg_here = TRUE_XG.prob(xa, ya, header, pressure)
            p_shoot = metrics.sigmoid((xg_here - SHOT_XG_PIVOT) * SHOT_XG_SLOPE + 0.4 * float(s.momentum[k]))
            if header:
                p_shoot = max(p_shoot, 0.5)
            distance = math.hypot(PITCH_LENGTH - xa, CENTER_Y - ya)
            if 16.0 <= distance <= 28.0 and pressure < 0.6:
                p_shoot += LONG_SHOT_P * (0.5 + club.truth.attack)
            if r.random() < p_shoot:
                self._shoot(t, c, xa, ya, header, pressure, out)
                return

        mates = np.array([i for i in range(len(s.pid)) if s.team[i] == k and s.active[i] and i != c])
        opp = np.flatnonzero((s.team != k) & s.active)
        rx, ry = to_attacking(s.x[mates], s.y[mates], side)
        ox, oy = to_attacking(s.x[opp], s.y[opp], side)
        dist = np.hypot(rx - xa, ry - ya)
        marking = np.min(np.hypot(rx[:, None] - ox[None, :], ry[:, None] - oy[None, :]), axis=1)
        opponent = self.clubs[1 - k].truth
        logit = (
            metrics.pass_logit_array(xa, ya, rx, ry, pressure)
            + 1.3 * (s.passing[c] - 0.5)
            + ATTACK_PASS_W * (club.truth.attack - 0.5)
            - DEFENCE_PASS_W * (opponent.defence - 0.5)
            - 0.5 * s.fatigue[c]
            + 0.25 * float(s.momentum[k])
            - 1.2 * np.maximum(0.0, 1.0 - marking / 4.0)
        )
        p = 1.0 / (1.0 + np.exp(-logit))
        threat_here = TRUE_XG.prob(xa, ya) + 0.03 * (xa / PITCH_LENGTH) ** 2
        threat = 1.0 / (1.0 + np.exp(-TRUE_XG.logit_array(rx, ry))) + 0.03 * (rx / PITCH_LENGTH) ** 2
        gain = threat - threat_here
        forward = (rx - xa) / np.maximum(dist, 1e-6)
        ambition = 0.7 + 0.15 * club.truth.tempo + 0.4 * club.truth.attack
        utility = p * (0.25 + PROGRESS_W * ambition * gain + 0.02 * forward) - (1.0 - p) * (
            0.3 + 0.5 * (1.0 - xa / PITCH_LENGTH)
        )
        is_gk = np.array([s.role[i] == "GK" for i in mates])
        utility = np.where(is_gk & (pressure < 0.5), utility - 0.25, utility)
        offside = rx > self._offside_line(k) + 0.5
        utility = np.where((dist < 4.0) | (dist > 50.0) | offside, -10.0, utility)

        ahead = (ox > xa) & (np.abs(oy - ya) < (ox - xa) + 2.0)
        space = float(np.min(np.hypot(ox[ahead] - xa, oy[ahead] - ya))) if np.any(ahead) else 25.0
        u_carry = 0.04 + 0.16 * min(max((space - 3.0) / 8.0, 0.0), 1.0) * (1.0 if xa < 80.0 else 0.3)
        if s.role[c] == "GK":
            u_carry = -10.0
        u_hold = 0.06

        options = np.concatenate([utility, [u_carry, u_hold]])
        w = np.exp((options - options.max()) / SOFTMAX_T)
        choice = int(r.choice(len(options), p=w / w.sum()))
        if choice < len(mates):
            self._pass(t, c, int(mates[choice]), pressure, out, p_complete=float(p[choice]))
        elif choice == len(mates):
            reach = r.uniform(3.0, 6.0) if xa > 75.0 else r.uniform(6.0, 12.0)
            fx = min(xa + reach, 92.0)
            fy = min(max(ya + r.uniform(-4.0, 4.0), 2.0), PITCH_WIDTH - 2.0)
            s.carry_target = from_attacking(fx, fy, side)
            s.carry_start = (c, float(s.x[c]), float(s.y[c]))
            s.next_decision = t + r.uniform(*CARRY_S)
        else:
            s.next_decision = t + r.uniform(*HOLD_S)

    def _cross_target(self, c: int) -> int:
        s = self.state
        k = int(s.team[c])
        side = SIDES[k]
        mates = [i for i in range(len(s.pid)) if s.team[i] == k and s.active[i] and i != c and s.role[i] != "GK"]

        def in_box_score(i: int) -> float:
            xa, ya = to_attacking(s.x[i], s.y[i], side)
            return -abs(xa - 98.0) - 0.5 * abs(ya - CENTER_Y)

        return max(mates, key=in_box_score)

    def _pass(self, t: float, c: int, target: int, pressure: float, out: list[Output],
              p_complete: float | None = None, cross: bool = False) -> None:
        s = self.state
        r = s.rng["outcome"]
        k = int(s.team[c])
        side = SIDES[k]
        sx, sy = float(s.bx), float(s.by)
        ex = float(min(max(s.x[target] + 0.4 * s.vx[target], 1.0), PITCH_LENGTH - 1.0))
        ey = float(min(max(s.y[target] + 0.4 * s.vy[target], 1.0), PITCH_WIDTH - 1.0))
        d = math.hypot(ex - sx, ey - sy)
        if p_complete is None:
            xa, ya = to_attacking(sx, sy, side)
            exa, eya = to_attacking(ex, ey, side)
            p_complete = metrics.pass_completion(xa, ya, exa, eya, pressure)
            if cross:
                p_complete = metrics.sigmoid(0.1 + 1.0 * (s.passing[c] - 0.5))
        lofted = d > 28.0 or cross
        peak = 0.09 * d + (1.5 if cross else 0.0) if lofted else 0.0
        speed = r.uniform(18.0, 22.0) if lofted else min(max(7.0 + 0.5 * d, 9.0), 27.0)

        result = "complete"
        other = -1
        if r.random() >= p_complete:
            opp = np.flatnonzero((s.team != k) & s.active)
            vx, vy = ex - sx, ey - sy
            seg = max(vx * vx + vy * vy, 1e-9)
            u = np.clip(((s.x[opp] - sx) * vx + (s.y[opp] - sy) * vy) / seg, 0.05, 1.0)
            px, py = sx + u * vx, sy + u * vy
            lane = np.hypot(s.x[opp] - px, s.y[opp] - py)
            j = int(np.argmin(lane))
            roll = r.random()
            if lane[j] < 3.5 and roll < INTERCEPT_SHARE * (0.6 + 0.8 * self.clubs[1 - k].truth.defence):
                result = "intercept"
                other = int(opp[j])
                ex, ey = float(px[j]), float(py[j])
            elif roll < 0.85:
                result = "out"
                ex, ey = self._push_out(ex, ey, sx, sy)
            else:
                result = "loose"
                ang = r.uniform(0, 2 * math.pi)
                off = r.uniform(3.0, 8.0)
                ex = min(max(ex + off * math.cos(ang), 1.0), PITCH_LENGTH - 1.0)
                ey = min(max(ey + off * math.sin(ang), 1.0), PITCH_WIDTH - 1.0)

        flight_d = math.hypot(ex - sx, ey - sy)
        s.flight = Flight("pass", sx, sy, ex, ey, t, t + max(flight_d / speed, 0.2), peak, k, c,
                          target if result == "complete" else -1, result, other)
        s.owner = -1
        s.carry_target = None
        key = "receiver" if result == "complete" else "intended"
        out.append(
            self._event(t, EventType.PASS, k, c, sx, sy, end=(ex, ey),
                        outcome="complete" if result == "complete" else "incomplete",
                        pressure=round(pressure, 3), meta={key: s.pid[target], **({"cross": True} if cross else {})})
        )

    def _push_out(self, ex: float, ey: float, sx: float, sy: float) -> tuple[float, float]:
        """Carry a misplaced pass over the nearest boundary line."""
        gaps = {
            "left": ey,
            "right": PITCH_WIDTH - ey,
            "back": ex,
            "front": PITCH_LENGTH - ex,
        }
        side = min(gaps, key=gaps.get)
        if side == "left":
            return ex, -1.0
        if side == "right":
            return ex, PITCH_WIDTH + 1.0
        if side == "back":
            return -1.0, ey
        return PITCH_LENGTH + 1.0, ey

    def _shoot(self, t: float, c: int, xa: float, ya: float, header: bool, pressure: float, out: list[Output]) -> None:
        s = self.state
        r = s.rng["outcome"]
        k = int(s.team[c])
        side = SIDES[k]
        defending = 1 - k
        logit_true = (
            TRUE_XG.logit(xa, ya, header, pressure)
            + FINISHING_OFFSET
            + 1.0 * (s.finishing[c] - 0.5)
            + FINISH_QUALITY_W * (self.clubs[k].truth.attack - self.clubs[defending].truth.defence)
            + 0.3 * float(s.momentum[k])
        )
        roll = r.random()
        meta: dict[str, Any] = {}
        if roll < metrics.sigmoid(logit_true):
            result = "goal"
            gy = r.uniform(GOAL_Y_LOW + 0.3, GOAL_Y_HIGH - 0.3)
            gx = PITCH_LENGTH
        elif pressure > 0.3 and r.random() < 0.15 + 0.3 * self.clubs[defending].truth.defence:
            result = "blocked"
            blocker = self._nearest(defending, s.x[c], s.y[c], outfield=True)
            meta["blocker"] = s.pid[blocker] if blocker is not None else ""
            frac = r.uniform(1.5, 4.0)
            dx, dy = PITCH_LENGTH - xa, CENTER_Y - ya
            n = math.hypot(dx, dy)
            gx, gy = xa + dx / n * frac, ya + dy / n * frac
        elif r.random() < 0.52:
            result = "saved"
            meta["keeper"] = s.pid[self._keeper(defending)]
            gy = r.uniform(GOAL_Y_LOW + 0.2, GOAL_Y_HIGH - 0.2)
            gx = PITCH_LENGTH
        else:
            result = "off_target"
            miss = r.uniform(0.5, 6.0) * (1 if r.random() < 0.5 else -1)
            gy = (GOAL_Y_HIGH if miss > 0 else GOAL_Y_LOW) + miss
            gx = PITCH_LENGTH + 1.0
        ex, ey = from_attacking(gx, gy, side)
        sx, sy = float(s.bx), float(s.by)
        if header:
            speed = r.uniform(9.0, 15.0)
        else:
            speed = 16.0 + 12.0 * r.beta(2, 2) + 6.0 * s.finishing[c]
        d = math.hypot(ex - sx, ey - sy)
        peak = r.uniform(0.0, GOAL_HEIGHT / 2) if result in ("goal", "saved") else r.uniform(0.0, 3.0)
        s.flight = Flight("shot", sx, sy, ex, ey, t, t + max(d / speed, 0.15), peak, k, c, -1, result)
        s.owner = -1
        # A freeze frame of the outfield defenders at the moment of the shot, like StatsBomb 360 data.
        defenders = np.flatnonzero((s.team == defending) & s.active & ~self._gk_mask)
        meta["defenders"] = [[round(float(s.x[i]), 1), round(float(s.y[i]), 1)] for i in defenders]
        out.append(
            self._event(t, EventType.SHOT, k, c, sx, sy, end=(ex, ey), outcome=result, pressure=round(pressure, 3),
                        body_part="head" if header else "foot", meta=meta)
        )

    # Output

    def _frame(self, t: float) -> TrackingFrame:
        s = self.state
        speed = np.minimum(np.hypot(s.vx, s.vy), MAX_PLAYER_SPEED_MS)
        players = [
            PlayerPos(id=s.pid[i], team=SIDES[s.team[i]], x=round(float(s.x[i]), 2), y=round(float(s.y[i]), 2),
                      speed_ms=round(float(speed[i]), 2))
            for i in range(len(s.pid))
            if s.active[i]
        ]
        ball = BallPos(
            x=round(min(max(s.bx, -BALL_MARGIN), PITCH_LENGTH + BALL_MARGIN), 2),
            y=round(min(max(s.by, -BALL_MARGIN), PITCH_WIDTH + BALL_MARGIN), 2),
            z=round(max(s.bz, 0.0), 2),
        )
        return TrackingFrame(t=t, ball=ball, players=players)


def simulate(
    meta: MatchMeta,
    league: League,
    config: SimConfig = SimConfig(),
    scenario: Scenario | None = None,
) -> Iterator[Output]:
    yield from MatchSimulator(meta, league, config, scenario).run()
