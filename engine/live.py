"""Live stats engine: turns the event and frame stream into match state, metrics and key moments.

Everything here is deterministic. Push events and frames in time order; read stats() at any
time; push() returns the key moments that the agents will later narrate.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from engine import metrics
from engine.league import League
from engine.leverage import Leverage, LeverageModel
from engine.models import EventType, MatchEvent, MatchMeta, Moment, MomentKind, Side, StatsUpdate, TrackingFrame
from engine.pitch import goal_geometry, to_attacking
from engine.press import PossessionTimeline, PressResistance, PressRow
from engine.shape import ShapeChange, ShapeTracker
from engine.winprob import GameState, Ratings, result_probs
from engine.xt import XTGrid

SIDES: tuple[Side, Side] = ("home", "away")

WINDOW_S = 300.0
ASSIST_WINDOW_S = 10.0
FAILED_PASS_WINDOW_S = 6.0
MOMENTUM_ALPHA = 0.1
MOMENTUM_SCALE = 150.0
CHAOS_BASELINE_PER_MIN = 2.5

LEVERAGE_MOMENT = 0.6
BIG_CHANCE_XG = 0.3
LOW_XG_GOAL = 0.1
TOP_SPEED_MOMENT_MS = 9.0
DEBOUNCE_S = 20.0
CONTROL_EVAL_S = 120.0
CONTROL_MARGIN = 0.2
CHAOS_HIGH = 1.4


@dataclass
class ShotRecord:
    event_id: str
    team: Side
    player_id: str
    minute: int
    t: float
    x: float
    y: float
    xg: float
    outcome: str
    body_part: str
    leverage: float
    shot_type: str = "Shot"
    distance_m: float = 0.0
    angle_deg: float = 0.0
    pressure: float = 0.0
    defender_m: float | None = None  # nearest outfield defender at the moment of the shot, from tracking
    creator: str | None = None
    score_before: str = "0-0"
    wp_if_goal: float = 0.0  # shooting team's win probability if it goes in
    wp_if_miss: float = 0.0  # and if it does not
    speed_ms: float | None = None


def shot_type(header: bool, distance: float, first_time: bool, cross: bool, assisted: bool = False) -> str:
    if header:
        return "Header from a cross" if cross else "Header"
    if distance < 8.0:
        return "Close-range finish"
    if distance >= 20.0:
        return "Long shot"
    if first_time:
        return "First-time shot"
    return "Shot after a pass" if assisted else "Shot after a dribble"


@dataclass
class LeverageRow:
    player_id: str
    team: Side
    shot_making: float = 0.0
    creation: float = 0.0
    defending: float = 0.0
    turnovers: float = 0.0

    @property
    def total(self) -> float:
        return self.shot_making + self.creation + self.defending + self.turnovers


@dataclass
class _Window:
    events: deque = field(default_factory=deque)  # (t, side, kind)

    def add(self, t: float, side: Side, kind: str) -> None:
        self.events.append((t, side, kind))

    def trim(self, now: float) -> None:
        while self.events and self.events[0][0] < now - WINDOW_S:
            self.events.popleft()


class LiveStats:
    def __init__(
        self,
        meta: MatchMeta,
        league: League,
        ratings: Ratings | None = None,
        xt: XTGrid | None = None,
    ) -> None:
        self.meta = meta
        self.ratings = ratings or Ratings.load()
        self.xt = xt or XTGrid.load()
        self.prior = self.ratings.prior(meta.home, meta.away)
        self.model = LeverageModel(self.prior, self.xt)
        keepers = {p.player_id for c in (meta.home, meta.away) for p in league.squads[c] if p.position == "GK"}
        self._keepers = keepers
        self._last_frame: TrackingFrame | None = None

        self.t = 0.0
        self.score = [0, 0]
        self.xg = [0.0, 0.0]
        self.xt_added = [0.0, 0.0]
        self.men = [11, 11]
        self.passes = [0, 0]
        self.completed = [0, 0]
        self.momentum_raw = 0.0
        self.timeline = PossessionTimeline()
        self.window = _Window()
        self.press = PressResistance()
        self.shape = ShapeTracker(keepers)
        self.kinematics = metrics.Kinematics()

        self.shots: list[ShotRecord] = []
        self.leverage_rows: dict[str, LeverageRow] = {}
        self.leverage_log: dict[str, Leverage] = {}
        self.moments: list[Moment] = []

        self._last_complete: dict[Side, tuple[str, str, float, bool]] = {}  # passer, receiver, t, cross
        self._last_failed: tuple[str, Side, float, float] | None = None
        self._pending_goal: tuple[ShotRecord, Leverage] | None = None
        self._pending_speed: list[ShotRecord] = []
        self._last_moment_t = -math.inf
        self._moment_count = 0
        self._top_speed = 0.0
        self._last_top_speed_t = -math.inf
        self._next_control_eval = CONTROL_EVAL_S
        self._controller: Side | None = None
        self._chaotic = False

    # Public API

    def push(self, item: MatchEvent | TrackingFrame) -> list[Moment]:
        if isinstance(item, TrackingFrame):
            found = self._on_frame(item)
        else:
            found = self._on_event(item)
        found += self._control_check()
        self.moments.extend(found)
        return found

    def state(self) -> GameState:
        return GameState(
            minute=self.t / 60.0,
            score=(self.score[0], self.score[1]),
            xg=(self.xg[0], self.xg[1]),
            men=(self.men[0], self.men[1]),
        )

    def stats(self) -> StatsUpdate:
        control, chaos, _ = self._control()
        return StatsUpdate(
            t=self.t,
            score=(self.score[0], self.score[1]),
            xg=(round(self.xg[0], 3), round(self.xg[1], 3)),
            xt=(round(self.xt_added[0], 3), round(self.xt_added[1], 3)),
            possession=self.timeline.share(0.0, self.t) if self.t > 0 else (0.5, 0.5),
            win_prob=result_probs(self.prior, self.state()),
            momentum=round(math.tanh(self.momentum_raw * MOMENTUM_SCALE), 3),
            control_index=round(control, 3),
            chaos_index=round(chaos, 3),
        )

    def leverage_table(self) -> list[LeverageRow]:
        return sorted(self.leverage_rows.values(), key=lambda r: -r.total)

    def press_table(self) -> list[PressRow]:
        return self.press.table()

    # Events

    def _on_event(self, e: MatchEvent) -> list[Moment]:
        self.t = max(self.t, e.t)
        k = SIDES.index(e.team)
        self.press.record(e)
        found: list[Moment] = []
        handler = {
            EventType.POSSESSION_CHANGE: self._possession_change,
            EventType.PASS: self._pass,
            EventType.CARRY: self._carry,
            EventType.SHOT: self._shot,
            EventType.GOAL: self._goal,
            EventType.TACKLE: self._tackle,
            EventType.INTERCEPTION: self._interception,
            EventType.CARD: self._card,
        }.get(e.type)
        if handler is not None:
            found += handler(e, k)
        self.press.resolve(e.t, self.timeline)
        return found

    def _possession_change(self, e: MatchEvent, k: int) -> list[Moment]:
        self.timeline.change(e.t, e.team)
        reason = e.meta.get("reason")
        if reason != "kickoff":
            self.window.add(e.t, e.team, "turnover")
        lf = self._last_failed
        if reason in ("throw_in", "goal_kick", "loose_ball") and lf and lf[1] != e.team and e.t - lf[3] <= FAILED_PASS_WINDOW_S:
            passer, _, p_complete, _ = lf
            self._last_failed = None
            gainer = e.player_id if reason == "loose_ball" else None
            lev = self.model.turnover(self.state(), k, e.x, e.y, "misplaced_pass", gainer, passer, p_complete)
            return self._apply(e, lev)
        return []

    def _pass(self, e: MatchEvent, k: int) -> list[Moment]:
        self.passes[k] += 1
        sx, sy = to_attacking(e.x, e.y, e.team)
        ex, ey = to_attacking(e.end_x, e.end_y, e.team)
        p_complete = metrics.pass_completion(sx, sy, ex, ey, e.pressure)
        if e.outcome == "complete":
            self.completed[k] += 1
            self.window.add(e.t, e.team, "pass_ok")
            self._threat(k, sx, sy, ex, ey)
            receiver = e.meta.get("receiver", "")
            self._last_complete[e.team] = (e.player_id or "", receiver, e.t, bool(e.meta.get("cross")))
            lev = self.model.completed_pass(self.state(), k, e.end_x, e.end_y, e.player_id or "", p_complete)
            return self._apply(e, lev)
        self.window.add(e.t, e.team, "pass_fail")
        self._last_failed = (e.player_id or "", e.team, p_complete, e.t)
        return []

    def _carry(self, e: MatchEvent, k: int) -> list[Moment]:
        sx, sy = to_attacking(e.x, e.y, e.team)
        ex, ey = to_attacking(e.end_x, e.end_y, e.team)
        self._threat(k, sx, sy, ex, ey)
        return []

    def _threat(self, k: int, sx: float, sy: float, ex: float, ey: float) -> None:
        gain = self.xt.at(ex, ey) - self.xt.at(sx, sy)
        self.xt_added[k] += max(gain, 0.0)
        signed = gain if k == 0 else -gain
        self.momentum_raw = MOMENTUM_ALPHA * signed + (1 - MOMENTUM_ALPHA) * self.momentum_raw

    def _shot(self, e: MatchEvent, k: int) -> list[Moment]:
        xa, ya = to_attacking(e.x, e.y, e.team)
        header = e.body_part == "head"
        defender_m = self._defender_distance(e)
        xg = metrics.xg(xa, ya, header, e.pressure, defender_m)
        score_before = f"{self.score[0]}-{self.score[1]}"
        self.xg[k] += xg
        shooter = e.player_id or ""
        lc = self._last_complete.get(e.team)
        fed = lc is not None and lc[1] == shooter
        creator = lc[0] if fed and e.t - lc[2] <= ASSIST_WINDOW_S else None
        first_time = fed and e.t - lc[2] <= 1.0
        stopper = e.meta.get("keeper") or e.meta.get("blocker") or None
        goal = e.outcome == "goal"
        lev = self.model.shot(self.state(), k, xg, goal, shooter, creator, stopper)
        distance, angle = goal_geometry(xa, ya)
        record = ShotRecord(
            e.event_id, e.team, shooter, e.minute, e.t, e.x, e.y, round(xg, 3), e.outcome or "",
            e.body_part or "foot", round(lev.value, 3),
            shot_type=shot_type(header, distance, first_time, fed and lc[3], assisted=creator is not None),
            distance_m=round(distance, 1),
            angle_deg=round(math.degrees(angle), 1),
            pressure=e.pressure,
            defender_m=None if defender_m is None else round(defender_m, 1),
            creator=creator,
            score_before=score_before,
            wp_if_goal=round(lev.wp_actual if goal else lev.wp_opposite, 4),
            wp_if_miss=round(lev.wp_opposite if goal else lev.wp_actual, 4),
        )
        self.shots.append(record)
        if e.outcome != "blocked":  # a blocked shot stops within metres, so its speed means nothing
            self._pending_speed.append(record)
        self._credit(lev)
        self.leverage_log[e.event_id] = lev
        if goal:
            self._pending_goal = (record, lev)
            return []
        if xg >= BIG_CHANCE_XG:
            return self._moment(
                "big_chance", e, lev.value, [shooter],
                {"xg": round(xg, 3), "player": shooter, "outcome": e.outcome or "",
                 "wp_if_scored": round(lev.wp_opposite, 3), "leverage": round(lev.value, 3)},
                debounce=True,
            )
        return []

    def _defender_distance(self, e: MatchEvent) -> float | None:
        """Distance from the shooter to the nearest outfield defender: from the shot's freeze frame
        when the feed sends one, otherwise from the latest tracking frame."""
        frozen = e.meta.get("defenders")
        if frozen:
            return metrics.nearest_defender(e.x, e.y, frozen)
        f = self._last_frame
        if f is None:
            return None
        return metrics.nearest_defender(
            e.x, e.y, [(p.x, p.y) for p in f.players if p.team != e.team and p.id not in self._keepers]
        )

    def _goal(self, e: MatchEvent, k: int) -> list[Moment]:
        self.score[k] += 1
        if self._pending_goal is None:
            return []
        record, lev = self._pending_goal
        self._pending_goal = None
        kind: MomentKind = "low_xg_goal" if record.xg < LOW_XG_GOAL else "goal"
        return self._moment(
            kind, e, lev.value, [record.player_id],
            {"xg": record.xg, "player": record.player_id, "score": f"{self.score[0]}-{self.score[1]}",
             "wp_before": round(lev.wp_before, 3), "wp_after": round(lev.wp_actual, 3),
             "leverage": round(lev.value, 3)},
            event_ids=[record.event_id, e.event_id],
        )

    def _tackle(self, e: MatchEvent, k: int) -> list[Moment]:
        if e.outcome != "won":
            return []
        lev = self.model.turnover(self.state(), k, e.x, e.y, "tackle", e.player_id, e.meta.get("carrier"), 0.5)
        return self._apply(e, lev)

    def _interception(self, e: MatchEvent, k: int) -> list[Moment]:
        lf = self._last_failed
        share = lf[2] if lf and lf[0] == e.meta.get("passer") else 1.0
        self._last_failed = None
        lev = self.model.turnover(self.state(), k, e.x, e.y, "interception", e.player_id, e.meta.get("passer"), share)
        return self._apply(e, lev)

    def _card(self, e: MatchEvent, k: int) -> list[Moment]:
        if e.outcome != "red":
            return []
        lev = self.model.red_card(self.state(), k, e.player_id or "")
        self.men[k] -= 1
        self._credit(lev)
        self.leverage_log[e.event_id] = lev
        return self._moment(
            "red_card", e, lev.value, [e.player_id or ""],
            {"player": e.player_id or "", "wp_before": round(lev.wp_before, 3),
             "wp_after": round(lev.wp_actual, 3), "leverage": round(lev.value, 3)},
        )

    def _apply(self, e: MatchEvent, lev: Leverage) -> list[Moment]:
        self._credit(lev)
        self.leverage_log[e.event_id] = lev
        if abs(lev.value) < LEVERAGE_MOMENT:
            return []
        if lev.action == "misplaced_pass":
            player = next((c.player_id for c in lev.credits if c.kind == "turnovers"), "")
        else:
            player = e.player_id or (lev.credits[0].player_id if lev.credits else "")
        return self._moment(
            "leverage_swing", e, lev.value, [c.player_id for c in lev.credits],
            {"action": lev.action, "player": player, "wp_before": round(lev.wp_before, 3),
             "wp_after": round(lev.wp_actual, 3), "wp_opposite": round(lev.wp_opposite, 3),
             "leverage": round(lev.value, 3)},
            debounce=True,
        )

    def _credit(self, lev: Leverage) -> None:
        for c in lev.credits:
            row = self.leverage_rows.setdefault(c.player_id, LeverageRow(c.player_id, c.team))
            setattr(row, c.kind, getattr(row, c.kind) + c.value)

    # Frames

    def _on_frame(self, frame: TrackingFrame) -> list[Moment]:
        self.t = max(self.t, frame.t)
        self._last_frame = frame
        self.kinematics.update(frame)
        found: list[Moment] = []
        for change in self.shape.update(frame, self.timeline.current):
            found += self._shape_moment(change)
        found += self._speed_records(frame.t)
        while self._pending_speed and frame.t >= self._pending_speed[0].t + 0.5:
            shot = self._pending_speed.pop(0)
            shot.speed_ms = self.kinematics.ball_speed_after(shot.t)
        self.press.resolve(frame.t, self.timeline)
        return found

    def _speed_records(self, t: float) -> list[Moment]:
        if t - self._last_top_speed_t < 120.0:
            return []
        best_id, best = None, self._top_speed
        for pid, run in self.kinematics.runs.items():
            if run.top_speed_ms > best + 0.15:
                best_id, best = pid, run.top_speed_ms
        if best_id is None:
            return []
        self._top_speed = best
        if best < TOP_SPEED_MOMENT_MS:
            return []
        self._last_top_speed_t = t
        team = self._team_of(best_id)
        return self._moment(
            "top_speed", None, 0.0, [best_id],
            {"player": best_id, "speed_ms": round(best, 2), "speed_kmh": round(best * 3.6, 1)},
            team=team, debounce=True,
        )

    def _team_of(self, player_id: str) -> Side | None:
        if player_id.startswith(self.meta.home):
            return "home"
        if player_id.startswith(self.meta.away):
            return "away"
        return None

    def _shape_moment(self, c: ShapeChange) -> list[Moment]:
        return self._moment(
            "shape_change", None, 0.0, [],
            {"from": c.previous or "", "to": c.state, "line_height_m": round(c.line_height, 1),
             "compactness_m2": round(c.compactness), "pressers": round(c.pressers, 2)},
            team=c.team,
        )

    # Control and chaos

    def _control(self) -> tuple[float, float, Side | None]:
        self.window.trim(self.t)
        t0 = max(self.t - WINDOW_S, 0.0)
        if self.t - t0 < 60.0:
            return 0.0, 0.0, None
        share = self.timeline.share(t0, self.t)
        ok = {"home": 0, "away": 0}
        fail = {"home": 0, "away": 0}
        turnovers = 0
        for _, side, kind in self.window.events:
            if kind == "pass_ok":
                ok[side] += 1
            elif kind == "pass_fail":
                fail[side] += 1
            else:
                turnovers += 1
        control = {}
        for i, side in enumerate(SIDES):
            attempts = ok[side] + fail[side]
            control[side] = share[i] * (ok[side] / attempts if attempts else 0.0)
        leader = max(SIDES, key=lambda s: control[s])
        chaos = turnovers / ((self.t - t0) / 60.0) / CHAOS_BASELINE_PER_MIN
        if abs(control["home"] - control["away"]) < CONTROL_MARGIN:
            leader = None
        return control[leader] if leader else max(control.values()), chaos, leader

    def _control_check(self) -> list[Moment]:
        if self.t < self._next_control_eval:
            return []
        self._next_control_eval = self.t + CONTROL_EVAL_S
        control, chaos, leader = self._control()
        found: list[Moment] = []
        if leader is not None and leader != self._controller:
            if self._controller is not None:
                found += self._moment(
                    "control_flip", None, 0.0, [],
                    {"now_in_control": leader, "control_index": round(control, 3), "chaos_index": round(chaos, 3)},
                    team=leader, debounce=True,
                )
            self._controller = leader
        chaotic = chaos >= CHAOS_HIGH
        if chaotic and not self._chaotic:
            found += self._moment(
                "control_flip", None, 0.0, [],
                {"now_in_control": "nobody", "control_index": round(control, 3), "chaos_index": round(chaos, 3)},
                debounce=True,
            )
        self._chaotic = chaotic
        return found

    # Moments

    def _moment(
        self,
        kind: MomentKind,
        e: MatchEvent | None,
        leverage: float,
        players: list[str],
        evidence: dict[str, float | int | str],
        event_ids: list[str] | None = None,
        team: Side | None = None,
        debounce: bool = False,
    ) -> list[Moment]:
        t = e.t if e is not None else self.t
        if debounce and t - self._last_moment_t < DEBOUNCE_S:
            return []
        self._last_moment_t = t
        self._moment_count += 1
        return [
            Moment(
                moment_id=f"{self.meta.match_id}-mo-{self._moment_count:02d}",
                minute=min(int(t // 60), 130),
                kind=kind,
                leverage=round(leverage, 3),
                team=e.team if e is not None else team,
                players=[p for p in players if p],
                evidence=evidence,
                event_ids=event_ids or ([e.event_id] if e is not None else []),
                state_ref=f"{self.meta.match_id}@{t:.1f}",
            )
        ]
