"""League page payloads: clubs with their identities, the table, results, scorers and the live matchday."""

from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
from typing import Any

from engine.league import PROFILES, League
from engine.scenarios import STORIES, library
from engine.season import CURRENT_MATCHDAY, MATCHDAY_FIXTURES, Season, load_season


@lru_cache(maxsize=1)
def season() -> Season:
    return load_season()


def club_dict(league: League, club_id: str, s: Season) -> dict[str, Any]:
    c = league.clubs[club_id]
    return {
        "id": c.club_id, "name": c.name, "short": c.short, "primary": c.primary, "secondary": c.secondary,
        "formation": c.formation, **asdict(PROFILES[club_id]), "form": s.form(club_id),
    }


def scenarios_payload() -> list[dict[str, Any]]:
    return [{"id": sc.scenario_id, "title": sc.title, "story": sc.story, "home": sc.home, "away": sc.away}
            for sc in library()]


def league_payload(league: League) -> dict[str, Any]:
    s = season()
    stories = {(st.home, st.away): st for st in STORIES}
    results = [
        {"matchday": r.matchday, "home": r.home, "away": r.away, "score": list(r.score), "xg": list(r.xg),
         "goals": r.goals}
        for r in s.results if r.season == "this"
    ]
    fixtures = [
        {"home": h, "away": a, "scenario": stories[(h, a)].scenario_id, "title": stories[(h, a)].title,
         "story": stories[(h, a)].story, "h2h": s.head_to_head(h, a)}
        for h, a in MATCHDAY_FIXTURES
    ]
    return {
        "matchday": CURRENT_MATCHDAY,
        "clubs": {cid: club_dict(league, cid, s) for cid in league.clubs},
        "table": s.table("this"),
        "last_table": s.table("last"),
        "results": results,
        "fixtures": fixtures,
        "players": s.players("this")[:20],
    }
