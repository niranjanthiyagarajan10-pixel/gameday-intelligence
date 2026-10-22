"""Fit the public models on simulated seasons and report how realistic and accurate they are.

    python -m engine.calibrate

1. Simulates five full seasons (5 x 90 matches, events only) with seeds the live demo never uses.
2. Fits xT, xG (with nearest-defender distance) and team ratings on seasons 1 to 4, from events
   alone, never from the simulator's hidden truth.
3. Scores them on season 5, which the fits never saw: xG against the hand-set prior model, win
   probability against a league-average baseline, and fitted ratings against the hidden strengths.
4. Plays 12 held-out matches with full tracking, half with a red card, and scores shape detection
   against the block each team was really playing. The same matches give the physical metrics.
Writes data/models/{xt,xg,ratings}.json, docs/realism.md and docs/validation.md.
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
from engine.sim import Incident, MatchSimulator, Scenario, SimConfig
from engine.winprob import GameState, MatchResult, Ratings, fit_ratings, result_probs
from engine.xt import DEFAULT_PATH as XT_PATH
from engine.xt import fit_xt

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "data" / "models"
DOCS = ROOT / "docs"
SEASONS = 5
SHAPE_MATCHES = 12
SHAPE_SEED = 900  # held out: the thresholds in engine/shape.py were set on seeds 700 to 711
BLOCK_NAMES = {"high": "high_press", "mid": "mid_block", "low": "low_block"}

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

Played = tuple[str, str, list[MatchEvent]]


# Simulation jobs (module level so worker processes can run them)


def _play(job: tuple[int, str, str, int]) -> Played:
    i, home, away, seed = job
    meta = MatchMeta(match_id=f"c{i:04d}", home=home, away=away, seed=seed)
    events = list(MatchSimulator(meta, build_league(), SimConfig(mode="events_only")).run())
    return home, away, events  # type: ignore[return-value]


def _shape_job(i: int) -> dict:
    """One held-out match with full tracking: shape agreement samples and physical metrics."""
    pairs = [("KR", "AV"), ("CC", "EA"), ("NA", "BF"), ("RU", "TW"), ("WH", "SM"), ("SM", "KR")]
    home, away = pairs[i % len(pairs)]
    scenario = None
    if i % 2:
        scenario = Scenario(name="red card", incidents=[
            Incident(minute=25 + 5 * (i % 6), kind="red_card", team="away", player_number=8)])
    league = build_league()
    meta = MatchMeta(match_id=f"v{i:03d}", home=home, away=away, seed=SHAPE_SEED + i)
    sim = MatchSimulator(meta, league, SimConfig(mode="full"), scenario)
    live = LiveStats(meta, league)
    samples: list[tuple[str, str]] = []
    while not sim.finished:
        for item in sim.step():
            live.push(item)
        if round(sim.t * 5) % 25 == 0:  # every 5 seconds of match time
            for k, side in enumerate(("home", "away")):
                detected = live.shape.teams[side].state
                if detected is not None and sim.state.possession == 1 - k:
                    samples.append((BLOCK_NAMES[sim.state.block[k]], detected))
    keepers = {p.player_id for c in (home, away) for p in league.squads[c] if p.position == "GK"}
    runs = [(r.distance_m, r.top_speed_ms) for pid, r in live.kinematics.runs.items()
            if pid not in keepers and r.distance_m > 5000]
    return {"samples": samples, "runs": runs}


def _run(fn, jobs):
    with ProcessPoolExecutor() as pool:
        return list(pool.map(fn, jobs))


# Features and summaries


def _defender(e: MatchEvent) -> float | None:
    return metrics.nearest_defender(e.x, e.y, e.meta.get("defenders") or [])


def _shot_rows(played: list[Played]) -> list[tuple[MatchEvent, float | None]]:
    return [(e, _defender(e)) for _, _, evs in played for e in evs if e.type == EventType.SHOT]


def _xg(model: metrics.XGModel, e: MatchEvent, defender: float | None) -> float:
    xa, ya = to_attacking(e.x, e.y, e.team)
    return model.prob(xa, ya, e.body_part == "head", e.pressure, defender)


def _summary(home: str, away: str, events: list[MatchEvent], model: metrics.XGModel) -> MatchResult:
    xg = {"home": 0.0, "away": 0.0}
    goals = {"home": 0, "away": 0}
    for e in events:
        if e.type == EventType.SHOT:
            xg[e.team] += _xg(model, e, _defender(e))
        elif e.type == EventType.GOAL:
            goals[e.team] += 1
    return MatchResult(home, away, xg["home"], xg["away"], goals["home"], goals["away"])


def _state_at(events: list[MatchEvent], minute: float, model: metrics.XGModel) -> GameState:
    score, xg, men = [0, 0], [0.0, 0.0], [11, 11]
    for e in events:
        if e.t > minute * 60:
            break
        k = 0 if e.team == "home" else 1
        if e.type == EventType.GOAL:
            score[k] += 1
        elif e.type == EventType.SHOT:
            xg[k] += _xg(model, e, _defender(e))
        elif e.type == EventType.CARD and e.outcome == "red":
            men[k] -= 1
    return GameState(minute=minute, score=(score[0], score[1]), xg=(xg[0], xg[1]), men=(men[0], men[1]))


def _brier3(probs: tuple[float, float, float], outcome: int) -> float:
    return sum((p - (1.0 if i == outcome else 0.0)) ** 2 for i, p in enumerate(probs))


def _xg_scores(model: metrics.XGModel, shots: list[tuple[MatchEvent, float | None]]) -> dict[str, float]:
    p = np.array([_xg(model, e, d) for e, d in shots])
    y = np.array([1.0 if e.outcome == "goal" else 0.0 for e, _ in shots])
    eps = 1e-9
    return {
        "brier": float(np.mean((p - y) ** 2)),
        "log_loss": float(-np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))),
        "predicted": float(p.sum()),
        "goals": float(y.sum()),
    }


def _calibration(model: metrics.XGModel, shots: list[tuple[MatchEvent, float | None]]) -> list[tuple[str, int, float, float]]:
    edges = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
    p = [_xg(model, e, d) for e, d in shots]
    y = [1.0 if e.outcome == "goal" else 0.0 for e, _ in shots]
    table = []
    for lo, hi in zip(edges, edges[1:]):
        idx = [i for i, v in enumerate(p) if lo <= v < hi]
        if idx:
            table.append((f"{lo:.2f} to {hi:.2f}", len(idx), st.mean(p[i] for i in idx), st.mean(y[i] for i in idx)))
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--season-seed", type=int, default=2025)
    args = parser.parse_args()
    league = build_league()
    clubs = list(league.clubs)
    fixtures = list(itertools.permutations(clubs, 2))

    jobs = [
        (s * 1000 + i, h, a, args.season_seed * 10000 + s * 1000 + i)
        for s in range(SEASONS)
        for i, (h, a) in enumerate(fixtures)
    ]
    played = _run(_play, jobs)
    train, test = played[: (SEASONS - 1) * len(fixtures)], played[(SEASONS - 1) * len(fixtures):]

    # Fit on seasons 1 to 4
    MODELS.mkdir(parents=True, exist_ok=True)
    train_events = [e for _, _, evs in train for e in evs]
    XT_PATH.write_text(fit_xt(train_events).to_json(), encoding="utf-8")
    train_shots = _shot_rows(train)
    default_defender = float(np.median([d for _, d in train_shots if d is not None]))
    feats = []
    for e, d in train_shots:
        xa, ya = to_attacking(e.x, e.y, e.team)
        feats.append(metrics.shot_features(xa, ya, e.body_part == "head", e.pressure, d, default_defender))
    xg_model = metrics.fit_xg(feats, [1.0 if e.outcome == "goal" else 0.0 for e, _ in train_shots])
    metrics.XG_PATH.write_text(xg_model.to_json(), encoding="utf-8")
    ratings = fit_ratings(_summary(h, a, evs, xg_model) for h, a, evs in train)
    (MODELS / "ratings.json").write_text(ratings.to_json(), encoding="utf-8")

    # Held-out season 5
    test_shots = _shot_rows(test)
    xg_prior = _xg_scores(metrics.PRIOR_XG, test_shots)
    xg_fitted = _xg_scores(xg_model, test_shots)
    calibration = _calibration(xg_model, test_shots)

    truth_att = [league.clubs[c].truth.attack for c in clubs]
    truth_def = [league.clubs[c].truth.defence for c in clubs]
    corr_att = float(np.corrcoef(truth_att, [ratings.attack[c] for c in clubs])[0, 1])
    corr_def = float(np.corrcoef(truth_def, [-ratings.defence[c] for c in clubs])[0, 1])

    flat = Ratings(attack={}, defence={}, goals_per_team=ratings.goals_per_team, home_edge=ratings.home_edge)
    wp_rows = []
    for minute in (0, 45, 75):
        ours, base = [], []
        for h, a, evs in test:
            final = _state_at(evs, 90.0, xg_model).score
            outcome = 0 if final[0] > final[1] else 1 if final[0] == final[1] else 2
            state = _state_at(evs, minute, xg_model)
            ours.append(_brier3(result_probs(ratings.prior(h, a), state), outcome))
            base.append(_brier3(result_probs(flat.prior(h, a), state), outcome))
        wp_rows.append((minute, st.mean(ours), st.mean(base)))

    # Shape detection and physical metrics on held-out tracked matches
    tracked = _run(_shape_job, range(SHAPE_MATCHES))
    samples = [s for r in tracked for s in r["samples"]]
    runs = [x for r in tracked for x in r["runs"]]

    # Realism on the training seasons
    per_team: dict[str, list[float]] = {k: [] for k in ("shots", "passes", "fouls", "cards")}
    ok = attempts = goals = 0
    for _, _, evs in train:
        c = Counter((e.team, e.type) for e in evs)
        for side in ("home", "away"):
            per_team["shots"].append(c[(side, EventType.SHOT)])
            per_team["passes"].append(c[(side, EventType.PASS)])
            per_team["fouls"].append(c[(side, EventType.FOUL)])
            per_team["cards"].append(c[(side, EventType.CARD)])
        goals += sum(1 for e in evs if e.type == EventType.GOAL)
        attempts += sum(1 for e in evs if e.type == EventType.PASS)
        ok += sum(1 for e in evs if e.type == EventType.PASS and e.outcome == "complete")
    measured = {
        "shots": st.mean(per_team["shots"]),
        "passes": st.mean(per_team["passes"]),
        "pass_completion": ok / attempts,
        "goals_per_match": goals / len(train),
        "xg_per_shot": st.mean(_xg(xg_model, e, d) for e, d in train_shots),
        "fouls": st.mean(per_team["fouls"]),
        "cards": st.mean(per_team["cards"]),
        "distance_km": st.mean(d for d, _ in runs) / 1000,
        "top_speed_kmh": max(s for _, s in runs) * 3.6,
    }

    realism = _realism_md(measured, len(train), SHAPE_MATCHES)
    validation = _validation_md(
        len(train), len(test), len(train_shots), len(test_shots), xg_model, xg_prior, xg_fitted,
        calibration, corr_att, corr_def, wp_rows, samples,
    )
    (DOCS / "realism.md").write_text(realism, encoding="utf-8")
    (DOCS / "validation.md").write_text(validation, encoding="utf-8")
    print(realism)
    print(validation)


# Reports


def _fmt(v: float) -> str:
    return f"{v:.3f}" if v < 1 else f"{v:.1f}"


def _realism_md(m: dict[str, float], n: int, tracked: int) -> str:
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
        f"Generated by `python -m engine.calibrate` from {n} simulated matches (four seasons); "
        f"physical metrics from {tracked} matches with full tracking.",
        "",
        "| Metric | Simulated | Real football target | In range |",
        "|---|---|---|---|",
    ]
    for key, label in labels.items():
        lo, hi = TARGETS[key]
        v = m[key]
        lines.append(f"| {label} | {_fmt(v)} | {lo} to {hi} | {'yes' if lo <= v <= hi else 'no'} |")
    return "\n".join(lines) + "\n"


def _validation_md(n_train, n_test, n_train_shots, n_test_shots, model, prior, fitted, calibration,
                   corr_att, corr_def, wp_rows, samples) -> str:
    labels = ["high_press", "mid_block", "low_block"]
    names = {"high_press": "High press", "mid_block": "Mid block", "low_block": "Low block"}
    confusion = Counter(samples)
    agree = sum(v for (t, d), v in confusion.items() if t == d)
    lines = [
        "# Model validation",
        "",
        f"Generated by `python -m engine.calibrate`. Models are fitted on {n_train} simulated matches "
        f"(seasons 1 to 4) and scored on {n_test} matches they never saw (season 5).",
        "",
        "## Expected goals",
        "",
        f"Fitted by logistic regression on {n_train_shots:,} shots, scored on {n_test_shots:,} held-out shots.",
        "",
        "| Coefficient | Hand-set prior | Fitted |",
        "|---|---|---|",
    ]
    for name in ("intercept", "distance", "angle", "header", "pressure", "defender"):
        lines.append(f"| {name} | {getattr(metrics.PRIOR_XG, name):+.3f} | {getattr(model, name):+.3f} |")
    lines += [
        "",
        "`defender` is per metre to the nearest outfield defender, capped at 8 m.",
        "",
        "| Held-out shots | Hand-set prior | Fitted |",
        "|---|---|---|",
        f"| Brier score (lower is better) | {prior['brier']:.4f} | {fitted['brier']:.4f} |",
        f"| Log loss (lower is better) | {prior['log_loss']:.4f} | {fitted['log_loss']:.4f} |",
        f"| Goals against expected | {prior['goals']:.0f} against {prior['predicted']:.0f} | "
        f"{fitted['goals']:.0f} against {fitted['predicted']:.0f} |",
        "",
        "Calibration of the fitted model on held-out shots:",
        "",
        "| xG band | Shots | Mean xG | Goal rate |",
        "|---|---|---|---|",
    ]
    for band, n, mean_xg, rate in calibration:
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
        "Hidden pressing intensity also creates chances, so ratings fitted from results blend attack and press.",
        "",
        "## Win probability on held-out matches (Brier score, lower is better)",
        "",
        "| Minute | Our model | League-average baseline |",
        "|---|---|---|",
    ]
    for minute, ours, base in wp_rows:
        lines.append(f"| {minute} | {ours:.3f} | {base:.3f} |")
    lines += [
        "",
        "The baseline is the same live model with every club rated league average.",
        "",
        "## Shape detection against the block each team really played",
        "",
        f"{len(samples):,} samples, one every 5 seconds a team was out of possession, from {SHAPE_MATCHES} held-out "
        f"matches with full tracking (half with a red card). Agreement: {agree / len(samples):.1%}.",
        "",
        "| True block | Detected high press | Detected mid block | Detected low block | Recall |",
        "|---|---|---|---|---|",
    ]
    for t in labels:
        row = [confusion[(t, d)] for d in labels]
        total = sum(row)
        recall = f"{confusion[(t, t)] / total:.0%}" if total else "-"
        lines.append(f"| {names[t]} | {row[0]:,} | {row[1]:,} | {row[2]:,} | {recall} |")
    precision = []
    for d in labels:
        col = sum(confusion[(t, d)] for t in labels)
        precision.append(f"{names[d]} {confusion[(d, d)] / col:.0%}" if col else f"{names[d]} -")
    lines += ["", "Precision: " + ", ".join(precision) + ".",
              "Detection waits 60 seconds before confirming a change, so some disagreement right after a switch is expected."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
