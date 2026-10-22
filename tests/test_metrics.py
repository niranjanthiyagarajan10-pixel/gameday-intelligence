import pytest

from engine import metrics
from engine.models import TrackingFrame


@pytest.mark.parametrize("distance, expected", [(6, 0.49), (11, 0.24), (16, 0.12), (25, 0.04)])
def test_prior_xg_calibration_points(distance, expected):
    assert metrics.PRIOR_XG.prob(105 - distance, 34) == pytest.approx(expected, abs=0.02)


def test_xg_falls_with_distance_angle_headers_and_pressure():
    assert metrics.xg(95, 34) > metrics.xg(85, 34)
    assert metrics.xg(95, 34) > metrics.xg(95, 10)
    assert metrics.xg(95, 34, header=True) < metrics.xg(95, 34)
    assert metrics.xg(95, 34, pressure=1.0) < metrics.xg(95, 34)


def test_fit_xg_recovers_known_coefficients():
    from engine.rng import SeedTree

    truth = metrics.XGModel(intercept=-0.5, distance=-0.12, angle=1.1, header=-0.9, pressure=-0.7, defender=0.15)
    gen = SeedTree(5).generator("xg-fit-test")
    feats, goals = [], []
    for _ in range(40000):
        xa, ya = gen.uniform(75, 104), gen.uniform(14, 54)
        header, pressure, defender = bool(gen.random() < 0.2), float(gen.random()), float(gen.uniform(0.5, 8))
        feats.append(metrics.shot_features(xa, ya, header, pressure, defender, 3.0))
        goals.append(float(gen.random() < truth.prob(xa, ya, header, pressure, defender)))
    fitted = metrics.fit_xg(feats, goals)
    assert fitted.distance == pytest.approx(truth.distance, abs=0.02)
    assert fitted.defender == pytest.approx(truth.defender, abs=0.03)
    assert fitted.header == pytest.approx(truth.header, abs=0.15)


def test_xg_model_round_trip_and_defender_cap():
    m = metrics.XGModel(intercept=-1.0, distance=-0.1, angle=1.0, header=-1.0, pressure=-0.5, defender=0.2)
    assert metrics.XGModel.from_json(m.to_json()) == m
    assert m.logit(95, 34, defender_m=20.0) == pytest.approx(m.logit(95, 34, defender_m=metrics.DEFENDER_CAP_M))


def test_nearest_defender():
    assert metrics.nearest_defender(90.0, 34.0, [[93.0, 38.0], [80.0, 34.0]]) == pytest.approx(5.0)
    assert metrics.nearest_defender(90.0, 34.0, []) is None


def test_pass_completion_falls_with_distance_pressure_and_forwardness():
    short = metrics.pass_completion(50, 34, 60, 34)
    long = metrics.pass_completion(50, 34, 90, 34)
    assert short > long
    assert metrics.pass_completion(50, 34, 60, 34, pressure=1.0) < short
    assert metrics.pass_completion(50, 34, 40, 34) > short  # backwards is easier
    assert metrics.pass_difficulty(50, 34, 90, 34) == pytest.approx(1 - long)


def test_vectorized_models_match_scalar_ones():
    import numpy as np

    xs, ys = np.array([80.0, 95.0]), np.array([20.0, 34.0])
    for x, y, z in zip(xs, ys, metrics.PRIOR_XG.logit_array(xs, ys)):
        assert z == pytest.approx(metrics.PRIOR_XG.logit(x, y))
    for x, y, z in zip(xs, ys, metrics.pass_logit_array(50.0, 34.0, xs, ys, 0.3)):
        assert z == pytest.approx(metrics.pass_logit(50.0, 34.0, x, y, 0.3))


def frames(path, dt=0.2, ball=None):
    return [
        TrackingFrame(
            t=i * dt,
            ball=ball(i) if ball else {"x": 50.0, "y": 34.0},
            players=[{"id": "KR10", "team": "home", "x": x, "y": 34.0, "speed_ms": 0.0}],
        )
        for i, x in enumerate(path)
    ]


def test_distance_speed_and_sprints_come_from_positions():
    k = metrics.Kinematics()
    # 1 m per frame for 10 frames (5 m/s), then 1.6 m per frame for 10 frames (8 m/s)
    path = [10.0 + i for i in range(11)] + [20.0 + 1.6 * i for i in range(1, 11)]
    for f in frames(path):
        k.update(f)
    run = k.runs["KR10"]
    assert run.distance_m == pytest.approx(26.0)
    assert run.top_speed_ms == pytest.approx(8.0)
    assert run.sprints == 1
    assert run.hsr_m == pytest.approx(16.0, abs=2.0)


def test_teleports_are_not_counted_as_running():
    k = metrics.Kinematics()
    for f in frames([10.0, 11.0, 60.0, 61.0]):
        k.update(f)
    assert k.runs["KR10"].distance_m == pytest.approx(2.0)
    assert k.runs["KR10"].top_speed_ms <= metrics.TELEPORT_MS


def test_ball_speed_right_after_a_strike():
    k = metrics.Kinematics()
    for f in frames([10.0] * 4, ball=lambda i: {"x": 80.0 + 6.0 * max(i - 1, 0), "y": 34.0}):
        k.update(f)
    assert k.ball_speed_after(0.2) == pytest.approx(30.0)
