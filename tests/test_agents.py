"""Agents: the Verifier's checks, the Narrator's draft parsing, the card desk's retry and fallback
paths, the model wrapper's timeout and replay cache, and the MCP tools."""

import asyncio
import json

import pytest

from agents.desk import CardDesk
from agents.fallback import slots_for
from agents.llm import LLM, ReplayBackend, ReplayCache, cache_key
from agents.narrator import parse
from agents.verifier import verify
from engine.models import Claim, Moment

NAMES = {"KR10": "Rafael Okafor", "AV08": "Callum Hale"}
TEAMS = {"home": "Kingsport Rovers", "away": "Ashford Vale"}
FORBIDDEN = {"Rafael Okafor", "Okafor", "Callum Hale", "Hale", "Kingsport Rovers", "Ashford Vale"}

GOAL = Moment(moment_id="m-mo-01", minute=12, kind="goal", leverage=2.1, team="home", players=["KR10"],
              evidence={"xg": 0.31, "player": "KR10", "score": "1-0", "wp_before": 0.45, "wp_after": 0.68,
                        "leverage": 2.1}, state_ref="m@720.0")
EQUALISER = Moment(moment_id="m-mo-02", minute=81, kind="goal", leverage=1.4, team="away", players=["AV08"],
                   evidence={"xg": 0.08, "player": "AV08", "score": "1-1", "wp_before": 0.12, "wp_after": 0.3,
                             "leverage": 1.4}, state_ref="m@4860.0")
GOOD = "{player} scores to make it {score}, and {team} win chance jumps from {wp_before} to {wp_after}."


def check(template, moment=GOAL, claims=(), audience="casual"):
    return verify(template, list(claims), moment, slots_for(moment, NAMES, TEAMS), FORBIDDEN, audience)


# Verifier


def test_a_clean_template_passes():
    assert check(GOOD).ok


@pytest.mark.parametrize("template, reason", [
    ("{player} scores to make it {score} in minute 12.", "numbers must be slots"),
    ("Okafor scores to make it {score}.", "names must be slots"),
    ("{player} scores from {distance} to make it {score}.", "unknown slots"),
    ("{player} scores, and {team} lead.", "needs {score}"),
    ("{player} heads in to make it {score}.", "not in the evidence"),
    ("{player} equalises at {score}.", "the score is level, but the evidence says otherwise"),
    ("A late strike from {player} makes it {score}.", "it came late, but the evidence says otherwise"),
    ("{player} scores against the odds to make it {score}.", "low-chance goal, but the evidence says otherwise"),
    ("{player} scores " + chr(0x2014) + " {score}.", "no em dashes"),
    ("{player} scores to make it {score}, and {team} climb to {wp_after} percent.", "already carries its unit"),
    ("{player} scores to make it {score}, lifting {team}'s win chance to {wp_after}.", "never add 's to a slot"),
])
def test_bad_drafts_fail_with_a_reason(template, reason):
    verdict = check(template)
    assert not verdict.ok
    assert any(reason in r for r in verdict.reasons), verdict.reasons


def test_claims_the_evidence_supports_pass():
    t = "A late equaliser from {player} against the odds: {score}, and {team} climb to {wp_after}."
    assert check(t, EQUALISER, [Claim(claim_id="c1", metric="win_probability", subject="away", direction="up")]).ok


def test_declared_claims_are_checked_against_the_numbers():
    down = Claim(claim_id="c1", metric="win_probability", subject="home", direction="down")
    big = Claim(claim_id="c2", metric="xg", subject="", direction="up")
    assert "did not go down" in check(GOOD, claims=[down]).reasons[0]
    assert "not a big chance" in check(GOOD, EQUALISER, claims=[big]).reasons[0]


def test_every_fallback_template_passes_the_verifier():
    """The templates fans see when the Narrator is slow must meet the same bar as the Narrator."""
    from agents.desk import name_list
    from agents.fallback import TEMPLATES, template_key
    from tests.test_fallback import MOMENTS, NAMES as FB_NAMES, TEAMS as FB_TEAMS

    forbidden = name_list(FB_NAMES, FB_TEAMS)
    for m in MOMENTS:
        for aud in ("casual", "analyst"):
            template = TEMPLATES[template_key(m)][aud]
            verdict = verify(template, [], m, slots_for(m, FB_NAMES, FB_TEAMS), forbidden, aud)
            assert verdict.ok, (m.kind, aud, verdict.reasons)


def test_too_long_fails():
    assert "too long" in check(GOOD + " That changes the whole picture of this match for both sides." * 3).reasons[-1]


# Narrator parsing


def test_parse_reads_json_even_in_a_code_fence():
    d = parse('```json\n{"template": "' + GOOD + '", "claims": [{"metric": "score", "subject": "home", "direction": "up"}]}\n```')
    assert d.error is None and d.template == GOOD and d.claims[0].metric == "score"


@pytest.mark.parametrize("text", [None, "", "no json here", '{"claims": []}', "{not json}"])
def test_parse_reports_unusable_replies(text):
    assert parse(text).error


# Card desk with a scripted model


class Scripted:
    """Stands in for Foundry: answers from a script, can be slow or fail."""

    name = "foundry"

    def __init__(self, replies, delay=0.0, fail=False):
        self.replies = list(replies)
        self.prompts = []
        self.delay = delay
        self.fail = fail

    async def complete(self, *, agent, instructions, prompt, model):
        self.prompts.append(prompt)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ConnectionError("network down")
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def reply(template, claims=()):
    return json.dumps({"template": template, "claims": list(claims)})


def desk(backend, timeout=8.0):
    return CardDesk(LLM(backend, timeout_s=timeout), NAMES, TEAMS, "KRAV-7")


def run(coro):
    return asyncio.run(coro)


def test_a_verified_draft_goes_live():
    out = run(desk(Scripted([reply(GOOD)])).write(GOAL, "casual"))
    assert out.source == "narrator"
    assert out.cue.text() == "Rafael Okafor scores to make it 1-0, and Kingsport Rovers win chance jumps from 45% to 68%."
    assert [(s.agent, s.status) for s in out.steps] == [("Narrator", "ok"), ("Verifier", "pass")]


def test_a_rejected_draft_is_sent_back_with_reasons_and_fixed():
    backend = Scripted([reply("Okafor makes it {score}."), reply(GOOD)])
    out = run(desk(backend).write(GOAL, "casual"))
    assert out.source == "narrator"
    assert [s.status for s in out.steps] == ["ok", "reject", "ok", "pass"]
    retry = json.loads(backend.prompts[1])
    assert "names must be slots" in " ".join(retry["previous_attempt"]["rejected_because"])


def test_three_bad_drafts_fall_back_to_the_template():
    out = run(desk(Scripted([reply("{player} equalises at {score}.")])).write(GOAL, "analyst"))
    assert out.source == "template"
    assert [s.agent for s in out.steps] == ["Narrator", "Verifier"] * 3 + ["Fallback"]
    assert out.cue.verified and "Rafael Okafor" in out.cue.text()


def test_a_slow_model_times_out_to_the_template():
    out = run(desk(Scripted([reply(GOOD)], delay=1.0), timeout=0.05).write(GOAL, "casual"))
    assert out.source == "template"
    assert out.steps[0].status == "timeout" and out.steps[-1].agent == "Fallback"


def test_a_failing_model_falls_back_without_raising():
    out = run(desk(Scripted([""], fail=True)).write(GOAL, "casual"))
    assert out.source == "template" and out.steps[0].status == "error"


def test_without_foundry_the_desk_serves_templates():
    out = run(CardDesk(LLM(), NAMES, TEAMS, "KRAV-7").write(GOAL, "casual"))
    assert out.source == "template" and out.steps[0].status == "offline"


def test_replay_cache_answers_recorded_prompts(tmp_path):
    cache = ReplayCache(tmp_path / "cache.json")
    cache.put(cache_key("Narrator", "m", "i", "p"), "hello")
    cache.save()
    llm = LLM(ReplayBackend(ReplayCache(tmp_path / "cache.json")))
    hit = run(llm.complete(agent="Narrator", instructions="i", prompt="p", model="m"))
    miss = run(llm.complete(agent="Narrator", instructions="i", prompt="other", model="m"))
    assert hit.ok and hit.text == "hello" and hit.backend == "replay"
    assert not miss.ok


def test_no_endpoint_means_offline(monkeypatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setenv("REPLAY_MODE", "0")
    assert not LLM.from_env().live


# MCP tools


@pytest.fixture(scope="module")
def room():
    from app.room import MatchRoom, RoomConfig
    from engine.league import build_league

    r = MatchRoom("tools", build_league(), RoomConfig(half_s=300.0, scenario=None))
    while not r.feed.finished:
        r.advance()
    return r


def test_tools_answer_from_the_live_match(room):
    from mcp_server import tools

    state = tools.get_match_state(room)
    assert state["home"] == "Kingsport Rovers" and len(state["score"]) == 2
    shooter = room.live.shots[0].player_id
    player = tools.get_player_live(room, room.roster["players"][shooter]["name"])
    assert player["player"] == shooter and player["shots"] >= 1
    assert tools.get_shot_map(room, "Kingsport Rovers")["shots"] or tools.get_shot_map(room, "away")["shots"]
    assert tools.get_leverage_table(room, limit=3)["rows"]
    cmp = tools.compare_windows(room, 0, 5, 5, 10)
    assert set(cmp["window"]) == {"minutes", "home", "away"}
    if room.cards:
        mid = room.cards[0]["moment"]["moment_id"]
        assert tools.get_moment_evidence(room, mid)["slots"]
        assert "events" in tools.list_supporting_events(room, mid)
        assert tools.verify_claims(room, mid, "Okafor did it.")["pass"] is False
    with pytest.raises(ValueError):
        tools.get_team_shape(room, "Nowhere FC")


def test_mcp_server_lists_and_calls_tools(room):
    from mcp import Client

    from mcp_server.server import create_mcp

    class OneRoomHub:
        def get(self, room_id):
            return room if room_id == "main" else None

    mcp = create_mcp(OneRoomHub())

    async def go():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            result = await client.call_tool("get_match_state", {})
            missing = await client.call_tool("get_match_state", {"room": "nope"})
            return {t.name for t in listed.tools}, result, missing

    names, result, missing = run(go())
    assert {"get_match_state", "get_moment_evidence", "verify_claims", "get_gravity"} <= names
    assert not result.is_error and "Kingsport Rovers" in result.content[0].text
    assert missing.is_error
