"""The API and WebSocket stream, on a short fast match."""

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.room import RoomConfig
from engine.models import OverlayEvent

CONFIG = RoomConfig(half_s=60.0, speed=30.0, scenario=None)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(CONFIG)) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_room_state_has_both_teams_and_lineups(client):
    state = client.get("/api/rooms/main").json()
    assert state["type"] == "hello"
    clubs = state["roster"]["clubs"]
    assert clubs["home"]["name"] == "Kingsport Rovers" and clubs["away"]["name"] == "Ashford Vale"
    assert len(clubs["home"]["lineup"]) == 11
    assert state["roster"]["players"]["KR10"]["name"] == "Rafael Okafor"


def test_unknown_room_is_404(client):
    assert client.get("/api/rooms/nope").status_code == 404


def test_stream_sends_hello_then_frames_and_stats(client):
    seen = set()
    with client.websocket_connect("/ws/main") as ws:
        assert ws.receive_json()["type"] == "hello"
        frame = None
        for _ in range(400):
            msg = ws.receive_json()
            seen.add(msg["type"])
            if msg["type"] == "frame":
                frame = msg
            if {"frame", "stats", "analyst"} <= seen:
                break
    assert {"frame", "stats", "analyst"} <= seen
    assert len(frame["players"]) <= 22 and len(frame["ball"]) == 3


def test_controls(client):
    assert client.post("/api/rooms/main/control", json={"action": "speed", "value": 10}).json()["speed"] == 10
    assert client.post("/api/rooms/main/control", json={"action": "speed", "value": 7}).status_code == 422
    assert client.post("/api/rooms/main/control", json={"action": "pause"}).json()["paused"] is True
    assert client.post("/api/rooms/main/control", json={"action": "resume"}).json()["paused"] is False


def test_private_room_starts_from_a_minute(client):
    room_id = client.post("/api/rooms", json={"start_minute": 1.0, "speed": 30.0}).json()["room_id"]
    state = {}
    for _ in range(100):
        state = client.get(f"/api/rooms/{room_id}").json()
        if state["status"] != "catching_up" and state["stats"]["t"] >= 60.0:
            break
        time.sleep(0.1)
    assert state["stats"]["t"] >= 60.0


def test_private_replays_are_the_same_match():
    """A jump link must replay the match everyone else sees, not a new one."""
    from app.room import MatchRoom
    from engine.league import build_league

    a = MatchRoom("aaaa", build_league(), CONFIG)
    b = MatchRoom("bbbb", build_league(), CONFIG)
    for _ in range(600):
        a.advance()
        b.advance()
    assert a.last_frame == b.last_frame
    assert a.live.score == b.live.score


def test_cues_are_machine_readable_overlays(client):
    for _ in range(100):
        cues = client.get("/api/rooms/main/cues").json()["cues"]
        if cues:
            break
        time.sleep(0.1)
    for cue in cues:
        OverlayEvent.model_validate({k: v for k, v in cue.items() if k != "text"})
