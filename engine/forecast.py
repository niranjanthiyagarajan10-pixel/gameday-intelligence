"""Pre-match forecasts from the fitted team ratings: the same Poisson model the live win probability
starts from at kickoff, so the preview and the first live number always agree."""

from __future__ import annotations

from functools import lru_cache

from engine.winprob import GameState, Ratings, result_probs

Probs = tuple[float, float, float]


@lru_cache(maxsize=1)
def _ratings() -> Ratings:
    return Ratings.load()


def pre_match(home: str, away: str) -> Probs:
    """(home win, draw, away win) before kickoff."""
    return result_probs(_ratings().prior(home, away), GameState(minute=0.0))


def expected_goals(home: str, away: str) -> tuple[float, float]:
    """The goals each side is expected to score, from the ratings."""
    return _ratings().prior(home, away)
