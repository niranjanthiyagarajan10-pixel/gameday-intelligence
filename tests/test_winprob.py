import numpy as np
import pytest

from engine.rng import SeedTree
from engine.winprob import GameState, MatchResult, Ratings, fit_ratings, live_rates, result_probs, result_value

EVEN = (1.35, 1.35)


def test_probabilities_sum_to_one_and_even_teams_are_symmetric():
    p = result_probs(EVEN, GameState(minute=0))
    assert sum(p) == pytest.approx(1.0)
    assert p[0] == pytest.approx(p[2])


def test_full_time_result_is_certain():
    assert result_probs(EVEN, GameState(minute=90, score=(1, 0))) == pytest.approx((1.0, 0.0, 0.0))
    assert result_probs(EVEN, GameState(minute=90, score=(2, 2)))[1] == pytest.approx(1.0)


def test_goals_and_red_cards_move_the_needle():
    base = result_probs(EVEN, GameState(minute=30))
    assert result_probs(EVEN, GameState(minute=30, score=(1, 0)))[0] > base[0]
    assert result_probs(EVEN, GameState(minute=30, men=(10, 11)))[0] < base[0]


def test_late_lead_is_worth_more_than_early_lead():
    early = result_probs(EVEN, GameState(minute=10, score=(1, 0)))[0]
    late = result_probs(EVEN, GameState(minute=85, score=(1, 0)))[0]
    assert late > early


def test_live_rates_move_from_prior_to_observed_xg():
    prior = (1.0, 1.0)
    assert live_rates(prior, GameState(minute=0)) == prior
    late = live_rates(prior, GameState(minute=80, xg=(3.0, 0.2)))
    assert late[0] > 2.0 and late[1] < 0.6


def test_result_value_counts_draws_as_half():
    assert result_value((0.2, 0.6, 0.2), 0) == pytest.approx(0.5)


def test_fit_ratings_recovers_known_strengths():
    gen = SeedTree(3).generator("ratings-test")
    true_attack = {"A": 1.5, "B": 1.0, "C": 0.6}
    results = []
    for _ in range(40):
        for h in true_attack:
            for a in true_attack:
                if h == a:
                    continue
                xh, xa = 1.35 * true_attack[h], 1.35 * true_attack[a]
                results.append(MatchResult(h, a, xh, xa, int(gen.poisson(xh)), int(gen.poisson(xa))))
    r = fit_ratings(results)
    assert r.attack["A"] > r.attack["B"] > r.attack["C"]
    assert np.mean(list(r.attack.values())) == pytest.approx(1.0)


def test_ratings_round_trip_and_default():
    r = Ratings(attack={"KR": 1.2}, defence={"KR": 0.9}, goals_per_team=1.4, home_edge=1.05)
    assert Ratings.from_json(r.to_json()) == r
    # With no fitted ratings every club is league average and home advantage is not assumed.
    home, away = Ratings(attack={}, defence={}).prior("X", "Y")
    assert home == away == pytest.approx(1.35)
    # A fitted home edge favours the home side.
    home, away = r.prior("X", "Y")
    assert home > away
