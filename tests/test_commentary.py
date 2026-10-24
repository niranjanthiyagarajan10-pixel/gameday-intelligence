"""Commentator styles and the voice: style drafts go through the same Verifier, the voice never
reads anything but verified text, and both fall back without an error."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from agents import commentator
from app.main import create_app
from app.room import RoomConfig
from app.speech import Speech, ssml, voice_for
from tests.test_agents import GOAL, GOOD, Scripted, desk, reply


def run(coro):
    return asyncio.run(coro)


def test_every_style_has_its_own_brief():
    briefs = {s: commentator.instructions(s) for s in commentator.STYLES}
    assert len(set(briefs.values())) == len(commentator.STYLES)
    for brief in briefs.values():
        assert "TEMPLATE" in brief and "Never type a digit" in brief
    with pytest.raises(KeyError):
        commentator.instructions("shouty")


def test_a_style_draft_is_verified_and_labelled():
    backend = Scripted([reply(GOOD)])
    out = run(desk(backend).write(GOAL, "casual", style="hype"))
    assert out.source == "narrator" and out.cue.verified
    assert out.cue.cue_id.endswith("-hype")
    assert [s.agent for s in out.steps] == ["Commentator", "Verifier"]


def test_a_style_draft_that_types_a_name_falls_back():
    bad = reply("Okafor scores to make it {score}.")
    out = run(desk(Scripted([bad, bad, bad])).write(GOAL, "casual", style="stats"))
    assert out.source == "template"
    assert out.steps[-1].agent == "Fallback"


def test_ssml_escapes_text_and_picks_a_voice_per_style_and_language():
    body = ssml("Kingsport <lead> & Ashford", "hype", "en")
    assert "&lt;lead&gt; &amp; Ashford" in body
    assert voice_for("hype", "en").style == "excited"
    assert voice_for("classic", "hi").name.startswith("hi-IN")
    assert voice_for("tactician", "es").name.startswith("es-")
    assert 'xml:lang="hi-IN"' in ssml("text", "classic", "hi")


def test_speech_is_off_without_config():
    assert Speech.from_env() is None


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(RoomConfig(half_s=120.0, speed=30.0, scenario=None))) as c:
        yield c


def _first_card(client):
    client.post("/api/rooms/main/control", json={"action": "restart"})
    client.post("/api/rooms/main/control", json={"action": "resume"})
    for _ in range(200):
        cards = client.get("/api/rooms/main").json()["cards"]
        if cards:
            return cards[0]
        import time
        time.sleep(0.05)
    raise AssertionError("no card")


def test_commentary_falls_back_to_the_verified_classic_line(client):
    card = _first_card(client)
    mid = card["moment"]["moment_id"]
    body = client.get(f"/api/rooms/main/commentary/{mid}", params={"style": "hype", "lang": "en"}).json()
    assert body["text"] == card["cues"]["casual"]["text"]
    assert body["source"] == "classic"
    assert client.get(f"/api/rooms/main/commentary/{mid}", params={"style": "loud"}).status_code == 422
    assert client.get("/api/rooms/main/commentary/nope", params={"style": "hype"}).status_code == 404


def test_voice_without_speech_hands_back_the_text_for_the_browser(client):
    card = _first_card(client)
    r = client.post("/api/rooms/main/speech", json={"moment_id": card["moment"]["moment_id"], "style": "classic"})
    assert r.status_code == 503
    assert r.json()["text"] == card["cues"]["casual"]["text"]
