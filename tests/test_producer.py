"""The Producer and the Highlights reel: clips picked in code, intro and outro checked like every story."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from agents import producer
from app import producer as P
from app.main import create_app
from app.room import MatchRoom, RoomConfig
from engine.league import build_league


@pytest.fixture(scope="module")
def room():
    r = MatchRoom("reel", build_league(), RoomConfig(half_s=2700.0, scenario=None))
    r.fast_forward(5400.0)
    return r


def _recorded(r):
    return {eid for eid, c in r.clips.items() if c is not None}


def test_clips_are_every_goal_in_match_order_and_capped(room):
    clips = P.select(room.live.shots, _recorded(room))
    goals = [s.event_id for s in room.live.shots if s.outcome == "goal"]
    assert clips and len(clips) <= max(P.MAX_CLIPS, len(goals))
    assert set(goals) <= {s.event_id for s in clips}
    assert [s.t for s in clips] == sorted(s.t for s in clips)
    assert [s.event_id for s in P.select(room.live.shots, _recorded(room))] == [s.event_id for s in clips]
    assert len(P.select(room.live.shots, _recorded(room), cap=1)) == max(1, len(goals))


def test_no_clips_before_any_chance(room):
    assert P.select(room.live.shots, set()) == []
    fresh = MatchRoom("reel-empty", build_league(), RoomConfig(half_s=2700.0, scenario=None))
    assert asyncio.run(fresh.reel()) is None


def _pack(room):
    clips = P.select(room.live.shots, _recorded(room))
    return P.pack(room.live, room.names, room.teams, True, False, clips)


def test_template_reel_passes_its_own_checks(room):
    pk = _pack(room)
    parts = producer.fallback(pk["facts"], pk["truths"])
    assert producer.check(parts, pk["facts"], room.desk.forbidden, pk["truths"]) == []
    live = {**pk["truths"], "finished": False}
    assert producer.check(producer.fallback(pk["facts"], live), pk["facts"], room.desk.forbidden, live) == []


def test_producer_rejects_planted_errors(room):
    pk = _pack(room)
    good = producer.fallback(pk["facts"], pk["truths"])
    name = next(iter(room.names.values()))
    planted = [
        {**good, "intro": "Here are 5 moments from the match."},  # a typed number
        {**good, "intro": f"{name} stars in {{clips}}."},  # a typed name
        {**good, "outro": "{home} created {home_xg} expected goals."},  # cause and effect
        {**good, "outro": "Pressing led to {swing_player} scoring."},  # cause and effect
        {**good, "intro": "{home} {home_goals}, {away} {away_goals} after {minute}."},  # a short one, still fine
    ]
    for parts in planted[:-1]:
        assert producer.check(parts, pk["facts"], room.desk.forbidden, pk["truths"]), parts
    assert producer.check(planted[-1], pk["facts"], room.desk.forbidden, pk["truths"]) == []
    if not pk["truths"]["comeback"]:
        bad = {**good, "outro": "What a comeback from {home}."}
        assert producer.check(bad, pk["facts"], room.desk.forbidden, pk["truths"])


def test_reel_is_cached_until_the_match_moves_on(room):
    first = asyncio.run(room.reel())
    assert first["source"] == "template" and first["intro"] and first["outro"]
    assert "{" not in first["intro"] + first["outro"]
    assert asyncio.run(room.reel())["intro"] == first["intro"]
    assert room._reel is not None and room._reel["key"][0] == room.status
    said = asyncio.run(room.reel_line("intro", "es"))  # the template intro, translated ahead of time
    assert said["lang"] == "es" and said["source"] == "template" and said["text"] != first["intro"]
    assert "{" not in said["text"]
    assert asyncio.run(room.reel_line("middle", "en")) is None


def test_reel_endpoint():
    with TestClient(create_app(RoomConfig(half_s=2700.0, speed=1.0, scenario=None))) as client:
        hub = client.app.state.hub
        room = hub.get("main")
        assert client.get("/api/rooms/main/reel").status_code == 404
        room.fast_forward(5400.0)
        body = client.get("/api/rooms/main/reel?lang=es").json()
        assert body["clips"] and body["intro"] and body["outro"]
        minutes = [c["minute"] for c in body["clips"]]
        assert minutes == sorted(minutes)
        assert client.get(f"/api/rooms/main/explain/{body['clips'][0]['event_id']}").status_code == 200
        r = client.post("/api/rooms/main/reel/speech", json={"part": "outro", "lang": "en"})
        assert r.status_code in (200, 503)
        if r.status_code == 503:
            assert r.json()["text"] == body["outro"]
        assert client.post("/api/rooms/main/reel/speech", json={"part": "x"}).status_code == 422
        assert client.get("/api/rooms/nope/reel").status_code == 404
