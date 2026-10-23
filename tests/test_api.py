"""The API and WebSocket stream, on a short fast match."""

import json
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


def restart(client):
    client.post("/api/rooms/main/control", json={"action": "restart"})
    client.post("/api/rooms/main/control", json={"action": "resume"})


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
    restart(client)  # the test match lasts seconds; make sure it is still being played
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


def test_shot_page_has_metrics_and_a_replay_clip():
    from app.room import MatchRoom
    from engine.league import build_league

    room = MatchRoom("clips", build_league(), CONFIG)
    while not room.feed.finished:
        room.advance()
    assert room.live.shots, "expected at least one shot in two halves of a minute"
    shot = room.live.shots[0]
    page = room.shot(shot.event_id)
    s = page["shot"]
    assert s["shot_type"] and s["distance_m"] > 0 and 0 <= s["xg"] <= 1
    assert s["defender_m"] is None or s["defender_m"] >= 0
    assert 0 <= s["wp_if_miss"] <= s["wp_if_goal"] <= 1
    clip = page["clip"]
    times = [f["t"] for f in clip["frames"]]
    assert times == sorted(times) and times[0] >= shot.t - 12.0 - 1e-6
    assert all(e["t"] <= shot.t for e in clip["events"])
    assert room.shot("nope") is None


def test_player_page_summary():
    from app.room import MatchRoom
    from engine.league import build_league

    room = MatchRoom("players", build_league(), CONFIG)
    while not room.feed.finished:
        room.advance()
    shooter = room.live.shots[0].player_id
    summary = room.player(shooter)["summary"]
    assert summary["shots"] >= 1 and len(summary["list"]) == summary["shots"]
    assert summary["goals_minus_xg"] == round(summary["goals"] - summary["xg"], 3)
    assert summary["distance_km"] >= 0
    assert room.player("ZZ99") is None


def test_shot_and_player_endpoints(client):
    for _ in range(200):
        shots = client.get("/api/rooms/main").json()["analyst"]["shots"]
        if shots:
            break
        time.sleep(0.1)
    assert shots
    first = shots[0]
    assert client.get(f"/api/rooms/main/shots/{first['event_id']}").json()["shot"]["event_id"] == first["event_id"]
    assert client.get(f"/api/rooms/main/players/{first['player']}").json()["summary"]["shots"] >= 1
    assert client.get("/api/rooms/main/shots/missing").status_code == 404


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


def test_stream_sends_events_for_the_pitch_to_animate(client):
    restart(client)  # the test match lasts seconds; make sure it is still being played
    with client.websocket_connect("/ws/main") as ws:
        ws.receive_json()
        batch = None
        for _ in range(600):
            msg = ws.receive_json()
            if msg["type"] == "events":
                batch = msg["events"]
                break
    assert batch
    for e in batch:
        assert e["id"] and e["type"] in {"pass", "shot", "tackle", "interception", "card", "goal"}
        assert e["team"] in ("home", "away") and 0 <= e["x"] <= 105 and 0 <= e["y"] <= 68
        if e["type"] == "tackle":
            assert e["outcome"] == "won"


def test_tracking_visuals_pass_network_and_heatmap():
    from app.payloads import analyst_message
    from app.room import MatchRoom
    from engine.league import build_league
    from engine.metrics import HEAT_X, HEAT_Y

    room = MatchRoom("viz", build_league(), CONFIG)
    while not room.feed.finished:
        room.advance()
    network = analyst_message(room.live)["network"]
    for side in ("home", "away"):
        nodes = {n["player"] for n in network[side]["nodes"]}
        assert 0 < len(nodes) <= 11
        assert all(room.roster["players"][p]["side"] == side for p in nodes)
        for edge in network[side]["edges"]:
            assert edge["n"] >= 2 and edge["a"] in nodes and edge["b"] in nodes
    heat = room.player("KR10")["summary"]["heatmap"]
    assert len(heat) == HEAT_X and all(len(col) == HEAT_Y for col in heat)
    assert sum(map(sum, heat)) > 0


def test_trace_endpoint_reports_the_agent_backend(client):
    body = client.get("/api/rooms/main/trace").json()
    assert body["agents"]["backend"] in ("offline", "foundry", "replay")
    assert isinstance(body["steps"], list)


def test_mcp_endpoint_answers_json_rpc():
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(create_app(CONFIG), base_url="http://localhost:8000") as c:
        init = c.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "1"}}})
        assert init.status_code == 200, init.text
        listed = c.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {t["name"] for t in listed.json()["result"]["tools"]}
        assert {"get_match_state", "get_player_live", "verify_claims"} <= names
        called = c.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "get_match_state", "arguments": {}}})
        assert "Kingsport Rovers" in json.dumps(called.json())


def test_room_swaps_in_the_narrators_verified_text():
    import asyncio

    from agents.fallback import TEMPLATES, template_key
    from agents.llm import LLM
    from app.room import MatchRoom
    from engine.league import build_league
    from engine.models import Moment

    class EchoNarrator:
        """Answers with the trusted template for the moment, so every draft should pass."""

        name = "foundry"

        async def complete(self, *, agent, instructions, prompt, model):
            pack = json.loads(prompt)
            m = Moment(moment_id="x", minute=pack["moment"]["minute"], kind=pack["moment"]["kind"],
                       leverage=pack["moment"]["leverage"], evidence=pack["evidence"], state_ref="x@0")
            audience = "analyst" if "an analyst" in instructions else "casual"
            return json.dumps({"template": TEMPLATES[template_key(m)][audience], "claims": []})

    room = MatchRoom("narrate", build_league(), CONFIG, LLM(EchoNarrator()))
    while not room.cards and not room.feed.finished:
        room.advance()
    assert room.cards, "expected a key moment in two halves of a minute"
    queue = room.subscribe()
    room._to_narrate.append(room.cards[0])

    async def drain():
        task = asyncio.create_task(room._narrate_worker())
        for _ in range(100):
            await asyncio.sleep(0.02)
            if not room._to_narrate and room.cards[0]["source"] == "narrator":
                break
        task.cancel()

    asyncio.run(drain())
    card = room.cards[0]
    assert card["source"] == "narrator" and card["sources"] == {"casual": "narrator", "analyst": "narrator"}
    kinds = []
    while not queue.empty():
        kinds.append(queue.get_nowait()["type"])
    assert "trace" in kinds and "card_update" in kinds
    assert {s["agent"] for s in room.trace} == {"Narrator", "Verifier"}
