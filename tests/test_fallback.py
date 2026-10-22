import re

import pytest

from agents.fallback import TEMPLATES, fallback_cue, hero_for, template_key
from engine.models import Moment, OverlayEvent

NAMES = {"KR10": "Rafael Okafor", "AV08": "Callum Hale"}
TEAMS = {"home": "Kingsport Rovers", "away": "Ashford Vale"}

MOMENTS = [
    Moment(moment_id="m-mo-01", minute=12, kind="goal", leverage=2.1, team="home", players=["KR10"],
           evidence={"xg": 0.31, "player": "KR10", "score": "1-0", "wp_before": 0.45, "wp_after": 0.68, "leverage": 2.1},
           state_ref="m@720.0"),
    Moment(moment_id="m-mo-02", minute=30, kind="low_xg_goal", leverage=2.4, team="away", players=["AV08"],
           evidence={"xg": 0.04, "player": "AV08", "score": "1-1", "wp_before": 0.2, "wp_after": 0.38, "leverage": 2.4},
           state_ref="m@1800.0"),
    Moment(moment_id="m-mo-03", minute=55, kind="red_card", leverage=-1.1, team="away", players=["AV08"],
           evidence={"player": "AV08", "wp_before": 0.3, "wp_after": 0.19, "leverage": -1.1}, state_ref="m@3300.0"),
    Moment(moment_id="m-mo-04", minute=60, kind="big_chance", leverage=-0.4, team="home", players=["KR10"],
           evidence={"xg": 0.42, "player": "KR10", "outcome": "saved", "wp_if_scored": 0.81, "leverage": -0.4},
           state_ref="m@3600.0"),
    Moment(moment_id="m-mo-05", minute=66, kind="leverage_swing", leverage=0.84, team="home", players=["KR10"],
           evidence={"action": "tackle", "player": "KR10", "wp_before": 0.52, "wp_after": 0.74, "wp_opposite": 0.52,
                     "leverage": 0.84}, state_ref="m@3960.0"),
    Moment(moment_id="m-mo-06", minute=67, kind="leverage_swing", leverage=0.7, team="away", players=["AV08"],
           evidence={"action": "misplaced_pass", "player": "KR10", "wp_before": 0.3, "wp_after": 0.35,
                     "wp_opposite": 0.3, "leverage": 0.7}, state_ref="m@4020.0"),
    Moment(moment_id="m-mo-07", minute=70, kind="top_speed", leverage=0.0, team="home", players=["KR10"],
           evidence={"player": "KR10", "speed_ms": 9.2, "speed_kmh": 33.1}, state_ref="m@4200.0"),
    Moment(moment_id="m-mo-08", minute=72, kind="control_flip", leverage=0.0, team="home",
           evidence={"now_in_control": "home", "control_index": 0.61, "chaos_index": 0.7}, state_ref="m@4320.0"),
    Moment(moment_id="m-mo-09", minute=74, kind="control_flip", leverage=0.0,
           evidence={"now_in_control": "nobody", "control_index": 0.4, "chaos_index": 1.6}, state_ref="m@4440.0"),
    Moment(moment_id="m-mo-10", minute=58, kind="shape_change", leverage=0.0, team="away",
           evidence={"from": "mid_block", "to": "low_block", "line_height_m": 24.2, "compactness_m2": 731,
                     "pressers": 0.4}, state_ref="m@3480.0"),
]


def test_templates_never_contain_numbers():
    for key, versions in TEMPLATES.items():
        for audience, template in versions.items():
            assert not re.search(r"\d", template), f"{key}/{audience} has a digit; numbers must be slots"


@pytest.mark.parametrize("moment", MOMENTS, ids=lambda m: m.moment_id)
@pytest.mark.parametrize("audience", ["casual", "analyst"])
def test_every_moment_fills_a_valid_cue(moment, audience):
    cue = fallback_cue(moment, audience, NAMES, TEAMS, "m")
    OverlayEvent.model_validate(cue.model_dump())
    text = cue.text()
    assert "{" not in text and text.strip()
    assert cue.verified and cue.evidence_ref == moment.moment_id
    assert cue.t_start > float(moment.state_ref.split("@")[1])


def test_numbers_and_names_come_from_evidence():
    goal = fallback_cue(MOMENTS[0], "casual", NAMES, TEAMS, "m").text()
    assert "Rafael Okafor" in goal and "Kingsport Rovers" in goal and "45%" in goal and "68%" in goal
    shape = fallback_cue(MOMENTS[-1], "casual", NAMES, TEAMS, "m").text()
    assert "low block" in shape and "24 m" in shape


def test_template_keys_cover_actions_and_chaos():
    assert template_key(MOMENTS[4]) == "leverage_swing.tackle"
    assert template_key(MOMENTS[5]) == "leverage_swing.misplaced_pass"
    assert template_key(MOMENTS[8]) == "control_flip.chaos"


def test_hero_numbers():
    assert hero_for(MOMENTS[0]).value == "+23"
    assert hero_for(MOMENTS[3]).label == "xG"
    assert hero_for(MOMENTS[6]).value == "33.1"
    assert hero_for(MOMENTS[7]).label == "control index" and hero_for(MOMENTS[8]).label == "chaos index"
