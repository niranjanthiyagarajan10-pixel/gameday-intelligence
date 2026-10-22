from engine.models import MatchEvent
from engine.xt import GRID_X, XTGrid, fallback_xt, fit_xt, zone


def ev(i, kind, x, y, end=None, outcome=None, team="home"):
    return MatchEvent(
        event_id=f"m-{i}", match_id="m", t=float(i), minute=0, period=1, type=kind, team=team,
        x=x, y=y, end_x=end[0] if end else None, end_y=end[1] if end else None, outcome=outcome,
    )


def test_fallback_grid_rises_toward_goal():
    g = fallback_xt()
    assert g.at(100, 34) > g.at(80, 34) > g.at(40, 34)
    assert 0.0 <= g.values.min() and g.values.max() < 1.0


def test_value_flows_back_from_shots_through_moves():
    events = []
    # Zone near goal: shots that often score.
    for i in range(20):
        events.append(ev(i, "shot", 100, 34, outcome="goal" if i % 2 else "saved"))
    # Midfield zone: moves that always reach the shooting zone.
    for i in range(20, 40):
        events.append(ev(i, "pass", 60, 34, end=(100, 34), outcome="complete"))
    # Another midfield zone: moves that always fail.
    for i in range(40, 60):
        events.append(ev(i, "pass", 60, 10, end=(100, 34), outcome="incomplete"))
    g = fit_xt(events)
    assert g.at(100, 34) > 0.3
    assert g.at(60, 34) > 0.3 * g.at(100, 34)
    assert g.at(60, 10) == 0.0


def test_events_use_the_acting_teams_attacking_frame():
    home_shot = fit_xt([ev(0, "shot", 100, 34, outcome="goal")])
    away_shot = fit_xt([ev(0, "shot", 5, 34, outcome="goal", team="away")])
    assert home_shot.at(100, 34) == away_shot.at(100, 34)


def test_grid_json_round_trip():
    g = fallback_xt()
    again = XTGrid.from_json(g.to_json())
    assert abs(again.at(95, 30) - g.at(95, 30)) < 1e-6


def test_zone_bounds():
    assert zone(-5, -5) == (0, 0)
    assert zone(500, 500)[0] == GRID_X - 1
