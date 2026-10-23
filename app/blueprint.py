"""The Match Blueprint: a one-page story of a match, adapted from the NBA Inside the Game Blueprint.

Overview, highlights, top performers, shot difficulty, gravity, marking and leverage spotlights.
Every number comes from the live engine; every sentence is a word-only template from
`agents/report.py` with slots filled here.
"""

from __future__ import annotations

from typing import Any

from agents.report import GRAVITY_CATEGORIES, HOW_SCORED, LEVERAGE_PARTS, MISS_WORDS, REPORT, count, say
from app.payloads import shot_dict
from engine.gravity import CATEGORIES, GravityRow
from engine.live import LiveStats, ShotRecord
from engine.models import Side
from engine.spells import best_spells

SIDES: tuple[Side, Side] = ("home", "away")
HIGHLIGHTS = 5
HIGHLIGHT_XG = 0.25  # misses at least this good make the reel
MIN_GRAVITY_FRAMES = 1500  # five minutes measured with the ball before a player's gravity is shown
MIN_MARKING_S = 180.0
MIN_CATEGORY_FRAMES = 25
MEN_WORDS = {10: "ten", 9: "nine", 8: "eight", 7: "seven"}


def _fmt_xg(v: float) -> str:
    return f"{v:.2f}"


def _signed(v: float, digits: int = 2) -> str:
    return f"{v:+.{digits}f}"


def _pct(v: float) -> str:
    return f"{round(v * 100)}%"


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


class _Names:
    def __init__(self, roster: dict[str, Any]) -> None:
        self.players = roster["players"]
        self.clubs = roster["clubs"]

    def name(self, pid: str) -> str:
        return self.players.get(pid, {}).get("name", pid)

    def short(self, pid: str) -> str:
        """'R. Okafor', like the NBA's 'C. Braun'."""
        full = self.name(pid)
        first, _, last = full.partition(" ")
        return f"{first[0]}. {last}" if last else full

    def surname(self, pid: str) -> str:
        return self.players.get(pid, {}).get("short", pid)

    def team(self, side: Side) -> str:
        return self.clubs[side]["name"]


def _side_of(live: LiveStats, pid: str) -> Side:
    return "home" if pid.startswith(live.meta.home) else "away"


def _player_shots(live: LiveStats) -> dict[str, list[ShotRecord]]:
    by: dict[str, list[ShotRecord]] = {}
    for s in live.shots:
        by.setdefault(s.player_id, []).append(s)
    return by


# Overview


def _overview(live: LiveStats, n: _Names, finished: bool, gravity: list[dict[str, Any]]) -> dict[str, Any]:
    h, a = live.score
    minute = str(int(live.t // 60))
    score = f"{max(h, a)}-{min(h, a)}" if h != a else f"{h}-{a}"
    home, away = n.team("home"), n.team("away")
    sentences: list[str] = []
    if h == a:
        headline = say("headline_draw", home=home, away=away) if finished else say("headline_level", home=home, away=away, minute=minute)
        sentences.append(say("result_draw", home=home, away=away, score=score) if finished
                         else say("result_level", home=home, away=away, score=score, minute=minute))
    else:
        win, lose = ("home", "away") if h > a else ("away", "home")
        if finished:
            headline = say("headline_win", winner=n.team(win))
            sentences.append(say("result_win", winner=n.team(win), loser=n.team(lose), score=score))
        else:
            headline = say("headline_lead", leader=n.team(win), minute=minute)
            sentences.append(say("result_lead", leader=n.team(win), trailer=n.team(lose), score=score, minute=minute))

    by = _player_shots(live)
    for side in SIDES:
        mine = {p: s for p, s in by.items() if s[0].team == side}
        if not mine:
            continue
        goals = lambda p: sum(1 for s in mine[p] if s.outcome == "goal")  # noqa: E731
        xg = lambda p: sum(s.xg for s in mine[p])  # noqa: E731
        lead = max(mine, key=lambda p: (goals(p), xg(p)))
        if goals(lead):
            sentences.append(say("top_scorer", player=n.name(lead), team=n.team(side), goals=count(goals(lead), "goal"),
                                 shots=count(len(mine[lead]), "shot"), xg=_fmt_xg(xg(lead))))
        else:
            sentences.append(say("top_threat", player=n.name(lead), team=n.team(side),
                                 shots=count(len(mine[lead]), "shot"), xg=_fmt_xg(xg(lead))))

    wasteful = [(sum(s.xg for s in ss) - sum(1 for s in ss if s.outcome == "goal"), p) for p, ss in by.items()]
    wasteful = [w for w in wasteful if w[0] >= 0.6]
    if wasteful:
        _, p = max(wasteful)
        sentences.append(say("wasteful", player=n.name(p), goals=count(sum(1 for s in by[p] if s.outcome == "goal"), "goal"),
                             xg=_fmt_xg(sum(s.xg for s in by[p]))))

    if live.xg[0] != live.xg[1]:
        k = 0 if live.xg[0] > live.xg[1] else 1
        possession = live.timeline.share(0.0, live.t) if live.t > 0 else (0.5, 0.5)
        sentences.append(say("chance_battle", team=n.team(SIDES[k]), xg_for=_fmt_xg(live.xg[k]),
                             xg_against=_fmt_xg(live.xg[1 - k]), possession=_pct(possession[k])))

    spells = [s for s in best_spells(live.by_minute).values() if s is not None]
    if spells:
        top = max(spells, key=lambda s: (s.goals, s.share))
        key = "spell_scored" if top.goals else "spell"
        sentences.append(say(key, team=n.team(top.team), start=str(top.start), end=str(top.end), share=_pct(top.share),
                             shots=count(top.shots, "shot"), goals=count(top.goals, "goal")))

    for k, side in enumerate(SIDES):
        reds = [pid for team, pid in live.sent_off if team == side]
        if reds:
            sentences.append(say("red_card", team=n.team(side), men=MEN_WORDS.get(live.men[k], str(live.men[k])),
                                 player=n.name(reds[0])))

    if gravity:
        g = max(gravity, key=lambda r: r["overall"])
        sentences.append(say("inside_gravity", player=n.name(g["player"]), gravity=f"{g['overall']:.1f}"))
    table = live.leverage_table()
    if table:
        top_lev = max(table, key=lambda r: abs(r.total))
        sentences.append(say("inside_leverage", player=n.name(top_lev.player_id), leverage=_signed(top_lev.total)))

    return {"headline": headline, "text": " ".join(sentences),
            "spells": [{"team": s.team, "start": s.start, "end": s.end, "share": s.share, "shots": s.shots,
                        "goals": s.goals, "xg": s.xg} for s in spells]}


# Highlights


def _highlights(live: LiveStats, n: _Names) -> list[dict[str, Any]]:
    picks = [s for s in live.shots if s.outcome == "goal" or s.xg >= HIGHLIGHT_XG]
    picks = sorted(picks, key=lambda s: (s.outcome != "goal", -abs(s.leverage), s.t))[:HIGHLIGHTS]
    out = []
    for s in sorted(picks, key=lambda s: s.t):
        shot_type = s.shot_type.lower()
        minute = str(s.minute + 1)
        if s.outcome == "goal":
            title = say("title_goal", surname=n.surname(s.player_id), how=HOW_SCORED.get(s.shot_type, ""))
            sub = say("sub_goal", player=n.name(s.player_id), shot_type=shot_type, minute=minute, xg=_fmt_xg(s.xg))
        else:
            key = f"title_{s.outcome}" if f"title_{s.outcome}" in REPORT else "title_off_target"
            title = say(key, surname=n.surname(s.player_id))
            sub = say("sub_miss", player=n.name(s.player_id), shot_type=shot_type,
                      outcome=MISS_WORDS.get(s.outcome, s.outcome), minute=minute, xg=_fmt_xg(s.xg))
        out.append({"event_id": s.event_id, "team": s.team, "player": s.player_id, "title": title.strip().upper(),
                    "subtitle": sub, "minute": s.minute, "xg": s.xg, "outcome": s.outcome})
    return out


# Gravity


def _gravity_value(row: GravityRow, idx: int) -> float | None:
    if row.frames[idx] < MIN_CATEGORY_FRAMES:
        return None
    v = row.mean(idx)
    return None if v is None else round(v, 1)


def _gravity(live: LiveStats, n: _Names) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    players = []
    for pid, row in live.gravity.rows.items():
        if row.total_frames < MIN_GRAVITY_FRAMES or row.overall is None:
            continue
        side = live.gravity.teams[pid]
        parts = {name: _gravity_value(row, i) for i, name in enumerate(CATEGORIES)}
        overall = round(row.overall, 1)
        text = [say("gravity_above" if overall >= 0 else "gravity_below", player=n.name(pid), team=n.team(side),
                    overall=f"{overall:.1f}")]
        shown = {k: v for k, v in parts.items() if v is not None}
        if shown and max(shown.values()) > 0:
            cat = max(shown, key=lambda k: shown[k])
            text.append(say("gravity_focus", category=GRAVITY_CATEGORIES[cat], value=f"{shown[cat]:.1f}"))
        players.append({"player": pid, "team": side, "overall": overall, "frames": row.total_frames,
                        "seconds": round(row.total_frames * 0.2), **parts, "text": " ".join(text)})
    players.sort(key=lambda r: -r["overall"])
    maps = {}
    for side in SIDES:
        m = live.gravity.maps[side]
        maps[side] = {
            "on_sum": [[round(float(v), 1) for v in col] for col in m.on_sum],
            "on_n": [[int(v) for v in col] for col in m.on_n],
            "off_sum": [[round(float(v), 1) for v in col] for col in m.off_sum],
            "off_n": [[int(v) for v in col] for col in m.off_n],
        }
    return players, maps


# Marking


def _marking(live: LiveStats, n: _Names) -> list[dict[str, Any]]:
    """For each defending team: the opponent's main threat and the defender who marked them most."""
    by = _player_shots(live)
    out = []
    for defending in SIDES:
        attacking: Side = "away" if defending == "home" else "home"
        threats = {p: sum(s.xg for s in ss) for p, ss in by.items() if ss[0].team == attacking}
        candidates = sorted(threats, key=lambda p: -threats[p]) or sorted(
            (p for p, side in live.marking.teams.items() if side == attacking and p in live.marking.attacking),
            key=lambda p: -live.marking.attacking[p])
        for attacker in candidates:
            m = live.marking.main_marker(attacker)
            if m is None or m.seconds < MIN_MARKING_S:
                continue
            al = m.allowed
            key = "marking_scored" if al.goals else "marking_held" if al.shots else "marking_no_shot"
            out.append({
                "team": defending, "defender": m.defender, "attacker": attacker,
                "seconds": m.seconds, "defending_s": m.defending_s, "share": m.share,
                "shots": al.shots, "xg": round(al.xg, 3), "goals": al.goals, "received": al.received, "tackles": al.tackles,
                "caption": say("marking_caption", defender=n.short(m.defender), attacker=n.short(attacker),
                               share=_pct(m.share), team=n.team(attacking)),
                "text": say(key, time=_clock(m.seconds), defender=n.name(m.defender), attacker=n.name(attacker),
                            shots=count(al.shots, "shot"), xg=_fmt_xg(al.xg), goals=count(al.goals, "goal"),
                            received=count(al.received, "pass")),
            })
            break
    return out


# Leverage


def _leverage(live: LiveStats, n: _Names) -> list[dict[str, Any]]:
    table = live.leverage_table()
    if not table:
        return []
    best_overall = max(table, key=lambda r: r.total).player_id
    out = []
    for side in SIDES:
        rows = [r for r in table if r.team == side]
        if not rows:
            continue
        r = max(rows, key=lambda r: r.total)
        parts = {"shot_making": r.shot_making, "creation": r.creation, "defending": r.defending, "turnovers": r.turnovers}
        text = [say("leverage_match" if r.player_id == best_overall else "leverage_team", player=n.name(r.player_id),
                    team=n.team(side), total=_signed(r.total))]
        main = max((k for k in parts if k != "turnovers"), key=lambda k: parts[k])
        if parts[main] > 0:
            label, why = LEVERAGE_PARTS[main]
            text.append(say("leverage_part", part=label, value=_signed(parts[main]), why=why))
        if parts["turnovers"] <= -0.3:
            text.append(say("leverage_cost", value=_signed(parts["turnovers"])))
        out.append({"player": r.player_id, "team": side, "total": round(r.total, 3),
                    **{k: round(v, 3) for k, v in parts.items()}, "text": " ".join(text)})
    return out


# Top performers


def _performers(live: LiveStats, gravity: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by = _player_shots(live)
    table = live.leverage_table()
    options: list[tuple[str, str, str, list[tuple[float, str]]]] = [
        ("goals_above_xg", "Goals above xG",
         "Goals scored minus the expected goals of the player's shots. Above zero is finishing better than an average player.",
         [(sum(1 for s in ss if s.outcome == "goal") - sum(s.xg for s in ss), p) for p, ss in by.items()
          if any(s.outcome == "goal" for s in ss)]),
        ("creation", "Creation leverage",
         "Win value created for others with passes and chances. 1.0 is 10 points of win probability.",
         [(r.creation, r.player_id) for r in table]),
        ("defending", "Defensive leverage",
         "Win value from tackles, interceptions, blocks and saves. 1.0 is 10 points of win probability.",
         [(r.defending, r.player_id) for r in table]),
        ("gravity", "Average gravity",
         "Defensive attention drawn above the league average for the same spot and role, from tracking. +100 is one extra defender.",
         [(g["overall"], g["player"]) for g in gravity]),
    ]
    chosen: set[str] = set()
    out = []
    for key, label, info, values in options:
        ranked = sorted(values, reverse=True)
        pick = next((v for v in ranked if v[1] not in chosen), ranked[0] if ranked else None)
        if pick is None:
            continue
        value, pid = pick
        chosen.add(pid)
        shown = f"{value:.1f}" if key == "gravity" else _signed(value)
        out.append({"key": key, "label": label, "info": info, "player": pid, "team": _side_of(live, pid), "value": shown})
    return out


# Shots


def _finishing(live: LiveStats, n: _Names) -> dict[str, str]:
    by = _player_shots(live)
    out = {}
    for side in SIDES:
        mine = {p: ss for p, ss in by.items() if ss[0].team == side}
        if not mine:
            continue
        p = max(mine, key=lambda p: (len(mine[p]), sum(s.xg for s in mine[p])))
        ss = mine[p]
        out[side] = say("finishing", player=n.name(p), team=n.team(side),
                        goals=count(sum(1 for s in ss if s.outcome == "goal"), "goal"), shots=count(len(ss), "shot"),
                        xg=_fmt_xg(sum(s.xg for s in ss)), on_target=str(sum(1 for s in ss if s.outcome in ("goal", "saved"))))
    return out


def build_blueprint(live: LiveStats, roster: dict[str, Any], status: str, half_s: float) -> dict[str, Any]:
    n = _Names(roster)
    finished = status == "full_time"
    gravity_players, gravity_maps = _gravity(live, n)
    shots = []
    running = [0, 0]
    for s in live.shots:
        if s.outcome == "goal":
            running[0 if s.team == "home" else 1] += 1
        shots.append({**shot_dict(s), "half": 1 if s.t < half_s else 2, "score_after": f"{running[0]}-{running[1]}"})
    return {
        "status": status,
        "t": live.t,
        "score": live.score,
        "men": live.men,
        "overview": _overview(live, n, finished, gravity_players),
        "highlights": _highlights(live, n),
        "performers": _performers(live, gravity_players),
        "shots": shots,
        "finishing": _finishing(live, n),
        "gravity": {"players": gravity_players, "maps": gravity_maps, "cell_m": 3.0},
        "marking": _marking(live, n),
        "leverage": _leverage(live, n),
    }
