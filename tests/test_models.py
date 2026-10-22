import pytest
from pydantic import ValidationError

from engine.models import (
    Answer,
    MatchEvent,
    MatchMeta,
    OverlayEvent,
    PlayerPos,
    StatsUpdate,
    TrackingFrame,
    fill_template,
    template_slots,
)

EVENT = {
    "event_id": "m001-000342",
    "match_id": "m001",
    "t": 2054.2,
    "minute": 34,
    "period": 1,
    "type": "tackle",
    "team": "home",
    "player_id": "H08",
    "x": 61.2,
    "y": 30.5,
    "outcome": "won",
    "pressure": 0.7,
}

CUE = {
    "cue_id": "m001-cue-07",
    "match_id": "m001",
    "t_start": 2056.0,
    "duration_s": 8,
    "kind": "key_moment",
    "audience": "casual",
    "club": "home",
    "lang": "en",
    "template": "{player} wins the ball and lifts home win chance from {wp_before} to {wp_after}.",
    "slots": {"player": "Rivera", "wp_before": "41%", "wp_after": "58%"},
    "verified": True,
    "source_claims": ["c1"],
}

STATS = {
    "t": 2054.2,
    "score": [1, 1],
    "xg": [0.9, 1.1],
    "xt": [3.4, 2.8],
    "possession": [0.52, 0.48],
    "win_prob": [0.58, 0.19, 0.23],
    "momentum": 0.31,
    "control_index": 0.64,
    "chaos_index": 0.22,
}


def test_spec_event_round_trips_through_json():
    event = MatchEvent(**EVENT)
    assert MatchEvent.model_validate_json(event.model_dump_json()) == event


@pytest.mark.parametrize("field, value", [("x", 105.1), ("y", -0.1), ("pressure", 1.2), ("minute", 131)])
def test_event_rejects_out_of_range_values(field, value):
    with pytest.raises(ValidationError):
        MatchEvent(**{**EVENT, field: value})


def test_event_end_point_needs_both_coordinates():
    with pytest.raises(ValidationError):
        MatchEvent(**{**EVENT, "end_x": 80.0})
    MatchEvent(**{**EVENT, "end_x": 80.0, "end_y": 34.0})


def test_contracts_reject_unknown_fields_and_are_frozen():
    with pytest.raises(ValidationError):
        MatchEvent(**{**EVENT, "xg": 0.3})
    event = MatchEvent(**EVENT)
    with pytest.raises(ValidationError):
        event.x = 10.0


def test_tracking_frame_rules():
    player = {"id": "H08", "team": "home", "x": 61.0, "y": 30.1, "speed_ms": 4.2}
    TrackingFrame(t=1.0, ball={"x": 61.2, "y": 30.5}, players=[player])
    with pytest.raises(ValidationError):
        TrackingFrame(t=1.0, ball={"x": 61.2, "y": 30.5}, players=[player, player])
    with pytest.raises(ValidationError):
        PlayerPos(**{**player, "speed_ms": 13.0})
    with pytest.raises(ValidationError):
        PlayerPos(**{**player, "x": 106.0})


def test_ball_may_leave_the_pitch_a_little():
    TrackingFrame(t=1.0, ball={"x": -2.0, "y": 70.0}, players=[])
    with pytest.raises(ValidationError):
        TrackingFrame(t=1.0, ball={"x": -5.0, "y": 34.0}, players=[])


def test_stats_shares_must_sum_to_one():
    StatsUpdate(**STATS)
    with pytest.raises(ValidationError):
        StatsUpdate(**{**STATS, "win_prob": [0.6, 0.2, 0.3]})
    with pytest.raises(ValidationError):
        StatsUpdate(**{**STATS, "possession": [0.5, 0.4]})


def test_match_meta_needs_two_clubs():
    with pytest.raises(ValidationError):
        MatchMeta(match_id="m001", home="KR", away="KR", seed=1)


def test_spec_cue_fills_its_slots():
    cue = OverlayEvent(**CUE)
    assert cue.text() == "Rivera wins the ball and lifts home win chance from 41% to 58%."


def test_cue_rejects_missing_or_unused_slots():
    with pytest.raises(ValidationError):
        OverlayEvent(**{**CUE, "slots": {"player": "Rivera", "wp_before": "41%"}})
    with pytest.raises(ValidationError):
        OverlayEvent(**{**CUE, "slots": {**CUE["slots"], "xg": "0.3"}})


def test_agents_cannot_format_numbers_inside_slots():
    with pytest.raises(ValueError):
        template_slots("Home lead {xg:.2f} to {away_xg}")
    with pytest.raises(ValueError):
        template_slots("Positional {} slot")


def test_template_slots_and_escaped_braces():
    assert template_slots("{player} scores, {{not a slot}} {minute}") == ["player", "minute"]
    assert fill_template("{player} at {{90}}", {"player": "Okafor"}) == "Okafor at {90}"


def test_answer_checks_slots():
    Answer(question="Why?", template="Kept {pct} under pressure.", slots={"pct": "58%"}, verified=True)
    with pytest.raises(ValidationError):
        Answer(question="Why?", template="Kept {pct} under pressure.", slots={}, verified=True)
