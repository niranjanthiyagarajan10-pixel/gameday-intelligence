"""The Newsdesk's raw material: every matchday fixture played to full time through the live engine.

Each scenario match is simulated with full tracking and fed through the same LiveStats as the live room,
so the article facts (goals, xG, possession, red cards, best spell, leverage leader) match what a fan saw.
Played once and cached in data/newsdesk.json; `python -m app.newsdesk` rebuilds it.

The matches are finished, so their reports never change. `python -m app.newsdesk --write` has the Newsdesk
agent write each one on Microsoft Foundry, retrying until a draft passes every check, and keeps the verified
reports (with their Spanish and Hindi) in data/newsdesk_written.json. The app serves those at once.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any

NEWSDESK_PATH = Path(__file__).resolve().parent.parent / "data" / "newsdesk.json"
WRITTEN_PATH = Path(__file__).resolve().parent.parent / "data" / "newsdesk_written.json"
WRITE_ROUNDS = 4  # each round is a draft and up to two retries


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


def build() -> None:
    from engine.scenarios import STORIES

    with ProcessPoolExecutor() as pool:
        played = list(pool.map(play, [s.scenario_id for s in STORIES]))
    NEWSDESK_PATH.write_text(json.dumps({"matchday": 9, "matches": played}, ensure_ascii=False, indent=1), encoding="utf-8")
    for m in played:
        print(m["scenario"], m["facts"]["score"], m["facts"].get("leader", "draw"), m["truths"])


async def write() -> None:
    """The Newsdesk agent writes every report on Foundry until each passes its checks."""
    from agents import newsdesk
    from agents.desk import name_list
    from agents.llm import LLM
    from app.env import load_env
    from app.room import MatchRoom, RoomConfig
    from engine.league import build_league

    load_env()
    llm = LLM.from_env()
    if not llm.live:
        raise SystemExit("no Foundry endpoint configured")
    await llm.warm()
    league = build_league()
    room = MatchRoom("newsdesk", league, RoomConfig(scenario=None), llm)
    written = json.loads(WRITTEN_PATH.read_text(encoding="utf-8")) if WRITTEN_PATH.exists() else {}
    for m in matches():
        if m["scenario"] in written:
            continue  # keep reports already written and checked; delete an entry to rewrite it
        names = name_list({p.player_id: p.name for c in (m["home"], m["away"]) for p in league.squads[c]},
                          {"home": m["facts"]["home"], "away": m["facts"]["away"]})
        for attempt in range(WRITE_ROUNDS):
            filled, source, langs = await room._write_story(
                "news", "Newsdesk", newsdesk, m["facts"], m["truths"], newsdesk.prompt(m["facts"], m["hint"]), names)
            if source == "agent":
                written[m["scenario"]] = {**filled, "langs": langs, "model": llm.strong,
                                          "written_at": time.strftime("%Y-%m-%d %H:%M")}
                print(m["scenario"], "written on round", attempt + 1, "|", filled["headline"])
                break
        else:
            print(m["scenario"], "kept its template after", WRITE_ROUNDS, "rounds")
    WRITTEN_PATH.write_text(json.dumps(written, ensure_ascii=False, indent=1), encoding="utf-8")


@lru_cache(maxsize=1)
def matches() -> list[dict[str, Any]]:
    return json.loads(NEWSDESK_PATH.read_text(encoding="utf-8"))["matches"]


@lru_cache(maxsize=1)
def written() -> dict[str, Any]:
    """Reports the Newsdesk agent wrote ahead of time and the checks passed, by scenario."""
    return json.loads(WRITTEN_PATH.read_text(encoding="utf-8")) if WRITTEN_PATH.exists() else {}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="have the Newsdesk agent write every report on Foundry")
    args = ap.parse_args()
    asyncio.run(write()) if args.write else build()
