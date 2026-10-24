"""Facts for the Preview and Post-game agents, computed by code from the simulated season and the match.

Every value an agent may use is a fact with a slot name, formatted here. The agents write words around
the slots; they never see a number they could retype, because a retyped number fails the check.
"""

from __future__ import annotations

from typing import Any

from engine.forecast import pre_match
from engine.league import PROFILES, League
from engine.season import CURRENT_MATCHDAY, Season, schedule

DECISIVE_KINDS = {"goal", "low_xg_goal", "red_card", "leverage_swing", "big_chance"}


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def pct(p: float) -> str:
    return f"{round(p * 100)}%"


def signed(v: float) -> str:
    return f"+{v:.1f}" if v >= 0 else f"{v:.1f}"


def _row(season: Season, club: str) -> dict[str, Any]:
    return next(r for r in season.table("this") if r["club"] == club)


def _scorer(season: Season, club: str) -> dict[str, Any] | None:
    return next((p for p in season.players("this") if p["club"] == club), None)


def preview(league: League, season: Season, home: str, away: str) -> dict[str, Any]:
    """Facts (slot name to formatted value), the truths the checks need, and the players to watch."""
    clubs = league.clubs
    facts: dict[str, str] = {"home": clubs[home].name, "away": clubs[away].name, "ground": PROFILES[home].ground,
                             "matchday": str(CURRENT_MATCHDAY)}
    truths: dict[str, Any] = {"derby": PROFILES[home].rival == away}
    for side, club in (("home", home), ("away", away)):
        row = _row(season, club)
        form = season.form(club)
        played = max(row["played"], 1)
        facts |= {
            f"{side}_nickname": PROFILES[club].nickname,
            f"{side}_style": PROFILES[club].style.lower(),
            f"{side}_position": ordinal(row["position"]),
            f"{side}_points": str(row["points"]),
            f"{side}_form": " ".join(form),
            f"{side}_wins_last5": str(form.count("W")),
            f"{side}_xg_per_game": f"{row['xg_for'] / played:.2f}",
            f"{side}_xga_per_game": f"{row['xg_against'] / played:.2f}",
        }
        scorer = _scorer(season, club)
        if scorer:
            facts[f"{side}_scorer"] = scorer["name"]
            facts[f"{side}_scorer_goals"] = str(scorer["goals"])
        truths[f"{side}_unbeaten"] = "L" not in form
        truths[f"{side}_winless"] = "W" not in form
        truths[f"{side}_position"] = row["position"]
    meetings = season.head_to_head(home, away)
    if meetings:
        wins = {home: 0, away: 0}
        draws = 0
        for m in meetings:
            h, a = m["score"]
            if h == a:
                draws += 1
            else:
                wins[m["home"] if h > a else m["away"]] += 1
        last = meetings[0]
        facts |= {
            "h2h_meetings": str(len(meetings)), "h2h_home_wins": str(wins[home]), "h2h_draws": str(draws),
            "h2h_away_wins": str(wins[away]),
            "h2h_last": f"{clubs[last['home']].name} {last['score'][0]}-{last['score'][1]} {clubs[last['away']].name}",
        }
    ph, pd, pa = pre_match(home, away)
    facts |= {"forecast_home": pct(ph), "forecast_draw": pct(pd), "forecast_away": pct(pa)}
    truths["favourite"] = "home" if ph > pa + 0.1 else "away" if pa > ph + 0.1 else None
    return {"facts": facts, "truths": truths, "forecast": [round(ph, 3), round(pd, 3), round(pa, 3)],
            "watch": players_to_watch(league, season, home, away),
            "h2h": meetings, "form": {"home": season.form(home), "away": season.form(away)},
            "table": {"home": _row(season, home), "away": _row(season, away)}}


def players_to_watch(league: League, season: Season, home: str, away: str) -> list[dict[str, Any]]:
    """Each side's top scorer, then the best finisher against expected goals from either side."""
    picks: list[dict[str, Any]] = []
    for club in (home, away):
        s = _scorer(season, club)
        if s:
            picks.append({**s, "label": "Goals this season", "value": str(s["goals"])})
    taken = {p["player_id"] for p in picks}
    rest = [p for p in season.players("this") if p["club"] in (home, away) and p["player_id"] not in taken]
    if rest:
        best = max(rest, key=lambda p: p["goals_above_xg"])
        picks.append({**best, "label": "Goals above xG", "value": signed(best["goals_above_xg"])})
    for p in picks:
        p["number"] = league.player(p["player_id"]).number
        p["side"] = "home" if p["club"] == home else "away"
    return picks


def next_fixture(club: str) -> tuple[str, bool] | None:
    """The club's opponent on the next matchday, and whether it plays at home."""
    rounds = schedule()
    if CURRENT_MATCHDAY >= len(rounds):
        return None
    for h, a in rounds[CURRENT_MATCHDAY]:
        if club in (h, a):
            return (a, True) if h == club else (h, False)
    return None


def postgame(room: Any, league: League) -> dict[str, Any]:
    """What decided the match, from its key moments, and what comes next for both clubs."""
    s = room.live.stats()
    home, away = room.config.home, room.config.away
    clubs = league.clubs
    decided = []
    cards = [c for c in room.cards if c["moment"]["kind"] in DECISIVE_KINDS]
    for c in sorted(cards, key=lambda c: -abs(c["moment"]["leverage"]))[:3]:
        m = c["moment"]
        ev = m["evidence"]
        swing = None
        if "wp_before" in ev and "wp_after" in ev:
            swing = round((float(ev["wp_after"]) - float(ev["wp_before"])) * 100)
        decided.append({"moment_id": m["moment_id"], "minute": m["minute"], "kind": m["kind"], "team": m.get("team"),
                        "swing": swing, "leverage": round(m["leverage"], 2), "text": c["cues"]["casual"]["text"],
                        "langs": {lang: v["casual"]["text"] for lang, v in c.get("langs", {}).items() if "casual" in v}})
    goals_minus_xg = [s.score[k] - s.xg[k] for k in (0, 1)]
    facts: dict[str, str] = {"home": clubs[home].name, "away": clubs[away].name,
                             "score": f"{s.score[0]}-{s.score[1]}",
                             "home_xg": f"{s.xg[0]:.2f}", "away_xg": f"{s.xg[1]:.2f}",
                             "home_finishing": signed(goals_minus_xg[0]), "away_finishing": signed(goals_minus_xg[1]),
                             "home_style": PROFILES[home].style.lower(), "away_style": PROFILES[away].style.lower()}
    lev = room.live.leverage_table()
    if lev:
        facts["top_player"] = room.names.get(lev[0].player_id, lev[0].player_id)
        facts["top_player_leverage"] = f"{lev[0].total:+.2f}"
    nexts = []
    for side, club in (("home", home), ("away", away)):
        nf = next_fixture(club)
        if nf is None:
            continue
        opp, at_home = nf
        ph, pd, pa = pre_match(club, opp) if at_home else pre_match(opp, club)
        win = ph if at_home else pa
        facts |= {f"{side}_next_opponent": clubs[opp].name, f"{side}_next_venue": "at home" if at_home else "away",
                  f"{side}_next_win": pct(win), f"{side}_next_opponent_style": PROFILES[opp].style.lower()}
        nexts.append({"club": club, "opponent": opp, "at_home": at_home, "matchday": CURRENT_MATCHDAY + 1,
                      "forecast": [round(ph, 3), round(pd, 3), round(pa, 3)]})
    truths = {"finished": room.status == "full_time", "score": tuple(s.score)}
    return {"facts": facts, "truths": truths, "decided": decided, "next": nexts}
