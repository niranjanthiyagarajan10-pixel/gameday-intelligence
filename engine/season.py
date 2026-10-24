"""The season so far: a fixture list, last season in full and this season up to the live matchday.

Every result comes from a seeded simulation, so the table, form, head to head and scorer
lists are real outputs of the same engine that plays the live match. They are simulated
once and cached in data/season.json; `python -m engine.season` rebuilds the cache.
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from engine import metrics
from engine.league import build_league
from engine.models import EventType, MatchEvent, MatchMeta
from engine.pitch import to_attacking
from engine.sim import MatchSimulator, SimConfig

SeasonName = Literal["last", "this"]

SEASON_PATH = Path(__file__).resolve().parent.parent / "data" / "season.json"
CURRENT_MATCHDAY = 9
# The live round: the demo match, a derby and three more stories. See data/scenarios/.
MATCHDAY_FIXTURES = [("KR", "AV"), ("NA", "BF"), ("CC", "EA"), ("RU", "TW"), ("WH", "SM")]
_SEASON_BASE = {"last": 500_000, "this": 600_000}


def schedule() -> list[list[tuple[str, str]]]:
    """18 matchdays, each club home and away against every other once.

    Round robin by the circle method. The order of clubs is chosen so the first round is
    MATCHDAY_FIXTURES; that round is played as matchday 9, the last of the first half.
    """
    order = [h for h, _ in MATCHDAY_FIXTURES] + [a for _, a in reversed(MATCHDAY_FIXTURES)]
    n = len(order)
    rounds: list[list[tuple[str, str]]] = []
    for r in range(n - 1):
        pairs = [(order[i], order[n - 1 - i]) for i in range(n // 2)]
        rounds.append([p if r % 2 == 0 else (p[1], p[0]) for p in pairs])
        order = [order[0], order[-1], *order[1:-1]]
    first_half = rounds[1:] + rounds[:1]
    return first_half + [[(a, h) for h, a in fixtures] for fixtures in first_half]


def match_seed(season: SeasonName, matchday: int, index: int) -> int:
    return _SEASON_BASE[season] + 100 * matchday + index


@dataclass(frozen=True)
class Result:
    season: SeasonName
    matchday: int
    home: str
    away: str
    score: tuple[int, int]
    xg: tuple[float, float]
    shots: tuple[int, int]
    on_target: tuple[int, int]
    reds: tuple[int, int]
    goals: list[dict[str, Any]] = field(default_factory=list)  # minute, team, player_id, xg
    players: dict[str, dict[str, Any]] = field(default_factory=dict)  # shooters: goals, shots, xg

    def side(self, club: str) -> int:
        return 0 if club == self.home else 1

    def outcome(self, club: str) -> str:
        k = self.side(club)
        mine, theirs = self.score[k], self.score[1 - k]
        return "W" if mine > theirs else "L" if mine < theirs else "D"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Result:
        tuples = {k: tuple(d[k]) for k in ("score", "xg", "shots", "on_target", "reds")}
        return cls(**{**d, **tuples})


def summarize(season: SeasonName, matchday: int, home: str, away: str, events: list[MatchEvent]) -> Result:
    """The facts a table, a form guide and a scorer list need, from one match's events."""
    sides = ("home", "away")
    score, xg, shots, on_target, reds = [0, 0], [0.0, 0.0], [0, 0], [0, 0], [0, 0]
    goals: list[dict[str, Any]] = []
    players: dict[str, dict[str, Any]] = {}
    for e in events:
        k = sides.index(e.team)
        if e.type == EventType.CARD and e.outcome == "red":
            reds[k] += 1
        if e.type != EventType.SHOT:
            continue
        xa, ya = to_attacking(e.x, e.y, e.team)
        defender = metrics.nearest_defender(e.x, e.y, e.meta.get("defenders") or [])
        chance = metrics.xg(xa, ya, e.body_part == "head", e.pressure, defender)
        xg[k] += chance
        shots[k] += 1
        row = players.setdefault(e.player_id or "", {"goals": 0, "shots": 0, "xg": 0.0})
        row["shots"] += 1
        row["xg"] = round(row["xg"] + chance, 3)
        if e.outcome in ("goal", "saved"):
            on_target[k] += 1
        if e.outcome == "goal":
            score[k] += 1
            row["goals"] += 1
            goals.append({"minute": e.minute, "team": e.team, "player_id": e.player_id, "xg": round(chance, 3)})
    return Result(
        season=season, matchday=matchday, home=home, away=away,
        score=(score[0], score[1]), xg=(round(xg[0], 3), round(xg[1], 3)),
        shots=(shots[0], shots[1]), on_target=(on_target[0], on_target[1]), reds=(reds[0], reds[1]),
        goals=goals, players=players,
    )


def play(job: tuple[SeasonName, int, str, str]) -> Result:
    season, matchday, home, away = job
    index = schedule()[matchday - 1].index((home, away))
    seed = match_seed(season, matchday, index)
    meta = MatchMeta(match_id=f"{season}-md{matchday:02d}-{home}{away}", home=home, away=away, seed=seed)
    events = list(MatchSimulator(meta, build_league(), SimConfig(mode="events_only")).run())
    return summarize(season, matchday, home, away, events)  # type: ignore[arg-type]


class Season:
    """Tables, form, head to head and player lists, derived from results. Nothing here is random."""

    def __init__(self, results: list[Result]) -> None:
        order = {"last": 0, "this": 1}
        self.results = sorted(results, key=lambda r: (order[r.season], r.matchday, r.home))

    def _of(self, season: SeasonName) -> list[Result]:
        return [r for r in self.results if r.season == season]

    def table(self, season: SeasonName = "this") -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for r in self._of(season):
            for club in (r.home, r.away):
                k = r.side(club)
                row = rows.setdefault(club, {"club": club, "played": 0, "won": 0, "drawn": 0, "lost": 0,
                                             "gf": 0, "ga": 0, "gd": 0, "points": 0, "xg_for": 0.0, "xg_against": 0.0})
                result = r.outcome(club)
                row["played"] += 1
                row[{"W": "won", "D": "drawn", "L": "lost"}[result]] += 1
                row["points"] += {"W": 3, "D": 1, "L": 0}[result]
                row["gf"] += r.score[k]
                row["ga"] += r.score[1 - k]
                row["gd"] = row["gf"] - row["ga"]
                row["xg_for"] = round(row["xg_for"] + r.xg[k], 2)
                row["xg_against"] = round(row["xg_against"] + r.xg[1 - k], 2)
        table = sorted(rows.values(), key=lambda t: (-t["points"], -t["gd"], -t["gf"], t["club"]))
        return [{"position": i + 1, **row} for i, row in enumerate(table)]

    def form(self, club: str, n: int = 5, season: SeasonName = "this") -> list[str]:
        """Latest result first."""
        played = [r for r in self._of(season) if club in (r.home, r.away)]
        return [r.outcome(club) for r in reversed(played)][:n]

    def head_to_head(self, a: str, b: str) -> list[dict[str, Any]]:
        """Every meeting, latest first."""
        met = [r for r in self.results if {r.home, r.away} == {a, b}]
        return [{"season": r.season, "matchday": r.matchday, "home": r.home, "away": r.away, "score": list(r.score)}
                for r in reversed(met)]

    def players(self, season: SeasonName = "this") -> list[dict[str, Any]]:
        """Everyone who shot this season, top scorers first. goals_above_xg is finishing skill plus luck."""
        league = build_league()
        totals: dict[str, dict[str, Any]] = {}
        for r in self._of(season):
            for pid, s in r.players.items():
                t = totals.setdefault(pid, {"goals": 0, "shots": 0, "xg": 0.0})
                t["goals"] += s["goals"]
                t["shots"] += s["shots"]
                t["xg"] += s["xg"]
        rows = []
        for pid, t in totals.items():
            p = league.player(pid)
            rows.append({"player_id": pid, "name": p.name, "club": p.club_id, "position": p.position,
                         "goals": t["goals"], "shots": t["shots"], "xg": round(t["xg"], 2),
                         "goals_above_xg": round(t["goals"] - t["xg"], 2)})
        return sorted(rows, key=lambda p: (-p["goals"], -p["xg"], p["player_id"]))

    def results_for(self, club: str, season: SeasonName = "this") -> list[Result]:
        return [r for r in self._of(season) if club in (r.home, r.away)]


def load_season(path: Path = SEASON_PATH) -> Season:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Season([Result.from_json(d) for d in data["results"]])


def jobs() -> list[tuple[SeasonName, int, str, str]]:
    rounds = schedule()
    out: list[tuple[SeasonName, int, str, str]] = []
    for season, last_md in (("last", len(rounds)), ("this", CURRENT_MATCHDAY - 1)):
        for md in range(1, last_md + 1):
            out += [(season, md, h, a) for h, a in rounds[md - 1]]  # type: ignore[misc]
    return out


def main() -> None:
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(play, jobs()))
    body = {"matchday": CURRENT_MATCHDAY, "results": [r.to_json() for r in results]}
    SEASON_PATH.write_text(json.dumps(body, separators=(",", ":")), encoding="utf-8")
    season = Season(results)
    for row in season.table("this"):
        print(row["position"], row["club"], row["played"], row["points"], row["gd"])
    print("top scorers", season.players("this")[:5])


if __name__ == "__main__":
    main()
