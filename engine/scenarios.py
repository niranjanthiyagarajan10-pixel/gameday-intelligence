"""The scenario library: one story for every match of the live matchday.

Goals cannot be scripted, so each story is found rather than forced. For each fixture we
search seeds until the simulated match plays out the way the story says (a derby comeback,
an upset, a 0-0), then store that seed. The checks below are re-run by the tests, so a
change to the simulator that breaks a story is caught.

`python -m engine.scenarios` searches again and rewrites data/scenarios/.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from engine.league import build_league
from engine.models import MatchMeta
from engine.season import CURRENT_MATCHDAY, Result, summarize
from engine.sim import Incident, MatchSimulator, Scenario, SimConfig, load_scenario

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "data" / "scenarios"
SEARCH_SEEDS = range(1, 400)


def running_scores(r: Result) -> list[tuple[int, int, int]]:
    """(minute, home goals, away goals) after each goal."""
    h = a = 0
    out = []
    for g in sorted(r.goals, key=lambda g: g["minute"]):
        h, a = (h + 1, a) if g["team"] == "home" else (h, a + 1)
        out.append((g["minute"], h, a))
    return out


def _came_back_from_two(r: Result) -> bool:
    for side in (0, 1):
        trailed = any((s[2 - side] - s[1 + side]) >= 2 for s in running_scores(r))
        if trailed and r.score[side] >= r.score[1 - side]:
            return True
    return False


def _upset(r: Result) -> bool:
    return r.score[1] > r.score[0] and r.xg[0] > r.xg[1]


def _ten_men_win(r: Result, side: int, red_minute: int) -> bool:
    team = ("home", "away")[side]
    scored_after = any(g["team"] == team and g["minute"] > red_minute for g in r.goals)
    behind_after = any(m > red_minute and (h, a)[side] < (h, a)[1 - side] for m, h, a in running_scores(r))
    return r.score[side] > r.score[1 - side] and scored_after and behind_after


@dataclass(frozen=True)
class Story:
    scenario_id: str
    title: str
    story: str
    home: str
    away: str
    incidents: tuple[Incident, ...]
    check: Callable[[Result], bool]
    seed: int | None = None  # fixed for the demo match; searched for the rest

    def scenario(self, seed: int) -> Scenario:
        return Scenario(
            name=f"{self.title}: {build_league().clubs[self.home].name} v {build_league().clubs[self.away].name}",
            scenario_id=self.scenario_id, title=self.title, story=self.story, home=self.home, away=self.away,
            seed=seed, matchday=CURRENT_MATCHDAY, incidents=list(self.incidents),
        )


STORIES: list[Story] = [
    Story("demo", "Ten men at Harbour Park",
          "Ashford lose Callum Hale to a red card and spend the rest of the match under siege.",
          "KR", "AV", (Incident(minute=55, kind="red_card", team="away", player_number=8),),
          check=lambda r: r.reds[1] >= 1, seed=7),
    Story("derby", "The Marsh derby",
          "Redmarsh and Thornwick, neighbours and rivals. One of them goes two down and fights back.",
          "RU", "TW", (), check=_came_back_from_two),
    Story("upset", "Smash and grab",
          "Castlemere make the chances; Eastwick take the points.",
          "CC", "EA", (), check=_upset),
    Story("fightback", "Ten-man fight-back",
          "Northvale lose a defender to a red card, fall behind, and still win.",
          "NA", "BF", (Incident(minute=30, kind="red_card", team="home", player_number=4),),
          check=lambda r: _ten_men_win(r, 0, 30)),
    Story("chess", "The chess match",
          "Two cautious sides cancel each other out: a goalless draw decided by shape, not shots.",
          "WH", "SM", (Incident(minute=0, kind="tactic", team="home", press=0.3),
                       Incident(minute=0, kind="tactic", team="away", press=0.3)),
          check=lambda r: r.score == (0, 0) and sum(r.xg) < 1.5),
]
BY_ID = {s.scenario_id: s for s in STORIES}


def play(scenario: Scenario) -> Result:
    assert scenario.home and scenario.away and scenario.seed is not None
    meta = MatchMeta(match_id=f"{scenario.scenario_id}-{scenario.seed}", home=scenario.home, away=scenario.away,
                     seed=scenario.seed)
    events = list(MatchSimulator(meta, build_league(), SimConfig(mode="events_only"), scenario).run())
    return summarize("this", CURRENT_MATCHDAY, scenario.home, scenario.away, events)  # type: ignore[arg-type]


def path_for(scenario_id: str) -> Path:
    return SCENARIO_DIR / f"{scenario_id}.json"


def library() -> list[Scenario]:
    return [load_scenario(path_for(s.scenario_id)) for s in STORIES]


def _try(job: tuple[str, int]) -> tuple[str, int, bool]:
    scenario_id, seed = job
    story = BY_ID[scenario_id]
    return scenario_id, seed, story.check(play(story.scenario(seed)))


def search() -> dict[str, int]:
    """First seed that plays out each story, searched in parallel batches."""
    found = {s.scenario_id: s.seed for s in STORIES if s.seed is not None}
    seeds = iter(SEARCH_SEEDS)
    with ProcessPoolExecutor() as pool:
        while len(found) < len(STORIES):
            batch = [next(seeds) for _ in range(14)]
            jobs = [(s.scenario_id, seed) for s in STORIES if s.scenario_id not in found for seed in batch]
            for scenario_id, seed, ok in pool.map(_try, jobs):
                if ok and scenario_id not in found:
                    found[scenario_id] = seed
            print({k: v for k, v in found.items()}, "after seed", batch[-1])
    return found  # type: ignore[return-value]


def main() -> None:
    for scenario_id, seed in search().items():
        scenario = BY_ID[scenario_id].scenario(seed)
        path_for(scenario_id).write_text(scenario.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8")
        r = play(scenario)
        print(scenario_id, seed, r.score, r.xg, running_scores(r))


if __name__ == "__main__":
    main()
