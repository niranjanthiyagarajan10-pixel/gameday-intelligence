"""Fit the public models on a simulated "previous season" and report how realistic and accurate they are.

    python -m engine.calibrate

1. Simulates a full double round robin (90 matches, events only) with seeds the live demo never uses.
2. Fits the xT grid and team ratings from those events alone, never from the hidden truth.
3. Checks the fitted ratings against the hidden team strengths.
4. Simulates a held-out set of matches and scores win probability at kickoff, half time and 75
   minutes against a league-average baseline (Brier score, lower is better).
5. Plays two matches with full tracking for physical metrics.
Writes data/models/xt.json, data/models/ratings.json, docs/realism.md and docs/validation.md.
"""

from __future__ import annotations

import argparse
import itertools
import statistics as st
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from engine import metrics
from engine.league import build_league
from engine.live import LiveStats
from engine.models import EventType, MatchEvent, MatchMeta
from engine.pitch import to_attacking
from engine.sim import MatchSimulator, SimConfig
from engine.winprob import GameState, MatchResult, Ratings, fit_ratings, result_probs
from engine.xt import DEFAULT_PATH as XT_PATH
from engine.xt import fit_xt

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "data" / "models"
DOCS = ROOT / "docs"

TARGETS = {
    "shots": (10, 14),
    "passes": (400, 500),
    "pass_completion": (0.80, 0.85),
    "goals_per_match": (2.5, 3.0),
    "xg_per_shot": (0.09, 0.13),
    "fouls": (9, 13),
    "cards": (1.5, 2.5),
    "distance_km": (9.5, 11.5),
    "top_speed_kmh": (31, 36),
}


def _play(job: tuple[int, str, str, int]) -> tuple[str, str, list[MatchEvent]]:
    i, home, away, seed = job
    meta = MatchMeta(match_id=f"c{i:03d}", home=home, away=away, seed=seed)
    events = [e for e in MatchSimulator(meta, build_league(), SimConfig(mode="events_only")).run()]
    return home, away, events  # type: ignore[return-value]


def _xg(e: MatchEvent) -> float:
    xa, ya = to_attacking(e.x, e.y, e.team)
    return metrics.xg(xa, ya, e.body_part == "head", e.pressure)


def _summary(home: str, away: str, events: list[MatchEvent]) -> MatchResult:
    xg = {"home": 0.0, "away": 0.0}
    goals = {"home": 0, "away": 0}
    for e in events:
        if e.type == EventType.SHOT:
            xg[e.team] += _xg(e)
        elif e.type == EventType.GOAL:
            goals[e.team] += 1
    return MatchResult(home, away, xg["home"], xg["away"], goals["home"], goals["away"])


def _state_at(events: list[MatchEvent], minute: float) -> GameState:
    score, xg, men = [0, 0], [0.0, 0.0], [11, 11]
    for e in events:
        if e.t > minute * 60:
            break
        k = 0 if e.team == "home" else 1
        if e.type == EventType.GOAL:
            score[k] += 1
        elif e.type == EventType.SHOT:
            xg[k] += _xg(e)
        elif e.type == EventType.CARD and e.outcome == "red":
            men[k] -= 1
    return GameState(minute=minute, score=(score[0], score[1]), xg=(xg[0], xg[1]), men=(men[0], men[1]))


def _brier(probs: tuple[float, float, float], outcome: int) -> float:
    return sum((p - (1.0 if i == outcome else 0.0)) ** 2 for i, p in enumerate(probs))


def _run(jobs: list[tuple[int, str, str, int]]) -> list[tuple[str, str, list[MatchEvent]]]:
    with ProcessPoolExecutor() as pool:
        return list(pool.map(_play, jobs))


def _fmt(v: float) -> str:
    return f"{v:.3f}" if v < 1 else f"{v:.1f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--season-seed", type=int, default=2025)
    parser.add_argument("--test-matches", type=int, default=60)
    args = parser.parse_args()
    league = build_league()
    clubs = list(league.clubs)

    fixtures = list(itertools.permutations(clubs, 2))
    season = _run([(i, h, a, args.season_seed * 1000 + i) for i, (h, a) in enumerate(fixtures)])
    all_events = [e for _, _, evs in season for e in evs]

    MODELS.mkdir(parents=True, exist_ok=True)
    xt = fit_xt(all_events)
    XT_PATH.write_text(xt.to_json(), encoding="utf-8")
    ratings = fit_ratings(_summary(h, a, evs) for h, a, evs in season)
    (MODELS / "ratings.json").write_text(ratings.to_json(), encoding="utf-8")

    # Realism, per team per match
    per_team: dict[str, list[float]] = {k: [] for k in ("shots", "passes", "fouls", "cards")}
    completion_ok = completion_all = goals = 0
    shot_xg: list[float] = []
    for _, _, evs in season:
        c = Counter((e.team, e.type) for e in evs)
        for side in ("home", "away"):
            per_team["shots"].append(c[(side, EventType.SHOT)])
            per_team["passes"].append(c[(side, EventType.PASS)])
            per_team["fouls"].append(c[(side, EventType.FOUL)])
            per_team["cards"].append(c[(side, EventType.CARD)])
        goals += sum(1 for e in evs if e.type == EventType.GOAL)
        completion_all += sum(1 for e in evs if e.type == EventType.PASS)
        completion_ok += sum(1 for e in evs if e.type == EventType.PASS and e.outcome == "complete")
        shot_xg += [_xg(e) for e in evs if e.type == EventType.SHOT]

    physical = _physical(league)
    measured = {
        "shots": st.mean(per_team["shots"]),
        "passes": st.mean(per_team["passes"]),
        "pass_completion": completion_ok / completion_all,
        "goals_per_match": goals / len(season),
        "xg_per_shot": st.mean(shot_xg),
        "fouls": st.mean(per_team["fouls"]),
        "cards": st.mean(per_team["cards"]),
        **physical,
    }
    realism = _realism_md(measured, len(season))
    (DOCS / "realism.md").write_text(realism, encoding="utf-8")

    # xG calibration on the season's shots
    goals_flags = [1.0 if e.outcome == "goal" else 0.0 for _, _, evs in season for e in evs if e.type == EventType.SHOT]
    xg_table = _calibration(shot_xg, goals_flags)

    # Ratings against hidden truth
    truth_att = [league.clubs[c].truth.attack for c in clubs]
    truth_def = [league.clubs[c].truth.defence for c in clubs]
    fit_att = [ratings.attack[c] for c in clubs]
    fit_def = [ratings.defence[c] for c in clubs]
    corr_att = float(np.corrcoef(truth_att, fit_att)[0, 1])
    corr_def = float(np.corrcoef(truth_def, [-d for d in fit_def])[0, 1])

    # Held-out win probability
    test_fixtures = [fixtures[i % len(fixtures)] for i in range(args.test_matches)]
    test = _run([(500 + i, h, a, (args.season_seed + 1) * 1000 + i) for i, (h, a) in enumerate(test_fixtures)])
    flat = Ratings(attack={}, defence={})
    rows = []
    for minute in (0, 45, 75):
        model_b, base_b = [], []
        for h, a, evs in test:
            final = _state_at(evs, 90.0).score
            outcome = 0 if final[0] > final[1] else 1 if final[0] == final[1] else 2
            state = _state_at(evs, minute)
            model_b.append(_brier(result_probs(ratings.prior(h, a), state), outcome))
            base_b.append(_brier(result_probs(flat.prior(h, a), state if minute else GameState(0)), outcome))
        rows.append((minute, st.mean(model_b), st.mean(base_b)))

    validation = _validation_md(xg_table, corr_att, corr_def, rows, len(season), len(test))
    (DOCS / "validation.md").write_text(validation, encoding="utf-8")
    print(realism)
    print(validation)


def _physical(league) -> dict[str, float]:
    distances, tops = [], []
    keepers = {p.player_id for s in league.squads.values() for p in s if p.position == "GK"}
    for i, (h, a) in enumerate((("KR", "AV"), ("NA", "CC"))):
        meta = MatchMeta(match_id=f"p{i}", home=h, away=a, seed=900 + i)
        live = LiveStats(meta, league)
        for item in MatchSimulator(meta, league, SimConfig(mode="full")).run():
            live.push(item)
        for pid, run in live.kinematics.runs.items():
            if pid not in keepers and run.distance_m > 5000:  # starters and long-serving subs
                distances.append(run.distance_m / 1000)
                tops.append(run.top_speed_ms * 3.6)
    return {"distance_km": st.mean(distances), "top_speed_kmh": max(tops)}


def _calibration(xg: list[float], goals: list[float]) -> list[tuple[str, int, float, float]]:
    edges = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
    table = []
    for lo, hi in zip(edges, edges[1:]):
        idx = [i for i, v in enumerate(xg) if lo <= v < hi]
        if idx:
            table.append((f"{lo:.2f} to {hi:.2f}", len(idx), st.mean(xg[i] for i in idx), st.mean(goals[i] for i in idx)))
    return table


def _realism_md(m: dict[str, float], n: int) -> str:
    labels = {
        "shots": "Shots per team",
        "passes": "Passes per team",
        "pass_completion": "Pass completion",
        "goals_per_match": "Goals per match",
        "xg_per_shot": "xG per shot",
        "fouls": "Fouls per team",
        "cards": "Cards per team",
        "distance_km": "Distance per outfield player (km)",
        "top_speed_kmh": "Top speed in a match (km/h)",
    }
    lines = [
        "# Simulator realism",
        "",
        f"Generated by `python -m engine.calibrate` from {n} simulated matches (physical metrics from 2 matches with full tracking).",
        "",
        "| Metric | Simulated | Real football target | In range |",
        "|---|---|---|---|",
    ]
    for key, label in labels.items():
        lo, hi = TARGETS[key]
        v = m[key]
        lines.append(f"| {label} | {_fmt(v)} | {lo} to {hi} | {'yes' if lo <= v <= hi else 'no'} |")
    return "\n".join(lines) + "\n"


def _validation_md(xg_table, corr_att, corr_def, rows, n_season, n_test) -> str:
    lines = [
        "# Model validation",
        "",
        f"Generated by `python -m engine.calibrate`. Models are fitted on {n_season} simulated matches and "
        f"win probability is scored on {n_test} held-out matches.",
        "",
        "## xG calibration (season shots)",
        "",
        "| xG band | Shots | Mean xG | Goal rate |",
        "|---|---|---|---|",
    ]
    for band, n, mean_xg, rate in xg_table:
        lines.append(f"| {band} | {n} | {mean_xg:.3f} | {rate:.3f} |")
    lines += [
        "",
        "## Fitted team ratings against hidden truth",
        "",
        "| Rating | Correlation with hidden strength |",
        "|---|---|",
        f"| Attack | {corr_att:.2f} |",
        f"| Defence | {corr_def:.2f} |",
        "",
        "## Win probability on held-out matches (Brier score, lower is better)",
        "",
        "| Minute | Our model | League-average baseline |",
        "|---|---|---|",
    ]
    for minute, model, base in rows:
        lines.append(f"| {minute} | {model:.3f} | {base:.3f} |")
    lines += [
        "",
        "The baseline uses the same live Poisson model with every club rated league average. "
        "At kickoff it knows nothing about the teams; later it also sees the score and xG.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
