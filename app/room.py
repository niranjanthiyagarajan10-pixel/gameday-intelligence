"""Match rooms: one simulated match running live, fanned out to every connected viewer.

The main room is the shared broadcast. Private rooms let one viewer (a judge following a jump
link, say) start a replay from any minute without changing what anyone else sees.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from app.payloads import analyst_message, card_message, frame_message, roster, stats_message
from engine.league import League
from engine.live import LiveStats
from engine.models import MatchMeta, TrackingFrame
from engine.sim import MatchSimulator, SimConfig, load_scenario

ROOT = Path(__file__).resolve().parent.parent
DEMO_SCENARIO = str(ROOT / "data" / "scenarios" / "demo.json")

SPEEDS = (1.0, 2.0, 4.0, 10.0, 30.0)
FRAME_INTERVAL_S = 0.1  # at most 10 frames a second to each viewer
STATS_INTERVAL_S = 0.25
ANALYST_INTERVAL_S = 2.0
HISTORY_EVERY_S = 30.0
QUEUE_MAX = 500
PRIVATE_IDLE_S = 15 * 60
MAX_PRIVATE_ROOMS = 20


@dataclass(frozen=True)
class RoomConfig:
    home: str = "KR"
    away: str = "AV"
    seed: int = 7
    scenario: str | None = DEMO_SCENARIO
    speed: float = 1.0
    start_minute: float = 0.0
    half_s: float = 2700.0

    @classmethod
    def from_env(cls) -> RoomConfig:
        return cls(
            home=os.getenv("DEMO_HOME", "KR"),
            away=os.getenv("DEMO_AWAY", "AV"),
            seed=int(os.getenv("DEMO_SEED", "7")),
            scenario=os.getenv("DEMO_SCENARIO", DEMO_SCENARIO) or None,
            speed=float(os.getenv("DEMO_SPEED", "1")),
        )


class MatchRoom:
    def __init__(self, room_id: str, league: League, config: RoomConfig) -> None:
        self.room_id = room_id
        self.league = league
        self.config = config
        self.speed = config.speed
        self.paused = False
        self.subscribers: set[asyncio.Queue] = set()
        self.last_seen = time.monotonic()
        self.task: asyncio.Task | None = None
        self._reset()

    def _reset(self) -> None:
        c = self.config
        # The match id (and so its random streams) depends only on the fixture and seed, never on
        # the room, so every replay of the demo is the same match the main room broadcasts.
        meta = MatchMeta(match_id=f"{c.home}{c.away}-{c.seed}", home=c.home, away=c.away, seed=c.seed, scenario=c.scenario)
        scenario = load_scenario(c.scenario) if c.scenario else None
        self.sim = MatchSimulator(meta, self.league, SimConfig(mode="full", half_s=c.half_s), scenario)
        self.live = LiveStats(meta, self.league)
        self.roster = roster(self.sim, self.league)
        self.names = {pid: p["name"] for pid, p in self.roster["players"].items()}
        self.teams = {side: club["name"] for side, club in self.roster["clubs"].items()}
        self.cards: list[dict[str, Any]] = []
        self.history: list[list[float]] = []
        self.last_frame: dict[str, Any] | None = None
        self.status = "live"
        self._next_history_t = 0.0

    # Snapshots

    def hello(self) -> dict[str, Any]:
        return {
            "type": "hello",
            "room": self.room_id,
            "status": self.status,
            "speed": self.speed,
            "paused": self.paused,
            "half_s": self.config.half_s,
            "roster": self.roster,
            "stats": stats_message(self.live.stats()),
            "frame": self.last_frame,
            "history": self.history,
            "cards": self.cards,
            "analyst": analyst_message(self.live),
        }

    def cues(self) -> list[dict[str, Any]]:
        return [cue for card in self.cards for cue in card["cues"].values()]

    # Viewers

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self.subscribers.add(q)
        self.last_seen = time.monotonic()
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)
        self.last_seen = time.monotonic()

    def publish(self, msg: dict[str, Any]) -> None:
        for q in list(self.subscribers):
            if q.full():  # a slow viewer drops its oldest message rather than holding up the match
                q.get_nowait()
            q.put_nowait(msg)

    # Running the match

    def advance(self) -> list[dict[str, Any]]:
        """One simulator tick through the live engine. Returns the cards it produced."""
        produced: list[dict[str, Any]] = []
        frame = None
        for item in self.sim.step():
            for moment in self.live.push(item):
                card = card_message(moment, self.names, self.teams, self.sim.meta.match_id)
                self.cards.append(card)
                produced.append(card)
                self._record_history()
            if isinstance(item, TrackingFrame):
                frame = item
        if frame is not None:
            self.last_frame = frame_message(frame)
        if self.live.t >= self._next_history_t:
            self._record_history()
            self._next_history_t = self.live.t + HISTORY_EVERY_S
        return produced

    def _record_history(self) -> None:
        s = self.live.stats()
        self.history.append([round(s.t, 1), *(round(p, 4) for p in s.win_prob)])

    def fast_forward(self, until_t: float) -> None:
        while not self.sim.finished and self.sim.t < until_t:
            self.advance()

    async def run(self) -> None:
        if self.config.start_minute > 0:
            self.status = "catching_up"
            await asyncio.to_thread(self.fast_forward, self.config.start_minute * 60)
            self.status = "live"
            self.publish(self.hello())
        dt = self.sim.config.dt
        last_frame = last_stats = last_analyst = 0.0
        next_tick = time.monotonic()
        while True:
            if self.sim.finished:
                if self.status != "full_time":
                    self.status = "full_time"
                    self.publish(stats_message(self.live.stats()))
                    self.publish(analyst_message(self.live))
                    self.publish(self._control_message())
                await asyncio.sleep(0.5)
                next_tick = time.monotonic()
                continue
            if self.paused:
                await asyncio.sleep(0.1)
                next_tick = time.monotonic()
                continue

            for card in self.advance():
                self.publish(card)
            now = time.monotonic()
            if self.last_frame and now - last_frame >= FRAME_INTERVAL_S:
                self.publish(self.last_frame)
                last_frame = now
            if now - last_stats >= STATS_INTERVAL_S:
                self.publish(stats_message(self.live.stats()))
                last_stats = now
            if now - last_analyst >= ANALYST_INTERVAL_S:
                self.publish(analyst_message(self.live))
                last_analyst = now

            next_tick += dt / self.speed
            delay = next_tick - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                if delay < -1.0:  # cannot keep up at this speed: stop trying to catch up
                    next_tick = time.monotonic()
                await asyncio.sleep(0)

    # Controls

    def _control_message(self) -> dict[str, Any]:
        return {"type": "control", "status": self.status, "speed": self.speed, "paused": self.paused}

    def control(self, action: str, value: float | None = None) -> dict[str, Any]:
        if action == "speed":
            if value not in SPEEDS:
                raise ValueError(f"speed must be one of {SPEEDS}")
            self.speed = float(value)
        elif action == "pause":
            self.paused = True
        elif action == "resume":
            self.paused = False
        elif action == "restart":
            self._reset()
            self.paused = False
            self.publish(self.hello())
        else:
            raise ValueError(f"unknown action {action}")
        msg = self._control_message()
        self.publish(msg)
        return msg


class Hub:
    def __init__(self, league: League, default: RoomConfig) -> None:
        self.league = league
        self.default = default
        self.rooms: dict[str, MatchRoom] = {}
        self._reaper: asyncio.Task | None = None

    async def start(self) -> None:
        self._launch("main", self.default)
        self._reaper = asyncio.create_task(self._reap())

    async def stop(self) -> None:
        tasks = [r.task for r in self.rooms.values() if r.task] + ([self._reaper] if self._reaper else [])
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def get(self, room_id: str) -> MatchRoom | None:
        return self.rooms.get(room_id)

    def private(self, start_minute: float, speed: float) -> MatchRoom:
        if sum(1 for r in self.rooms if r != "main") >= MAX_PRIVATE_ROOMS:
            raise RuntimeError("too many replays running, try again in a few minutes")
        room_id = uuid.uuid4().hex[:8]
        return self._launch(room_id, replace(self.default, start_minute=start_minute, speed=speed))

    def _launch(self, room_id: str, config: RoomConfig) -> MatchRoom:
        room = MatchRoom(room_id, self.league, config)
        room.task = asyncio.create_task(room.run())
        self.rooms[room_id] = room
        return room

    async def _reap(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()
            for room_id, room in list(self.rooms.items()):
                if room_id != "main" and not room.subscribers and now - room.last_seen > PRIVATE_IDLE_S:
                    if room.task:
                        room.task.cancel()
                    del self.rooms[room_id]
