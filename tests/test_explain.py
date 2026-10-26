"""Explain this moment: the beats found in code for every big chance in a played match."""

import pytest

from app.room import MatchRoom, RoomConfig
from engine.explain import find_beats, goal_side
from engine.league import build_league

KINDS = {"won", "foul_won", "restart", "pass", "carry", "tackle_beaten", "shot"}


@pytest.fixture(scope="module")
def chances():
    room = MatchRoom("explain", build_league(), RoomConfig(half_s=2700.0, scenario=None))
    room.fast_forward(5400.0)
    side_of = {p: v["side"] for p, v in room.roster["players"].items()}
    keepers = {p for p, v in room.roster["players"].items() if v["position"] == "GK"}
    out = []
    for s in room.live.shots:
        if s.xg >= 0.15 or s.outcome == "goal":
            page = room.shot(s.event_id)
            beats = find_beats(page["shot"], list(room.event_log.values()), page["clip"]["frames"], side_of, keepers)
            out.append((page["shot"], beats, side_of))
    assert out
    return out


def test_beats_are_in_time_order_and_end_with_the_shot(chances):
    for shot, beats, _ in chances:
        assert beats[-1]["kind"] == "shot"
        assert beats[-1]["player"] == shot["player"]
        times = [b["t"] for b in beats]
        assert times == sorted(times)
        assert all(b["kind"] in KINDS for b in beats)
        assert len(beats) <= 5


def test_every_beat_is_the_attacking_teams_move(chances):
    for shot, beats, side_of in chances:
        for b in beats:
            if b["kind"] in ("pass", "carry", "shot", "won") and b.get("player"):
                assert side_of[b["player"]] == shot["team"]
            if b["kind"] == "pass":
                assert b["facts"]["bypassed"] >= 0
                assert b["facts"]["distance_m"] >= 0


def test_a_goal_has_a_start_or_a_build_up(chances):
    goals = [beats for shot, beats, _ in chances if shot["outcome"] == "goal"]
    assert goals
    assert any(len(b) >= 2 for b in goals)


def test_goal_side_counts_only_opponents_nearer_goal():
    frame = {"players": [["H1", 50, 34, 0], ["A1", 60, 34, 0], ["A2", 40, 34, 0], ["AK", 100, 34, 0]]}
    side_of = {"H1": "home", "A1": "away", "A2": "away", "AK": "away"}
    assert goal_side(frame, 50, 34, "home", side_of, {"AK"}) == ["A1"]
    assert goal_side(frame, 50, 34, "away", {"H1": "home", "A1": "home", "A2": "home", "AK": "away"}, set()) == ["A2"]


def _pack(chances_room):
    from app import explain as E
    room, shot = chances_room
    page = room.shot(shot.event_id)
    return E.pack(page["shot"], list(room.event_log.values()), page["clip"]["frames"], room.roster, room.names, room.teams)


@pytest.fixture(scope="module")
def packs():
    from app import explain as E
    room = MatchRoom("explain-facts", build_league(), RoomConfig(half_s=2700.0, scenario=None))
    room.fast_forward(5400.0)
    out = [_pack((room, s)) for s in room.live.shots if E.explainable({"outcome": s.outcome, "xg": s.xg})]
    return room, out


def test_template_explanations_pass_their_own_checks(packs):
    from agents import explainer
    room, out = packs
    for pk in out:
        parts = explainer.fallback(pk["facts"], pk["truths"])
        assert len(parts["lines"]) == len(pk["beats"])
        assert explainer.check(parts, pk["facts"], room.desk.forbidden, pk["truths"]) == []


def test_explainer_rejects_planted_errors(packs):
    from agents import explainer
    room, out = packs
    pk = next(p for p in out if p["truths"]["outcome"] != "goal" and p["truths"]["beats"] >= 2)
    good = explainer.fallback(pk["facts"], pk["truths"])
    name = next(iter(n for n in room.names.values()))
    planted = [
        {**good, "lines": good["lines"][:-1]},  # a beat missing
        {**good, "why": "It was a 0.4 xG chance."},  # a typed number
        {**good, "why": f"{name} had the space."},  # a typed name
        {**good, "why": "{shooter} scores with ease."},  # a goal that was not
        {**good, "lines": [good["lines"][0].replace(".", ", then {b2_player} takes over.")] + good["lines"][1:]},  # out of order
        {**good, "why": "{shooter} was unmarked with time and space."} if (pk["truths"]["space_m"] or 9) < 3 else
        {**good, "why": "{shooter} was in a tight spot."},  # space claim against the tracking
    ]
    for parts in planted:
        assert explainer.check(parts, pk["facts"], room.desk.forbidden, pk["truths"]), parts


def test_explain_endpoint_serves_a_cached_template_story():
    import asyncio
    room = MatchRoom("explain-api", build_league(), RoomConfig(half_s=2700.0, scenario=None))
    room.fast_forward(5400.0)
    shot = next(s for s in room.live.shots if s.outcome == "goal")
    first = asyncio.run(room.explain(shot.event_id))
    assert first["source"] == "template"
    assert first["beats"][-1]["kind"] == "shot" and all(b["line"] for b in first["beats"])
    assert asyncio.run(room.explain(shot.event_id)) is first
    assert asyncio.run(room.explain("nope")) is None
