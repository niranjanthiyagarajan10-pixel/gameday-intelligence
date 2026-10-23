"""Words for the Match Blueprint page: the match overview, highlight titles and spotlight paragraphs.

Like the fallback cards, these templates only hold words. Every number and name is a slot that
`app/blueprint.py` fills from engine state, so the text is correct by construction. In M3 the Recap
agent rewrites the wording from the same slots, and the Verifier checks it against them.
"""

from __future__ import annotations

REPORT: dict[str, str] = {
    # Headlines
    "headline_win": "{winner} earn the win",
    "headline_draw": "{home} and {away} share the points",
    "headline_lead": "{leader} lead after {minute} minutes",
    "headline_level": "{home} and {away} level after {minute} minutes",
    # Overview sentences
    "result_win": "{winner} beat {loser} {score}.",
    "result_draw": "{home} and {away} drew {score}.",
    "result_lead": "{leader} lead {trailer} {score} after {minute} minutes.",
    "result_level": "{home} and {away} are level at {score} after {minute} minutes.",
    "top_scorer": "{player} led {team} with {goals} from {shots} worth {xg} xG.",
    "top_threat": "{player} was the biggest threat for {team}, with {shots} worth {xg} xG.",
    "wasteful": "{player} could not make the chances count, scoring {goals} from {xg} xG.",
    "chance_battle": "{team} won the chance battle by {xg_for} xG to {xg_against}, with {possession} of the ball.",
    "spell": "{team} had their best spell from minute {start} to minute {end}, with {share} of the threat and {shots}.",
    "spell_scored": "{team} had their best spell from minute {start} to minute {end}, with {share} of the threat, {shots} and {goals}.",
    "red_card": "{team} finished with {men} men after a red card for {player}.",
    "inside_gravity": "Inside the game, {player} drew the most attention, with an average gravity of {gravity}.",
    "inside_leverage": "{player} made the biggest difference to the result, with a total leverage of {leverage}.",
    # Highlights
    "title_goal": "{surname} scores {how}",
    "title_saved": "{surname} denied",
    "title_off_target": "{surname} goes close",
    "title_blocked": "{surname} blocked",
    "sub_goal": "{player} scored with a {shot_type} in minute {minute}, a chance worth {xg} xG.",
    "sub_miss": "{player} had a {shot_type} {outcome} in minute {minute}, a chance worth {xg} xG.",
    # Shot difficulty
    "finishing": "{player} of {team} scored {goals} from {shots} worth {xg} xG, with {on_target} on target.",
    # Gravity
    "gravity_above": "{player} drew more defensive attention than usual for {team}, with an average gravity of {overall}.",
    "gravity_below": "{player} drew less defensive attention than usual for {team}, with an average gravity of {overall}.",
    "gravity_focus": "The {category} gravity of {value} shows where defenders paid the most attention.",
    # Marking
    "marking_caption": "{defender} was the nearest defender to {attacker} for {share} of the time {team} had the ball",
    "marking_no_shot": "Across {time} as the nearest defender, {defender} kept {attacker} without a shot. {attacker} received {received} in that time.",
    "marking_held": "Across {time} as the nearest defender, {defender} held {attacker} to {shots} worth {xg} xG, with no goals. {attacker} received {received} in that time.",
    "marking_scored": "Across {time} as the nearest defender, {defender} saw {attacker} take {shots} worth {xg} xG and score {goals}. {attacker} received {received} in that time.",
    # Leverage
    "leverage_match": "{player} posted a total leverage of {total} for {team}, the highest in the match.",
    "leverage_team": "{player} led {team} with a total leverage of {total}.",
    "leverage_part": "{part} leverage of {value} was the biggest part, {why}.",
    "leverage_cost": "Turnovers cost {value}.",
}

HOW_SCORED = {
    "Header from a cross": "with a header",
    "Header": "with a header",
    "Close-range finish": "from close range",
    "Long shot": "from distance",
    "First-time shot": "first time",
    "Shot after a pass": "from a pass",
    "Shot after a dribble": "after a dribble",
}

MISS_WORDS = {"saved": "saved", "off_target": "go wide", "blocked": "blocked"}

LEVERAGE_PARTS = {
    "shot_making": ("Shot making", "from finishing chances against their xG"),
    "creation": ("Creation", "from passes and chances made for others"),
    "defending": ("Defensive", "from tackles, interceptions and saves"),
    "turnovers": ("Turnover", "from winning or losing the ball"),
}

GRAVITY_CATEGORIES = {
    "build_up_off_ball": "build-up off-ball",
    "final_third_off_ball": "final third off-ball",
    "build_up_on_ball": "build-up on-ball",
    "final_third_on_ball": "final third on-ball",
}


def say(key: str, **slots: str) -> str:
    return REPORT[key].format(**slots)


def count(n: int, word: str) -> str:
    """'1 shot', '3 shots', '2 passes'."""
    if n == 1:
        return f"{n} {word}"
    return f"{n} {word}es" if word.endswith("s") else f"{n} {word}s"
