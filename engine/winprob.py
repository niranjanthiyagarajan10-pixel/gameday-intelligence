"""Live win probability. See docs/SPEC.md section 8.

lambda_live = w * lambda_prior + (1 - w) * xg_per_90_observed,   w = k / (k + minutes_played)
remaining goals per team ~ Poisson(lambda_live * minutes_left / 90)
P(home win, draw, away win) from the difference of the two Poissons, truncated at 10 goals.

Pre-match rates come from team ratings fitted on a previous simulated season
(data/models/ratings.json), never from the simulator's hidden truth.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

LEAGUE_GOALS_PER_TEAM = 1.35
PRIOR_WEIGHT_K = 30.0
MATCH_MINUTES = 90.0
MAX_GOALS = 10
RED_ATTACK = 0.72  # scoring rate multiplier per missing player
RED_CONCEDE = 1.25  # opponent's scoring rate multiplier per missing player

DEFAULT_RATINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "ratings.json"

_N = np.arange(MAX_GOALS + 1)
_LOG_FACT = np.array([math.lgamma(n + 1) for n in _N])
_DIFF = _N[:, None] - _N[None, :]

Probs = tuple[float, float, float]


@dataclass(frozen=True)
class Ratings:
    """Multiplicative team ratings. Attack above 1 scores more; defence above 1 concedes more."""

    attack: dict[str, float]
    defence: dict[str, float]
    goals_per_team: float = LEAGUE_GOALS_PER_TEAM
    home_edge: float = 1.0  # home scoring multiplier, estimated from data, never assumed

    def prior(self, home: str, away: str) -> tuple[float, float]:
        g = self.goals_per_team
        lam_home = g * self.attack.get(home, 1.0) * self.defence.get(away, 1.0) * self.home_edge
        lam_away = g * self.attack.get(away, 1.0) * self.defence.get(home, 1.0) / self.home_edge
        return lam_home, lam_away

    def to_json(self) -> str:
        return json.dumps(
            {"goals_per_team": round(self.goals_per_team, 4),
             "home_edge": round(self.home_edge, 4),
             "attack": {k: round(v, 4) for k, v in sorted(self.attack.items())},
             "defence": {k: round(v, 4) for k, v in sorted(self.defence.items())}},
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> Ratings:
        d = json.loads(text)
        return cls(attack=d["attack"], defence=d["defence"], goals_per_team=d["goals_per_team"],
                   home_edge=d.get("home_edge", 1.0))

    @classmethod
    def load(cls, path: Path = DEFAULT_RATINGS_PATH) -> Ratings:
        """Fitted ratings if they have been generated, otherwise every club rated league average."""
        if path.exists():
            return cls.from_json(path.read_text(encoding="utf-8"))
        return cls(attack={}, defence={})


@dataclass(frozen=True)
class MatchResult:
    home: str
    away: str
    xg_home: float
    xg_away: float
    goals_home: int
    goals_away: int


def fit_ratings(results: Iterable[MatchResult], xg_weight: float = 0.7, iterations: int = 60) -> Ratings:
    """Iterative proportional fit of attack and defence on a blend of xG and goals (xG is less noisy)."""
    rows = list(results)
    clubs = sorted({r.home for r in rows} | {r.away for r in rows})
    scored = {c: 0.0 for c in clubs}
    conceded = {c: 0.0 for c in clubs}
    games: dict[str, list[tuple[str, bool]]] = {c: [] for c in clubs}
    home_total = away_total = 0.0
    for r in rows:
        h = xg_weight * r.xg_home + (1 - xg_weight) * r.goals_home
        a = xg_weight * r.xg_away + (1 - xg_weight) * r.goals_away
        scored[r.home] += h
        scored[r.away] += a
        conceded[r.home] += a
        conceded[r.away] += h
        games[r.home].append((r.away, True))
        games[r.away].append((r.home, False))
        home_total += h
        away_total += a
    g = (home_total + away_total) / (2 * len(rows))
    edge = math.sqrt(home_total / away_total) if away_total > 0 else 1.0
    attack = {c: 1.0 for c in clubs}
    defence = {c: 1.0 for c in clubs}
    for _ in range(iterations):
        for c in clubs:
            exp = sum(g * defence[o] * (edge if home else 1 / edge) for o, home in games[c])
            attack[c] = scored[c] / exp
        mean = sum(attack.values()) / len(clubs)
        attack = {c: v / mean for c, v in attack.items()}
        for c in clubs:
            exp = sum(g * attack[o] * (1 / edge if home else edge) for o, home in games[c])
            defence[c] = conceded[c] / exp
        mean = sum(defence.values()) / len(clubs)
        defence = {c: v / mean for c, v in defence.items()}
    return Ratings(attack=attack, defence=defence, goals_per_team=g, home_edge=edge)


@dataclass(frozen=True)
class GameState:
    minute: float
    score: tuple[int, int] = (0, 0)
    xg: tuple[float, float] = (0.0, 0.0)
    men: tuple[int, int] = (11, 11)

    def with_goal(self, team: int) -> GameState:
        s = list(self.score)
        s[team] += 1
        return replace(self, score=(s[0], s[1]))

    def with_men(self, team: int, delta: int) -> GameState:
        m = list(self.men)
        m[team] = max(m[team] + delta, 7)
        return replace(self, men=(m[0], m[1]))


LATE_MINUTE = 75.0
DEFAULT_EFFECTS_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "state_effects.json"


@dataclass(frozen=True)
class StateEffects:
    """How the game state changes a team's scoring rate from now on, learned from simulated seasons.

    The defaults are the hand-set starting point; engine/calibrate.py fits them by Poisson regression
    on minute-by-minute xG, the way Lasso learns its game-state effects.
    """

    down_a_man: float = RED_ATTACK  # multiplier per player fewer
    up_a_man: float = RED_CONCEDE  # multiplier per player more
    trailing: float = 1.0
    leading: float = 1.0
    late: float = 1.0  # after the 75th minute
    dispersion: float | None = None  # Negative Binomial size for goals still to come; None = Poisson

    def to_json(self) -> str:
        return json.dumps({k: (None if v is None else round(v, 4)) for k, v in self.__dict__.items()}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> StateEffects:
        return cls(**json.loads(text))

    @classmethod
    def load(cls, path: Path = DEFAULT_EFFECTS_PATH) -> StateEffects:
        return cls.from_json(path.read_text(encoding="utf-8")) if path.exists() else cls()


EFFECTS = StateEffects.load()


def live_rates(prior: tuple[float, float], state: GameState, effects: StateEffects | None = None) -> tuple[float, float]:
    """Scoring rates per 90 minutes from now on, before the late-game effect.

    The blend w * prior + (1 - w) * observed is the posterior mean of a Gamma prior worth k minutes
    of play updated with the xG seen so far, the same update Lasso uses.
    """
    fx = effects or EFFECTS
    minutes = max(state.minute, 0.0)
    w = PRIOR_WEIGHT_K / (PRIOR_WEIGHT_K + minutes)
    rates = []
    for k in range(2):
        observed = state.xg[k] * MATCH_MINUTES / minutes if minutes > 0 else prior[k]
        rate = w * prior[k] + (1 - w) * observed
        men_diff = state.men[k] - state.men[1 - k]
        rate *= fx.down_a_man ** max(-men_diff, 0) * fx.up_a_man ** max(men_diff, 0)
        goal_diff = state.score[k] - state.score[1 - k]
        rate *= fx.trailing if goal_diff < 0 else fx.leading if goal_diff > 0 else 1.0
        rates.append(rate)
    return rates[0], rates[1]


def exposure_left(minute: float, effects: StateEffects | None = None) -> float:
    """Matches' worth of play still to come, with minutes after 75 scaled by the late-game effect."""
    fx = effects or EFFECTS
    before = max(min(LATE_MINUTE, MATCH_MINUTES) - minute, 0.0)
    after = max(MATCH_MINUTES - max(minute, LATE_MINUTE), 0.0)
    return (before + fx.late * after) / MATCH_MINUTES


def goals_pmf(mu: float, dispersion: float | None = None) -> np.ndarray:
    """Distribution of goals still to come: Poisson, or Negative Binomial with the given size."""
    if mu <= 0:
        p = np.zeros(MAX_GOALS + 1)
        p[0] = 1.0
        return p
    if dispersion is None:
        p = np.exp(-mu + _N * math.log(mu) - _LOG_FACT)
    else:
        r = dispersion
        q = r / (r + mu)
        log_p = (
            np.array([math.lgamma(n + r) for n in _N]) - math.lgamma(r) - _LOG_FACT
            + r * math.log(q) + _N * math.log(1.0 - q)
        )
        p = np.exp(log_p)
    return p / p.sum()


def result_probs(prior: tuple[float, float], state: GameState, effects: StateEffects | None = None) -> Probs:
    """(home win, draw, away win) at full time, given the state now."""
    fx = effects or EFFECTS
    left = exposure_left(state.minute, fx)
    lam_h, lam_a = live_rates(prior, state, fx)
    joint = np.outer(goals_pmf(lam_h * left, fx.dispersion), goals_pmf(lam_a * left, fx.dispersion))
    final = _DIFF + (state.score[0] - state.score[1])
    home = float(joint[final > 0].sum())
    draw = float(joint[final == 0].sum())
    return home, draw, max(1.0 - home - draw, 0.0)


def fit_state_effects(rows: list[tuple[float, list[float], float]], ridge: float = 1.0, iterations: int = 40) -> StateEffects:
    """Poisson regression of xG per minute on game state, with the pre-match rate as an offset.

    Each row is (offset = log of the expected xG that minute, [down, up, trailing, leading, late], xG).
    An intercept absorbs any overall scale difference and is not kept.
    """
    offset = np.array([r[0] for r in rows])
    X = np.column_stack([np.ones(len(rows)), np.array([r[1] for r in rows], dtype=float)])
    y = np.array([r[2] for r in rows])
    beta = np.zeros(X.shape[1])
    penalty = ridge * np.eye(X.shape[1])
    penalty[0, 0] = 0.0
    for _ in range(iterations):
        mu = np.exp(offset + X @ beta)
        gradient = X.T @ (y - mu) - penalty @ beta
        hessian = (X * mu[:, None]).T @ X + penalty
        step = np.linalg.solve(hessian, gradient)
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    down, up, trailing, leading, late = (float(math.exp(b)) for b in beta[1:])
    return StateEffects(down_a_man=down, up_a_man=up, trailing=trailing, leading=leading, late=late)


def fit_dispersion(pairs: list[tuple[float, int]], grid: Iterable[float] = (1, 2, 3, 5, 8, 12, 20, 35, 60, 100)) -> float | None:
    """Pick the Negative Binomial size that best explains goals still to come; None if Poisson does best.

    Each pair is (forecast mean of remaining goals, goals actually scored after that point).
    """
    def loglik(r: float | None) -> float:
        return sum(math.log(max(goals_pmf(mu, r)[min(n, MAX_GOALS)], 1e-12)) for mu, n in pairs)

    best: float | None = None
    best_ll = loglik(None)
    for r in grid:
        ll = loglik(float(r))
        if ll > best_ll + 1.0:  # demand real evidence over Poisson, not noise
            best, best_ll = float(r), ll
    return best


def win_prob(probs: Probs, team: int) -> float:
    return probs[0] if team == 0 else probs[2]


def result_value(probs: Probs, team: int) -> float:
    """A win counts 1 and a draw counts a half. Used for leverage so an equaliser gets its due."""
    return win_prob(probs, team) + 0.5 * probs[1]
