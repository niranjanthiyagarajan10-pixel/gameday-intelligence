import pytest

from engine.models import MatchEvent
from engine.press import MIN_ATTEMPTS, PossessionTimeline, PressResistance


def ev(i, kind, team, player, t, pressure=0.0, outcome=None, meta=None):
    return MatchEvent(
        event_id=f"m-{i}", match_id="m", t=t, minute=int(t // 60), period=1, type=kind, team=team,
        player_id=player, x=50.0, y=34.0, end_x=55.0 if kind in ("pass", "carry") else None,
        end_y=34.0 if kind in ("pass", "carry") else None, outcome=outcome, pressure=pressure, meta=meta or {},
    )


def test_timeline_lookup_and_share():
    tl = PossessionTimeline()
    tl.change(0.0, "home")
    tl.change(30.0, "away")
    tl.change(40.0, "home")
    assert tl.at(10.0) == "home" and tl.at(35.0) == "away" and tl.current == "home"
    assert tl.share(0.0, 50.0) == pytest.approx((0.8, 0.2))


def test_retained_and_lost_pressured_possessions():
    tl = PossessionTimeline()
    tl.change(0.0, "home")
    press = PressResistance()
    for i in range(MIN_ATTEMPTS):
        press.record(ev(i, "pass", "home", "KR10", t=10.0 * i, pressure=0.8, outcome="complete"))
    press.record(ev(9, "pass", "home", "KR06", t=1.0, pressure=0.2, outcome="complete"))  # not pressured
    press.record(ev(10, "tackle", "away", "AV05", t=60.0, outcome="won", meta={"carrier": "KR06"}))
    tl.change(60.0, "away")
    press.resolve(100.0, tl)
    rows = {r.player_id: r for r in press.table()}
    assert rows["KR10"].attempts == MIN_ATTEMPTS and rows["KR10"].rate == 1.0
    assert rows["KR06"].attempts == 1 and rows["KR06"].retained == 0
    assert rows["KR06"].rate is None  # too few attempts to show


def test_attempts_wait_for_the_retention_window():
    tl = PossessionTimeline()
    tl.change(0.0, "home")
    press = PressResistance()
    press.record(ev(0, "carry", "home", "KR10", t=10.0, pressure=0.9, outcome="complete"))
    press.resolve(12.0, tl)
    assert press.table() == []
    press.resolve(15.0, tl)
    assert press.table()[0].attempts == 1
