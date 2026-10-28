"""Counterfactual leverage. See docs/SPEC.md section 8.

leverage(event) = value(actual outcome) - value(opposite outcome), from the acting team's side,
where value = P(win) + 0.5 * P(draw). Possession is valued with expected threat: holding the ball
at a spot is worth xT(spot) of a goal now plus the current state otherwise.

Credit is shared the way outcomes are earned against expectation, so an average player sums to
about zero and the numbers reward doing better than the model expects:
  shot:      shooter (goal - xG) * swing for shot making, creator xG * swing for creation,
             and on a save or block the stopper gets xG * swing for defending
  pass:      a completed pass earns (1 - P(complete)) * swing for creation
  turnover:  the winner of the ball gets the full swing for defending, the player who lost it
             a share of the loss (P(complete) for a misplaced pass, half for a lost duel)
  red card:  the change in value goes to the player sent off, under turnovers
Scale: 1.0 leverage = 10 points of win value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from engine.models import Side
from engine.pitch import to_attacking
from engine.winprob import GameState, Probs, result_probs, result_value, win_prob
from engine.xt import XTGrid

SCALE = 10.0
SIDES: tuple[Side, Side] = ("home", "away")
CreditKind = Literal["shot_making", "creation", "defending", "turnovers"]


@dataclass(frozen=True)
class Credit:
    player_id: str
    team: Side
    kind: CreditKind
    value: float


@dataclass(frozen=True)
class Leverage:
    action: str
    team: Side
    value: float
    credits: tuple[Credit, ...]
    wp_before: float
    wp_actual: float
    wp_opposite: float


def _mix(a: Probs, b: Probs, p: float) -> Probs:
    return (p * a[0] + (1 - p) * b[0], p * a[1] + (1 - p) * b[1], p * a[2] + (1 - p) * b[2])


class LeverageModel:
    def __init__(self, prior: tuple[float, float], xt: XTGrid) -> None:
        self.prior = prior
        self.xt = xt

    def probs(self, state: GameState) -> Probs:
        return result_probs(self.prior, state)

    def with_ball(self, state: GameState, possessor: int, x: float, y: float) -> Probs:
        """Result probabilities when `possessor` has the ball at (x, y) in pitch coordinates."""
        xa, ya = to_attacking(x, y, SIDES[possessor])
        threat = self.xt.at(xa, ya)
        return _mix(self.probs(state.with_goal(possessor)), self.probs(state), threat)

    def shot(
        self,
        state: GameState,
        team: int,
        xg: float,
        goal: bool,
        shooter: str,
        creator: str | None,
        stopper: str | None,
    ) -> Leverage:
        side, opp = SIDES[team], SIDES[1 - team]
        base = self.probs(state)
        scored = self.probs(state.with_goal(team))
        swing = result_value(scored, team) - result_value(base, team)
        surprise = float(goal) - xg
        credits = [
            Credit(shooter, side, "shot_making", surprise * swing * SCALE),
            Credit(creator or shooter, side, "creation", xg * swing * SCALE),
        ]
        if not goal and stopper:
            swing_def = result_value(base, 1 - team) - result_value(scored, 1 - team)
            credits.append(Credit(stopper, opp, "defending", xg * swing_def * SCALE))
        expected = _mix(scored, base, xg)
        actual, opposite = (scored, base) if goal else (base, scored)
        return Leverage(
            action="shot",
            team=side,
            value=surprise * swing * SCALE,
            credits=tuple(credits),
            wp_before=win_prob(expected, team),
            wp_actual=win_prob(actual, team),
            wp_opposite=win_prob(opposite, team),
        )

    def turnover(
        self,
        state: GameState,
        gainer: int,
        x: float,
        y: float,
        action: str,
        gainer_id: str | None,
        loser_id: str | None,
        loser_share: float,
    ) -> Leverage:
        gained = self.with_ball(state, gainer, x, y)
        kept = self.with_ball(state, 1 - gainer, x, y)
        swing = result_value(gained, gainer) - result_value(kept, gainer)
        credits = []
        if gainer_id:
            credits.append(Credit(gainer_id, SIDES[gainer], "defending", swing * SCALE))
        if loser_id:
            credits.append(Credit(loser_id, SIDES[1 - gainer], "turnovers", -swing * SCALE * loser_share))
        return Leverage(
            action=action,
            team=SIDES[gainer],
            value=swing * SCALE,
            credits=tuple(credits),
            wp_before=win_prob(kept, gainer),
            wp_actual=win_prob(gained, gainer),
            wp_opposite=win_prob(kept, gainer),
        )

    def completed_pass(
        self, state: GameState, team: int, end_x: float, end_y: float, passer: str, p_complete: float
    ) -> Leverage:
        kept = self.with_ball(state, team, end_x, end_y)
        lost = self.with_ball(state, 1 - team, end_x, end_y)
        swing = result_value(kept, team) - result_value(lost, team)
        value = (1.0 - p_complete) * swing * SCALE
        return Leverage(
            action="pass",
            team=SIDES[team],
            value=value,
            credits=(Credit(passer, SIDES[team], "creation", value),),
            wp_before=win_prob(_mix(kept, lost, p_complete), team),
            wp_actual=win_prob(kept, team),
            wp_opposite=win_prob(lost, team),
        )

    def red_card(self, state: GameState, team: int, player: str) -> Leverage:
        before = self.probs(state)
        after = self.probs(state.with_men(team, -1))
        value = (result_value(after, team) - result_value(before, team)) * SCALE
        return Leverage(
            action="red_card",
            team=SIDES[team],
            value=value,
            credits=(Credit(player, SIDES[team], "turnovers", value),),
            wp_before=win_prob(before, team),
            wp_actual=win_prob(after, team),
            wp_opposite=win_prob(before, team),
        )
