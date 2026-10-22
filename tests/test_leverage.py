import pytest

from engine.leverage import SCALE, LeverageModel
from engine.winprob import GameState, result_probs, result_value
from engine.xt import fallback_xt

MODEL = LeverageModel((1.35, 1.35), fallback_xt())
STATE = GameState(minute=60, score=(0, 0), xg=(0.8, 0.8))


def swing(state=STATE, team=0):
    base = result_probs(MODEL.prior, state)
    scored = result_probs(MODEL.prior, state.with_goal(team))
    return result_value(scored, team) - result_value(base, team)


def test_goal_credits_shooter_and_creator_by_expectation():
    lev = MODEL.shot(STATE, 0, xg=0.2, goal=True, shooter="KR09", creator="KR10", stopper=None)
    credits = {c.player_id: c for c in lev.credits}
    assert lev.value == pytest.approx(0.8 * swing() * SCALE)
    assert credits["KR09"].kind == "shot_making" and credits["KR09"].value == pytest.approx(0.8 * swing() * SCALE)
    assert credits["KR10"].kind == "creation" and credits["KR10"].value == pytest.approx(0.2 * swing() * SCALE)
    assert lev.wp_actual > lev.wp_before > lev.wp_opposite


def test_missed_big_chance_is_negative_and_keeper_is_credited():
    lev = MODEL.shot(STATE, 0, xg=0.6, goal=False, shooter="KR09", creator="KR10", stopper="AV01")
    credits = {c.player_id: c.value for c in lev.credits}
    assert lev.value < 0
    assert credits["KR09"] + credits["KR10"] == pytest.approx(0.0, abs=1e-9)
    assert credits["AV01"] > 0


def test_self_created_shot_gives_creation_to_shooter():
    lev = MODEL.shot(STATE, 0, xg=0.1, goal=True, shooter="KR09", creator=None, stopper=None)
    assert {c.player_id for c in lev.credits} == {"KR09"}


def test_winning_the_ball_in_your_own_box_matters_more_than_in_midfield():
    deep = MODEL.turnover(STATE, 0, 8.0, 34.0, "tackle", "KR04", "AV09", 0.5)
    midfield = MODEL.turnover(STATE, 0, 52.0, 34.0, "tackle", "KR04", "AV09", 0.5)
    assert deep.value > midfield.value > 0
    credits = {c.player_id: c for c in deep.credits}
    assert credits["KR04"].kind == "defending"
    assert credits["AV09"].kind == "turnovers" and credits["AV09"].value == pytest.approx(-0.5 * deep.value)


def test_harder_completed_passes_earn_more():
    easy = MODEL.completed_pass(STATE, 0, 90.0, 34.0, "KR10", p_complete=0.95)
    hard = MODEL.completed_pass(STATE, 0, 90.0, 34.0, "KR10", p_complete=0.40)
    assert hard.value > easy.value > 0


def test_red_card_costs_the_team():
    lev = MODEL.red_card(STATE, 1, "AV08")
    assert lev.value < 0
    assert lev.credits[0].kind == "turnovers"


def test_equaliser_late_is_a_big_swing():
    late_down = GameState(minute=85, score=(0, 1), xg=(1.0, 1.0))
    lev = MODEL.shot(late_down, 0, xg=0.1, goal=True, shooter="KR09", creator=None, stopper=None)
    assert lev.value > 3.0
