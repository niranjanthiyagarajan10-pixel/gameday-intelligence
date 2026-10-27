"""Step 6: the card desk as an Agent Framework workflow, its OpenTelemetry spans, and the In-depth Analyst."""

import asyncio
import json
import time

import pytest

from agents import deep, tracing
from agents.desk import CardDesk
from agents.fallback import TEMPLATES, template_key
from agents.llm import LLM
from agents.workflow import card_workflow, run_card
from app import matchday
from app.room import MatchRoom, RoomConfig
from engine.league import build_league
from engine.models import Moment
from tests.test_agents import GOAL, NAMES, TEAMS

LEAGUE = build_league()


class Echo:
    """Stands in for Foundry: the trusted template as the Narrator's draft, a pass-through translation."""

    name = "foundry"

    async def complete(self, *, agent, instructions, prompt, model):
        pack = json.loads(prompt)
        if agent == "Personalizer":
            return json.dumps({"template": pack["template"]})
        m = Moment(moment_id="x", minute=pack["moment"]["minute"], kind=pack["moment"]["kind"],
                   leverage=pack["moment"]["leverage"], evidence=pack["evidence"], state_ref="x@0")
        audience = "analyst" if "an analyst" in instructions else "casual"
        return json.dumps({"template": TEMPLATES[template_key(m)][audience], "claims": []})


class Broken:
    name = "foundry"

    async def complete(self, **_):
        raise RuntimeError("network down")


def test_the_workflow_runs_both_narrators_then_translates():
    wf = card_workflow(CardDesk(LLM(Echo()), NAMES, TEAMS, "KRAV-7"))
    done = asyncio.run(run_card(wf, GOAL, langs=("es", "hi")))
    assert [w.cue.audience for w in done.written] == ["casual", "analyst"]
    assert all(w.source == "narrator" for w in done.written)
    assert sorted((w.cue.lang, w.cue.audience) for w in done.translated) == [
        ("es", "analyst"), ("es", "casual"), ("hi", "analyst"), ("hi", "casual")]
    again = asyncio.run(run_card(wf, GOAL, translate=False))  # the same workflow serves every card
    assert len(again.written) == 2 and again.translated == []


def test_a_failing_model_still_gives_template_cards():
    wf = card_workflow(CardDesk(LLM(Broken()), NAMES, TEAMS, "KRAV-7"))
    done = asyncio.run(run_card(wf, GOAL, translate=False))
    assert [w.source for w in done.written] == ["template", "template"]


def test_workflow_spans_are_collected():
    assert tracing.setup()
    wf = card_workflow(CardDesk(LLM(Echo()), NAMES, TEAMS, "KRAV-7"))
    asyncio.run(run_card(wf, GOAL, translate=False))
    from opentelemetry import trace

    trace.get_tracer_provider().force_flush()
    for _ in range(20):
        names = {(s["name"], s["attrs"].get("executor.id")) for s in tracing.recent(600)["spans"]}
        if ("executor.process narrator_casual", "narrator_casual") in names:
            break
        time.sleep(0.2)
    assert ("executor.process narrator_casual", "narrator_casual") in names
    assert ("executor.process personalizer", "personalizer") in names
    assert any(n.startswith("workflow.run") for n, _ in names)
    assert all("definition" not in k for s in tracing.recent(600)["spans"] for k in s["attrs"])


@pytest.fixture(scope="module")
def room():
    r = MatchRoom("deep", LEAGUE, RoomConfig(half_s=1800.0, scenario=None))
    r.fast_forward(32 * 60.0)
    return r


def test_deep_facts_compare_two_windows(room):
    pack = matchday.deep_facts(room.live, room.names, room.teams)
    f = pack["facts"]
    assert f["window_start"] == f"{pack['minute'] - 15}'" and "home_threat_now" in f and "home_threat_before" in f
    shares = [int(f[k].rstrip("%")) for k in ("home_threat_now", "away_threat_now")]
    assert 99 <= sum(shares) <= 101
    assert pack["chart"] and all(0 <= c["home"] <= 1 for c in pack["chart"])
    template = deep.fallback(f, pack["truths"])
    assert deep.check(template, f, room.desk.forbidden, pack["truths"]) == []


def test_deep_wording_must_match_the_facts(room):
    pack = matchday.deep_facts(room.live, room.names, room.teams)
    f, t = pack["facts"], pack["truths"]
    claims = {
        "{home} press high.": "high_press" in (t["home_shape"], t["away_shape"]),
        "{away} sit deep in a low block.": "low_block" in (t["home_shape"], t["away_shape"]),
        "{home} have turned the tide.": t["rising"] is not None,
    }
    for line, true in claims.items():
        reasons = deep.check({"headline": "{home} v {away}", "text": line}, f, room.desk.forbidden, t)
        assert (reasons == []) == true, (line, reasons)
    assert deep.check({"headline": "{home} v {away}", "text": "{home} had 60% of the threat."}, f, room.desk.forbidden, t)


def test_room_writes_a_template_deep_card_and_serves_it(room):
    card = asyncio.run(room.write_deep())
    assert card["source"] == "template" and card["headline"] and card["chart"]
    assert room.hello()["deep"][-1]["id"] == card["id"]
