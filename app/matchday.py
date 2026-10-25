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
EARLY_MINUTE = 20  # "early" in a match story means inside the first twenty minutes


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


# Facts about one match, from the live engine: shared by Catch me up (live) and the Newsdesk (full time)


def _threat_share(live: Any, k: int, since_minute: int) -> float | None:
    rows = live.by_minute[since_minute:]
    total = sum(b.xt[0] + b.xt[1] for b in rows)
    return None if total <= 0 else sum(b.xt[k] for b in rows) / total


def match_facts(live: Any, names: dict[str, str], teams: dict[str, str], finished: bool,
                derby: bool = False, forecast: tuple[float, float, float] | None = None) -> dict[str, Any]:
    """Facts (slot to formatted value) and the truths the wording checks need, for one match so far."""
    from engine.spells import best_spells

    s = live.stats()
    home, away = teams["home"], teams["away"]
    minute = int(s.t // 60)
    facts: dict[str, str] = {
        "home": home, "away": away, "score": f"{s.score[0]}-{s.score[1]}",
        "home_goals": str(s.score[0]), "away_goals": str(s.score[1]), "minute": f"{minute}'",
        "home_xg": f"{s.xg[0]:.2f}", "away_xg": f"{s.xg[1]:.2f}",
        "home_possession": pct(s.possession[0]), "away_possession": pct(s.possession[1]),
        "home_win": pct(s.win_prob[0]), "draw": pct(s.win_prob[1]), "away_win": pct(s.win_prob[2]),
    }
    shots = [sum(1 for x in live.shots if x.team == side) for side in ("home", "away")]
    facts |= {"home_shots": str(shots[0]), "away_shots": str(shots[1])}
    lead = 0 if s.score[0] > s.score[1] else 1 if s.score[1] > s.score[0] else None
    if lead is not None:
        facts |= {"leader": (home, away)[lead], "trailer": (away, home)[lead]}
    # Goals in order, with the running score after each, so comebacks and late winners can be checked.
    running = [0, 0]
    trailed = {"home": False, "away": False}
    scorers: dict[str, int] = {}
    goals = []
    for i, shot in enumerate(x for x in live.shots if x.outcome == "goal"):
        k = 0 if shot.team == "home" else 1
        running[k] += 1
        n = i + 1
        facts |= {f"goal_{n}_player": names.get(shot.player_id, shot.player_id), f"goal_{n}_minute": f"{shot.minute}'",
                  f"goal_{n}_team": (home, away)[k], f"goal_{n}_xg": f"{shot.xg:.2f}",
                  f"goal_{n}_score": f"{running[0]}-{running[1]}"}
        scorers[shot.player_id] = scorers.get(shot.player_id, 0) + 1
        trailed["home"] |= running[0] < running[1]
        trailed["away"] |= running[1] < running[0]
        goals.append({"minute": shot.minute, "team": shot.team, "player": names.get(shot.player_id, shot.player_id),
                      "xg": round(shot.xg, 2), "score": f"{running[0]}-{running[1]}"})
    for i, (side, pid) in enumerate(live.sent_off):
        facts |= {f"red_{i + 1}_player": names.get(pid, pid), f"red_{i + 1}_team": teams[side]}
    if live.men[0] < 11 or live.men[1] < 11:
        facts |= {"home_men": str(live.men[0]), "away_men": str(live.men[1])}
    lev = live.leverage_table()
    if lev:
        facts |= {"top_player": names.get(lev[0].player_id, lev[0].player_id), "top_player_team": teams[lev[0].team],
                  "top_player_leverage": f"{lev[0].total:+.2f}"}
    recent: dict[str, Any] = {}
    if minute >= 10:
        k = 0 if (_threat_share(live, 0, minute - 10) or 0) >= 0.5 else 1
        share = _threat_share(live, k, minute - 10)
        if share is not None:
            facts |= {"last10_team": (home, away)[k], "last10_share": pct(share)}
            recent = {"team": k, "share": share}
    spells = best_spells(live.by_minute)
    spell = max((sp for sp in spells.values() if sp), key=lambda sp: sp.share, default=None)
    if spell:
        facts |= {"spell_team": teams[spell.team], "spell_start": f"{spell.start}'", "spell_end": f"{spell.end}'",
                  "spell_share": pct(spell.share), "spell_goals": str(spell.goals)}
    last = goals[-1] if goals else None
    winner = None if lead is None else ("home", "away")[lead]
    truths = {
        "finished": finished, "score": [s.score[0], s.score[1]], "leader": winner, "derby": derby,
        "reds": len(live.sent_off), "men": [live.men[0], live.men[1]],
        "early_red": any(m <= EARLY_MINUTE for m in getattr(live, "red_minutes", [])),
        "early_goal": bool(goals) and goals[0]["minute"] <= EARLY_MINUTE,
        "comeback": bool(winner and trailed[winner]) or (lead is None and any(trailed.values()) and sum(s.score) > 0),
        "late_winner": bool(finished and winner and last and last["minute"] >= 80 and last["team"] == winner
                            and abs(s.score[0] - s.score[1]) == 1),
        "hat_trick": any(v >= 3 for v in scorers.values()),
        "clean_sheet": s.score[0] == 0 or s.score[1] == 0,
        "dominant": bool(spell) or bool(recent and recent["share"] >= 0.6),
        "upset": bool(finished and winner and forecast and forecast[0 if winner == "home" else 2] < max(forecast[0], forecast[2])),
    }
    return {"facts": facts, "truths": truths, "goals": goals,
            "stats": {"xg": [round(s.xg[0], 2), round(s.xg[1], 2)], "shots": shots,
                      "possession": [round(s.possession[0], 3), round(s.possession[1], 3)],
                      "win_prob": [round(p, 3) for p in s.win_prob], "men": [live.men[0], live.men[1]],
                      "top_player": facts.get("top_player"), "top_player_leverage": facts.get("top_player_leverage"),
                      "spell": None if not spell else {"team": spell.team, "start": spell.start, "end": spell.end,
                                                       "share": round(spell.share, 3)}}}


# The In-depth Analyst: the last fifteen minutes against the fifteen before, and why


def _window(live: Any, k: int, start: int, end: int) -> dict[str, float] | None:
    rows = live.by_minute[max(start, 0):end]
    total = sum(b.xt[0] + b.xt[1] for b in rows)
    if not rows:
        return None
    return {"share": (sum(b.xt[k] for b in rows) / total) if total > 0 else 0.5,
            "xg": sum(b.xg[k] for b in rows), "shots": sum(b.shots[k] for b in rows)}


def deep_facts(live: Any, names: dict[str, str], teams: dict[str, str], derby: bool = False) -> dict[str, Any]:
    """Facts for an in-depth card: threat, chances and shots in the last fifteen minutes and the fifteen
    before, each team's defensive shape now, and the player pulling defenders around."""
    from agents.fallback import SHAPES
    from app.blueprint import MIN_GRAVITY_FRAMES

    base = match_facts(live, names, teams, False, derby)
    # Only what this card is about. Numbers about other things (the leverage leader, the best spell, each
    # goal) were borrowed by the model and pinned on the wrong player or the wrong measure in live runs.
    facts = {k: v for k, v in base["facts"].items()
             if not k.startswith(("top_player", "spell_", "goal_", "last10_", "red_"))}
    truths = dict(base["truths"])
    minute = int(live.t // 60)
    start = max(minute - 15, 0)
    facts |= {"window_start": f"{start}'", "window_end": f"{minute}'"}
    rising = None
    for k, side in enumerate(("home", "away")):
        now = _window(live, k, start, minute)
        before = _window(live, k, start - 15, start) if start >= 15 else None
        if now:
            facts |= {f"{side}_threat_now": pct(now["share"]), f"{side}_xg_now": f"{now['xg']:.2f}",
                      f"{side}_shots_now": str(now["shots"])}
            truths[f"{side}_share_now"] = now["share"]
        if before:
            facts[f"{side}_threat_before"] = pct(before["share"])
            if now and now["share"] - before["share"] >= 0.15:
                rising = side
        tracker = live.shape.teams[side]
        w = live.shape.window(side)
        if tracker.state and w:
            facts |= {f"{side}_shape": SHAPES.get(tracker.state, tracker.state), f"{side}_line": f"{w[0]:.0f} m",
                      f"{side}_compactness": f"{w[1]:.0f} sq m", f"{side}_pressers": f"{w[2]:.1f}"}
        truths[f"{side}_shape"] = tracker.state
    truths["rising"] = rising
    truths["dominant"] = any(truths.get(f"{s}_share_now", 0) >= 0.6 for s in ("home", "away"))
    best = None
    for pid, row in live.gravity.rows.items():
        if row.total_frames >= MIN_GRAVITY_FRAMES and row.overall is not None and (best is None or row.overall > best[1]):
            best = (pid, row.overall)
    if best:
        side = live.gravity.teams.get(best[0])
        facts |= {"gravity_player": names.get(best[0], best[0]), "gravity_value": f"{best[1]:+.1f}",
                  "gravity_team": teams.get(side, "") if side else ""}
    # Threat share in five-minute buckets over the last half hour, for the card's chart.
    chart = []
    for b0 in range(max(minute - 30, 0) // 5 * 5, minute, 5):
        rows = live.by_minute[b0:min(b0 + 5, minute)]
        total = sum(r.xt[0] + r.xt[1] for r in rows)
        chart.append({"start": b0, "home": round(sum(r.xt[0] for r in rows) / total, 3) if total > 0 else 0.5})
    return {"facts": facts, "truths": truths, "chart": chart, "minute": minute}
