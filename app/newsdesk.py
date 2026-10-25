"""The Newsdesk's raw material: every matchday fixture played to full time through the live engine.

Each scenario match is simulated with full tracking and fed through the same LiveStats as the live room,
so the article facts (goals, xG, possession, red cards, best spell, leverage leader) match what a fan saw.
Played once and cached in data/newsdesk.json; `python -m app.newsdesk` rebuilds it.
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any

NEWSDESK_PATH = Path(__file__).resolve().parent.parent / "data" / "newsdesk.json"


def play(scenario_id: str) -> dict[str, Any]:
    from app.matchday import match_facts
    from engine.forecast import pre_match
    from engine.league import PROFILES, build_league
    from engine.live import LiveStats
    from engine.models import MatchMeta
    from engine.scenarios import live_match_id, path_for
    from engine.sim import MatchSimulator, SimConfig, load_scenario

    sc = load_scenario(path_for(scenario_id))
    league = build_league()
    home, away = sc.home or "", sc.away or ""
    meta = MatchMeta(match_id=live_match_id(home, away, sc.seed or 0), home=home, away=away, seed=sc.seed or 0)
    live = LiveStats(meta, league)
    for item in MatchSimulator(meta, league, SimConfig(mode="full"), sc).run():
        live.push(item)
    names = {p.player_id: p.name for c in (home, away) for p in league.squads[c]}
    teams = {"home": league.clubs[home].name, "away": league.clubs[away].name}
    forecast = pre_match(home, away)
    pack = match_facts(live, names, teams, True, PROFILES[home].rival == away, forecast)
    pack["facts"]["ground"] = PROFILES[home].ground
    return {"scenario": scenario_id, "title": sc.title, "hint": sc.story, "home": home, "away": away,
            "forecast": [round(p, 3) for p in forecast], **pack}


def main() -> None:
    from engine.scenarios import STORIES

    with ProcessPoolExecutor() as pool:
        matches = list(pool.map(play, [s.scenario_id for s in STORIES]))
    NEWSDESK_PATH.write_text(json.dumps({"matchday": 9, "matches": matches}, ensure_ascii=False, indent=1), encoding="utf-8")
    for m in matches:
        print(m["scenario"], m["facts"]["score"], m["facts"].get("leader", "draw"), m["truths"])


@lru_cache(maxsize=1)
def matches() -> list[dict[str, Any]]:
    return json.loads(NEWSDESK_PATH.read_text(encoding="utf-8"))["matches"]


if __name__ == "__main__":
    main()
