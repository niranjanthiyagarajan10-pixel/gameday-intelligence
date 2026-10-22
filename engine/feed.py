"""The ingest boundary. Everything downstream reads a match through a Feed, never the simulator.

A feed delivers one tick at a time: the match events that happened in that tick, then the
tracking frame. Today the feed is our simulator, because the hackathon requires synthetic data.
For a real league only this boundary changes: an adapter that turns a data provider's live feed
into the same MatchEvent and TrackingFrame contracts. A recorded feed (JSON lines) replays any
match exactly, which is how a broadcaster would re-run a match through the pipeline.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from engine.models import MatchEvent, MatchMeta, Side, TrackingFrame
from engine.sim import MatchSimulator

FeedItem = MatchEvent | TrackingFrame


class Feed(Protocol):
    meta: MatchMeta
    dt: float
    lineups: dict[Side, list[str]]

    @property
    def t(self) -> float: ...

    @property
    def finished(self) -> bool: ...

    def step(self) -> list[FeedItem]: ...


class SimulatorFeed:
    """Our synthetic data provider: the seeded match simulator."""

    def __init__(self, sim: MatchSimulator) -> None:
        self.sim = sim
        self.meta = sim.meta
        self.dt = sim.config.dt
        self.lineups: dict[Side, list[str]] = {
            side: [p.player_id for p in players] for side, players in sim.lineups.items()  # type: ignore[misc]
        }

    @property
    def t(self) -> float:
        return self.sim.t

    @property
    def finished(self) -> bool:
        return self.sim.finished

    def step(self) -> list[FeedItem]:
        return self.sim.step()


def record(feed: Feed, path: str | Path) -> int:
    """Write a whole feed to JSON lines: a header, then one line per tick. Returns the tick count."""
    ticks = 0
    with Path(path).open("w", encoding="utf-8") as f:
        f.write(json.dumps({"meta": feed.meta.model_dump(mode="json"), "dt": feed.dt, "lineups": feed.lineups}) + "\n")
        while not feed.finished:
            items = feed.step()
            f.write(json.dumps([
                {"kind": "frame" if isinstance(i, TrackingFrame) else "event", **i.model_dump(mode="json")} for i in items
            ]) + "\n")
            ticks += 1
    return ticks


class RecordedFeed:
    """Replays a recorded feed tick by tick, exactly as it was delivered."""

    def __init__(self, path: str | Path) -> None:
        self._file = Path(path).open(encoding="utf-8")
        header = json.loads(self._file.readline())
        self.meta = MatchMeta.model_validate(header["meta"])
        self.dt = float(header["dt"])
        self.lineups = header["lineups"]
        self._ticks: Iterator[str] = iter(self._file)
        self._tick = 0
        self._finished = False

    @property
    def t(self) -> float:
        return round(self._tick * self.dt, 2)

    @property
    def finished(self) -> bool:
        return self._finished

    def step(self) -> list[FeedItem]:
        line = next(self._ticks, None)
        if line is None:
            self._finished = True
            self._file.close()
            return []
        self._tick += 1
        items: list[FeedItem] = []
        for raw in json.loads(line):
            kind = raw.pop("kind")
            items.append(TrackingFrame.model_validate(raw) if kind == "frame" else MatchEvent.model_validate(raw))
        return items
