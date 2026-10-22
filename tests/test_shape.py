from engine.models import TrackingFrame
from engine.shape import ShapeTracker, classify, measure


def away_defending(t, line_from_goal, ball_x=40.0, pressers=0):
    """Away defends the goal at x = 105. Home has the ball at ball_x."""
    players = [{"id": "AV01", "team": "away", "x": 104.0, "y": 34.0, "speed_ms": 0.0}]
    back_x = 105.0 - line_from_goal
    for i, y in enumerate((14.0, 28.0, 40.0, 54.0)):
        players.append({"id": f"AV0{i + 2}", "team": "away", "x": back_x, "y": y, "speed_ms": 0.0})
    for i, y in enumerate((20.0, 34.0, 48.0)):
        players.append({"id": f"AV1{i}", "team": "away", "x": back_x - 10.0, "y": y, "speed_ms": 0.0})
    for i in range(3):
        if i < pressers:
            x, y = ball_x + 2.0, 34.0 + i
        else:
            x, y = back_x - 18.0, 25.0 + 8.0 * i
        players.append({"id": f"AV2{i}", "team": "away", "x": x, "y": y, "speed_ms": 0.0})
    return TrackingFrame(t=t, ball={"x": ball_x, "y": 34.0}, players=players)


KEEPERS = {"AV01"}


def test_measure_ignores_frames_with_the_ball_near_the_defending_goal():
    assert measure(away_defending(0.0, 25.0, ball_x=95.0), "away", KEEPERS) is None
    line, area, pressers = measure(away_defending(0.0, 25.0), "away", KEEPERS)
    assert line == 25.0 and area > 0 and pressers == 0


def test_classify():
    assert classify(25.0, 800.0, 0.0) == "low_block"
    assert classify(50.0, 900.0, 1.0) == "high_press"
    assert classify(50.0, 900.0, 0.1) == "mid_block"
    assert classify(35.0, 900.0, 1.0) == "mid_block"


def test_a_change_is_confirmed_only_after_it_holds():
    tracker = ShapeTracker(KEEPERS)
    changes = []
    for i in range(0, 900):  # 0.2 s frames: 180 s in a low block
        changes += tracker.update(away_defending(i * 0.2, 24.0), possession="home")
    assert tracker.teams["away"].state == "low_block"
    assert changes == []
    for i in range(900, 2100):  # then 240 s pressing high
        changes += tracker.update(away_defending(i * 0.2, 52.0, ball_x=48.0, pressers=2), possession="home")
    assert [c.state for c in changes] == ["high_press"]
    change = changes[0]
    assert change.team == "away" and change.previous == "low_block"
    assert change.t - 180.0 >= 60.0
