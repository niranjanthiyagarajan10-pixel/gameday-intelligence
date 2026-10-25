"""The agent eval harness. Two questions, answered with numbers:

1. Do our checks catch the mistakes a model makes? (planted errors, no model needed)
   Real key moments from the five scenario matches are written up with trusted lines, then
   deliberately broken in the ways language models break facts: a typed number, a typed name,
   a claim the evidence does not support, a translation that drops a slot, an Analyst answer that
   reads a tool that does not exist. Every broken line must be caught, and every clean line must pass.

2. How do the real agents do on Foundry? (--live)
   The Narrator, the Commentator in three styles and the Personalizer write every sampled moment;
   the Analyst answers questions about a paused match whose true answers are read from the same MCP
   tools. We count first-draft passes, retries, fallbacks, latency and correct answers, and audit every
   published line: each number in it must come from a slot that code filled.

    python -m tests.agent_eval                      planted errors only
    python -m tests.agent_eval --live               plus the live agents (needs Foundry and `az login`)
    python -m tests.agent_eval --live --url URL     Analyst questions against a running app (default local)
    python -m tests.agent_eval --analyst --url URL  only the Analyst questions
    python -m tests.agent_eval --refresh-moments    replay the scenario matches to rebuild the moment set

Results go to data/evals/report.json, which the app shows at #/evals and the README quotes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents import analyst, personalizer, recap
from agents.desk import CardDesk, name_list
from agents.fallback import TEMPLATES, slots_for, template_key
from agents.verifier import IMPLIED, REQUIRED_SLOTS, verify
from engine.models import Claim, Moment, TrackingFrame

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "data" / "evals"
MOMENTS_PATH = EVAL_DIR / "moments.json"
REPORT_PATH = EVAL_DIR / "report.json"
LIVE_SAMPLE = 30  # moments the live run writes up; spread evenly over the five matches
ASK_GAP_S = 5.5


# The moment set: every key moment of the five scenario matches


def _collect(scenario_id: str) -> dict[str, Any]:
    from engine.league import build_league
    from engine.live import LiveStats
    from engine.models import MatchMeta
    from engine.scenarios import live_match_id, path_for
    from engine.sim import MatchSimulator, SimConfig, load_scenario

    sc = load_scenario(path_for(scenario_id))
    league = build_league()
    meta = MatchMeta(match_id=live_match_id(sc.home, sc.away, sc.seed or 0), home=sc.home, away=sc.away, seed=sc.seed or 0)
    live = LiveStats(meta, league)
    moments = []
    for item in MatchSimulator(meta, league, SimConfig(mode="full"), sc).run():
        moments += [m.model_dump(mode="json") for m in live.push(item)]
        if isinstance(item, TrackingFrame):
            continue
    names = {p.player_id: p.name for c in (sc.home, sc.away) for p in league.squads[c]}
    teams = {"home": league.clubs[sc.home].name, "away": league.clubs[sc.away].name}
    return {"scenario": scenario_id, "names": names, "teams": teams, "moments": moments}


def refresh_moments() -> None:
    from engine.scenarios import STORIES

    with ProcessPoolExecutor() as pool:
        matches = list(pool.map(_collect, [s.scenario_id for s in STORIES]))
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    MOMENTS_PATH.write_text(json.dumps({"matches": matches}, ensure_ascii=False), encoding="utf-8")


@dataclass(frozen=True)
class Case:
    match: str
    moment: Moment
    names: dict[str, str]
    teams: dict[str, str]

    @property
    def allowed(self) -> dict[str, str]:
        return slots_for(self.moment, self.names, self.teams)  # type: ignore[arg-type]

    @property
    def forbidden(self) -> set[str]:
        return name_list(self.names, self.teams)  # type: ignore[arg-type]


def load_cases() -> list[Case]:
    data = json.loads(MOMENTS_PATH.read_text(encoding="utf-8"))
    return [Case(m["scenario"], Moment.model_validate(mo), m["names"], m["teams"])
            for m in data["matches"] for mo in m["moments"]]


# Planted errors: each mutator breaks a trusted line one way, or returns None when it cannot apply

Draft = tuple[str, list[Claim]]
SLOT = re.compile(r"\{(\w+)\}")
NUMERIC = re.compile(r"\d")


def _first_slot(template: str, allowed: dict[str, str], numeric: bool) -> str | None:
    for name in SLOT.findall(template):
        if name in allowed and bool(NUMERIC.search(allowed[name])) == numeric:
            return name
    return None


def typed_number(t: str, c: Case) -> Draft | None:
    s = _first_slot(t, c.allowed, numeric=True)
    return (t.replace("{" + s + "}", c.allowed[s], 1), []) if s else None


def typed_name(t: str, c: Case) -> Draft | None:
    s = next((n for n in ("player", "team") if "{" + n + "}" in t and c.allowed.get(n)), None)
    return (t.replace("{" + s + "}", c.allowed[s], 1), []) if s else None


def unknown_slot(t: str, c: Case) -> Draft | None:
    return (t.rstrip(".") + " from {distance}.", [])


def missing_slot(t: str, c: Case) -> Draft | None:
    need = sorted(REQUIRED_SLOTS.get(c.moment.kind, set()) & set(SLOT.findall(t)))
    return (t.replace("{" + need[0] + "}", "the player"), []) if need else None


UNSUPPORTED = ["with a header", "from the penalty spot", "after a clever assist", "for a season best",
               "despite an injury", "as the crowd roars"]


def unsupported_detail(t: str, c: Case) -> Draft | None:
    detail = UNSUPPORTED[hash(c.moment.moment_id) % len(UNSUPPORTED)]
    return (t.rstrip(".") + f" {detail}.", [])


# One plain phrase per wording the Verifier reads as a claim.
PHRASES = ["It is all square.", "They lead now.", "A late winner.", "It comes late.", "It comes early.",
           "What a comeback.", "A big chance.", "Against the odds.", "They are down to ten men.",
           "The game turns chaotic.", "They sit in a low block.", "They go to a high press.",
           "A mid block now.", "The fastest run of the day.", "The opening goal.", "They double their lead.",
           "They dominate."]


def false_wording(t: str, c: Case) -> Draft | None:
    for phrase in PHRASES:
        for pattern, _, test in IMPLIED:
            if re.search(pattern, phrase.lower()) and test(c.moment) is False:
                return (t + " " + phrase, [])
    return None


def false_claim(t: str, c: Case) -> Draft | None:
    ev, m = c.moment.evidence, c.moment
    if "wp_before" in ev and "wp_after" in ev and ev["wp_before"] != ev["wp_after"]:
        wrong = "down" if float(ev["wp_after"]) > float(ev["wp_before"]) else "up"
        return (t, [Claim(claim_id="c1", metric="win_probability", subject="team", direction=wrong)])
    if "xg" in ev and float(ev["xg"]) < 0.3:
        return (t, [Claim(claim_id="c1", metric="xg", subject="team", direction="up")])
    if m.kind != "red_card":
        return (t, [Claim(claim_id="c1", metric="red_card", subject="team")])
    return (t, [Claim(claim_id="c1", metric="speed", subject="player")])


def em_dash(t: str, c: Case) -> Draft | None:
    return (t.replace(". ", " " + chr(0x2014) + " ", 1) if ". " in t else t + " " + chr(0x2014) + " what a moment.", [])


def possessive(t: str, c: Case) -> Draft | None:
    s = next((n for n in ("team", "player") if n in c.allowed and c.allowed[n]), None)
    return (t + " A big moment for {" + s + "}'s afternoon.", []) if s else None


def double_unit(t: str, c: Case) -> Draft | None:
    for name in SLOT.findall(t):
        v = c.allowed.get(name, "")
        unit = "percent" if v.endswith("%") else "meters" if v.endswith(" m") else "kilometres" if v.endswith("km/h") else None
        if unit:
            return (t.replace("{" + name + "}", "{" + name + "} " + unit, 1), [])
    return None


def gendered(t: str, c: Case) -> Draft | None:
    return (t + " What a moment for him.", [])


def too_long(t: str, c: Case) -> Draft | None:
    return (t + " " + "The match keeps moving and the story keeps growing. " * 6, [])


NARRATOR_MUTATORS = [typed_number, typed_name, unknown_slot, missing_slot, unsupported_detail, false_wording,
                     false_claim, em_dash, possessive, double_unit, gendered, too_long]


def _translation_mutators(src: str, c: Case) -> list[tuple[str, str | None]]:
    slots = SLOT.findall(src)
    name = c.allowed.get("player") or c.allowed.get("team") or ""
    return [
        ("drops a slot", src.replace("{" + slots[0] + "}", "", 1) if slots else None),
        ("adds a slot", src + " {" + slots[0] + "}" if slots else None),
        ("renames a slot", src.replace("{" + slots[0] + "}", "{jugador}", 1) if slots else None),
        ("types a digit", src + " 2"),
        ("types a Devanagari digit", src + " " + chr(0x0968)),
        ("types a name", src + " " + name if name and name not in re.sub(r"\{[^{}]*\}", " ", src) else None),
        ("em dash", src + " " + chr(0x2014) + " ok"),
    ]


def planted(cases: list[Case]) -> dict[str, Any]:
    """Every check's catch rate on planted errors and its pass rate on clean lines."""
    caught: dict[str, Counter] = defaultdict(Counter)
    clean = Counter()
    misses: list[dict[str, str]] = []

    def record(agent: str, category: str, rejected: bool, example: str) -> None:
        caught[f"{agent}: {category}"]["planted"] += 1
        caught[f"{agent}: {category}"]["caught"] += int(rejected)
        if not rejected and len(misses) < 20:
            misses.append({"agent": agent, "category": category, "example": example})

    for c in cases:
        allowed, forbidden = c.allowed, c.forbidden
        for audience in ("casual", "analyst"):
            trusted = TEMPLATES[template_key(c.moment)][audience]
            ok = verify(trusted, [], c.moment, allowed, forbidden, audience).ok
            clean["verifier"] += 1
            clean["verifier_pass"] += int(ok)
            if not ok:
                misses.append({"agent": "Verifier", "category": "clean line rejected", "example": trusted})
            for mutate in NARRATOR_MUTATORS:
                bad = mutate(trusted, c)
                if bad is None:
                    continue
                verdict = verify(bad[0], bad[1], c.moment, allowed, forbidden, audience)
                record("Narrator and Commentator", mutate.__name__.replace("_", " "), not verdict.ok, bad[0])
            # The Personalizer's check, on the same trusted line standing in for a translation.
            clean["personalizer"] += 1
            clean["personalizer_pass"] += int(not personalizer.check(trusted, trusted, forbidden))
            for category, out in _translation_mutators(trusted, c):
                if out is not None:
                    record("Personalizer", category, bool(personalizer.check(trusted, out, forbidden)), out)

    for (agent, category), result, example in _analyst_and_recap_plants() + _story_plants():
        if category.startswith("clean"):  # result means "passed" for a clean line
            clean["other"] += 1
            clean["other_pass"] += int(result)
        else:
            record(agent, category, result, example)
    rows = [{"check": k, "planted": v["planted"], "caught": v["caught"]} for k, v in sorted(caught.items())]
    return {
        "moments": len(cases),
        "planted": sum(r["planted"] for r in rows),
        "caught": sum(r["caught"] for r in rows),
        "clean": clean["verifier"] + clean["personalizer"] + clean["other"],
        "clean_passed": clean["verifier_pass"] + clean["personalizer_pass"] + clean["other_pass"],
        "rows": rows,
        "misses": misses,
    }


def _spec(tool: str, field: str, **args: Any) -> dict[str, Any]:
    return {"tool": tool, "args": args, "field": field}


# Clean Analyst answers over different tools; every planted error is applied to each of them.
GOOD_ANSWERS: list[tuple[str, dict[str, dict[str, Any]]]] = [
    ("It is {s1}.", {"s1": _spec("get_match_state", "score")}),
    ("The expected goals are {s1}.", {"s1": _spec("get_match_state", "xg")}),
    ("{s1} has a win chance of {s2}.", {"s1": _spec("get_match_state", "home"), "s2": _spec("get_match_state", "win_probability.home")}),
    ("Possession is split {s1}.", {"s1": _spec("get_match_state", "possession")}),
    ("The sides have {s1} players on the pitch.", {"s1": _spec("get_match_state", "men")}),
    ("{s1} has added the most win value, {s2}.", {"s1": _spec("get_leverage_table", "rows.0.name"), "s2": _spec("get_leverage_table", "rows.0.total")}),
    ("{s1} has hit {s2} km/h.", {"s1": _spec("get_player_live", "name", player="KR10"), "s2": _spec("get_player_live", "top_speed_kmh", player="KR10")}),
    ("{s1} has run {s2} km.", {"s1": _spec("get_player_live", "name", player="KR09"), "s2": _spec("get_player_live", "distance_km", player="KR09")}),
    ("The away side sits in a {s1}.", {"s1": _spec("get_team_shape", "state", team="away")}),
]


def _analyst_plants(answer: str, slots: dict[str, Any], values: dict[str, str], name: str) -> list[tuple[str, str, dict[str, Any]]]:
    first = next(iter(slots))
    numeric = next((k for k in slots if NUMERIC.search(values.get(k, ""))), None)
    named = next((k for k in slots if values.get(k) == name or values.get(k, "").istitle()), None)
    out = []
    if numeric:
        out.append(("types a number", answer.replace("{" + numeric + "}", values[numeric]),
                    {k: v for k, v in slots.items() if k != numeric}))
    if named:
        out.append(("types a name", answer.replace("{" + named + "}", values[named]), {k: v for k, v in slots.items() if k != named}))
    else:
        out.append(("types a name", answer + f" {name} is involved.", slots))
    out += [
        ("slot without a tool", answer + " Next is {s9}.", slots),
        ("tool read never used", answer, {**slots, "s9": _spec("get_match_state", "minute")}),
        ("unknown tool", answer, {**slots, first: {**slots[first], "tool": "delete_match"}}),
        ("write tool not allowed", answer, {**slots, first: _spec("verify_claims", "pass", moment_id="x", template="t")}),
        ("field that does not exist", answer, {**slots, first: {**slots[first], "field": "attendance"}}),
        ("gendered pronoun", answer + " That is his best yet.", slots),
        ("em dash", answer + " " + chr(0x2014) + " remarkable.", slots),
    ]
    return out


def _analyst_and_recap_plants() -> list[tuple[tuple[str, str], bool, str]]:
    """The Analyst's and the Recap's checks, on real answers and reports from a match in progress."""
    from app.room import MatchRoom, RoomConfig
    from engine.league import build_league

    room = MatchRoom("eval", build_league(), RoomConfig(half_s=600.0, scenario=None))
    room.fast_forward(900.0)
    forbidden = room.desk.forbidden
    name = room.names["AV09"]
    out: list[tuple[tuple[str, str], bool, str]] = []

    def analyst_rejects(answer: str, slots: dict[str, Any], question: str = "") -> bool:
        reasons = analyst.check(answer, slots, forbidden, question)
        if not reasons:
            values, _, reasons = analyst.resolve(room, slots)
            if not reasons:
                reasons = analyst.check_filled(answer.format(**values), question, forbidden)
        return bool(reasons)

    for answer, slots in GOOD_ANSWERS:
        values, _, problems = analyst.resolve(room, slots)
        out.append((("Analyst", "clean answer passes"), not problems and not analyst_rejects(answer, slots), answer))
        for category, bad, bad_slots in _analyst_plants(answer, slots, values, name):
            out.append((("Analyst", category), analyst_rejects(bad, bad_slots), bad))
        unit = next((k for k in slots if values.get(k, "").endswith(("%", "km/h"))), None)
        if unit:
            extra = "%" if values[unit].endswith("%") else " km/h"
            bad = answer.replace("{" + unit + "}", "{" + unit + "}" + extra, 1)
            out.append((("Analyst", "unit after a slot"), analyst_rejects(bad, slots), bad))
        out.append((("Analyst", "leaves out the player asked about"),
                    analyst_rejects(answer, slots, f"What about {name}?"), answer))

    from app.blueprint import build_blueprint

    facts = build_blueprint(room.live, room.roster, room.status, room.config.half_s)["overview"]["facts"]
    keys = sorted(facts)
    for i in range(0, min(len(keys), 9), 3):
        trio = keys[i:i + 3]
        headline = "{" + trio[0] + "} at the break"
        text = "The story in numbers: " + ", ".join("{" + k + "}" for k in trio) + "."
        out.append((("Recap", "clean report passes"), not recap.check(headline, text, facts, forbidden), text))
        numeric = next((k for k in trio if NUMERIC.search(str(facts[k]))), None)
        plants = [
            ("types a name", text + f" {name} stood out."),
            ("unknown fact", text + " The crowd was {attendance}."),
            ("unsupported detail", text + " A late header settled it."),
            ("gendered pronoun", text + " His side were better."),
            ("em dash", text + " " + chr(0x2014) + " as expected."),
        ]
        if numeric:
            plants.append(("types a number", text.replace("{" + numeric + "}", str(facts[numeric]))))
        for category, bad in plants:
            out.append((("Recap", category), bool(recap.check(headline, bad, facts, forbidden)), bad))
    return out


def _story_mutations(text: str, facts: dict[str, str], truths: dict[str, Any], implied: list) -> list[tuple[str, str]]:
    """Broken versions of a trusted Preview or Post-game line."""
    slots = SLOT.findall(text)
    out: list[tuple[str, str]] = []
    numeric = next((s for s in slots if NUMERIC.search(facts.get(s, ""))), None)
    if numeric:
        out.append(("types a number", text.replace("{" + numeric + "}", facts[numeric], 1)))
    if "{home}" in text:
        out.append(("types a name", text.replace("{home}", facts["home"], 1)))
    out += [("unknown fact", text + " The gate was {attendance}."),
            ("unsupported detail", text + " A key injury could decide it."),
            ("em dash", text + " " + chr(0x2014) + " watch this."),
            ("gendered pronoun", text + " His side will be ready.")]
    unit = next((s for s in slots if facts.get(s, "").endswith("%")), None)
    if unit:
        out.append(("unit after a fact", text.replace("{" + unit + "}", "{" + unit + "} percent", 1)))
    for phrase in ("A fierce local derby.", "Both arrive unbeaten.", "The league leaders are here.",
                   "A side at the bottom of the table.", "The favourites are clear.", "The match was drawn.",
                   "A deserved victory.", "A stunning comeback.", "A late winner.", "A hat-trick to remember.",
                   "Down to ten men.", "A huge upset."):
        if any(re.search(pattern, phrase.lower()) and not test(truths) for pattern, _, test in implied):
            out.append(("claim the facts do not support", text + " " + phrase))
            break
    return out


def _story_plants() -> list[tuple[tuple[str, str], bool, str]]:
    """The Preview and Post-game checks, on every live fixture's trusted lines."""
    from agents import postgame, preview
    from app import matchday
    from app.league import season
    from app.room import MatchRoom, RoomConfig
    from engine.league import build_league
    from engine.season import MATCHDAY_FIXTURES

    league = build_league()
    out: list[tuple[tuple[str, str], bool, str]] = []
    for home, away in MATCHDAY_FIXTURES:
        pack = matchday.preview(league, season(), home, away)
        facts, truths = pack["facts"], pack["truths"]
        names = name_list({p.player_id: p.name for c in (home, away) for p in league.squads[c]},
                          {"home": facts["home"], "away": facts["away"]})
        trusted = preview.fallback(facts, truths)
        out.append((("Preview", "clean preview passes"), not preview.check(trusted, facts, names, truths), trusted["story"]))
        for category, bad in _story_mutations(trusted["story"], facts, truths, preview.IMPLIED):
            out.append((("Preview", category), bool(preview.check({**trusted, "story": bad}, facts, names, truths)), bad))
    from agents import newsdesk, story, summarizer
    from app.newsdesk import matches

    for m in matches():
        facts, truths = m["facts"], m["truths"]
        names = name_list({p.player_id: p.name for c in (m["home"], m["away"]) for p in league.squads[c]},
                          {"home": facts["home"], "away": facts["away"]})
        report = newsdesk.fallback(facts, truths)
        out.append((("Newsdesk", "clean report passes"), not newsdesk.check(report, facts, names, truths), report["headline"]))
        for category, bad in _story_mutations(report["body"][-1], facts, truths, story.MATCH_IMPLIED):
            out.append((("Newsdesk", category),
                        bool(newsdesk.check({**report, "body": report["body"][:-1] + [bad]}, facts, names, truths)), bad))
        brief = summarizer.fallback(facts, truths)
        out.append((("Summarizer", "clean brief passes"), not summarizer.check(brief, facts, names, truths), brief["bullets"][0]))
        for category, bad in _story_mutations(brief["bullets"][0], facts, truths, story.MATCH_IMPLIED):
            out.append((("Summarizer", category),
                        bool(summarizer.check({"bullets": [bad] + brief["bullets"][1:]}, facts, names, truths)), bad))
    room = MatchRoom("eval-pg", league, RoomConfig(half_s=600.0, scenario=None))
    room.fast_forward(1200.0)
    pack = matchday.postgame(room, league)
    facts, truths = pack["facts"], pack["truths"]
    trusted = postgame.fallback(facts)
    out.append((("Post-game", "clean lines pass"), not postgame.check(trusted, facts, room.desk.forbidden, truths), trusted["look_ahead"][0]))
    for line in trusted["look_ahead"]:
        for category, bad in _story_mutations(line, facts, truths, postgame.IMPLIED):
            lines = [bad if x == line else x for x in trusted["look_ahead"]]
            out.append((("Post-game", category), bool(postgame.check({"look_ahead": lines}, facts, room.desk.forbidden, truths)), bad))
    from agents import deep

    room.fast_forward(2000.0)  # past the half hour, so the deep card has a window to compare with
    pack = matchday.deep_facts(room.live, room.names, room.teams)
    facts, truths = pack["facts"], pack["truths"]
    card = deep.fallback(facts, truths)
    out.append((("In-depth Analyst", "clean card passes"), not deep.check(card, facts, room.desk.forbidden, truths), card["text"]))
    for category, bad in _story_mutations(card["text"], facts, truths, deep.IMPLIED):
        out.append((("In-depth Analyst", category), bool(deep.check({**card, "text": bad}, facts, room.desk.forbidden, truths)), bad))
    for phrase in ("{home} press high.", "{away} sit deep in a low block.", "{home} have turned the tide."):
        if any(re.search(p, phrase.lower()) and not test(truths) for p, _, test in deep.IMPLIED):
            out.append((("In-depth Analyst", "shape or swing the facts do not show"),
                        bool(deep.check({**card, "text": card["text"] + " " + phrase}, facts, room.desk.forbidden, truths)), phrase))
    return out


# Live: the real agents on Foundry


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _untraced_numbers(text: str, values: list[str]) -> list[str]:
    """Numbers in a published line that no filled slot supplied. Should always be empty."""
    allowed = {n for v in values for n in NUMBER.findall(v)}
    return [n for n in NUMBER.findall(text) if n not in allowed]


def _sample(cases: list[Case], n: int) -> list[Case]:
    if len(cases) <= n:
        return cases
    step = len(cases) / n
    return [cases[int(i * step)] for i in range(n)]


async def live_writers(cases: list[Case]) -> dict[str, Any]:
    from agents.llm import LLM
    from app.env import load_env

    load_env()
    llm = LLM.from_env()
    if not llm.live:
        raise SystemExit("no Foundry endpoint configured: set FOUNDRY_PROJECT_ENDPOINT and run az login")
    await llm.warm()
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sem = asyncio.Semaphore(6)

    async def one(c: Case, label: str, audience: str, style: str | None) -> None:
        async with sem:
            desk = CardDesk(llm, c.names, c.teams, c.match)  # type: ignore[arg-type]
            started = time.perf_counter()
            w = await desk.write(c.moment, audience, style)  # type: ignore[arg-type]
            ms = round((time.perf_counter() - started) * 1000)
            drafts = sum(1 for s in w.steps if s.agent in ("Narrator", "Commentator") and s.status == "ok")
            first = next((s.status for s in w.steps if s.agent == "Verifier"), None) == "pass"
            text = w.cue.text()
            row = {"moment": c.moment.moment_id, "kind": c.moment.kind, "verified": w.source == "narrator",
                   "first_draft": first, "drafts": drafts, "ms": ms, "text": text,
                   "untraced": _untraced_numbers(text, list(w.cue.slots.values())),
                   "rejections": [s.detail for s in w.steps if s.status == "reject"],
                   "failures": [f"{s.status}: {s.detail[:80]}" for s in w.steps
                                if s.agent in ("Narrator", "Commentator") and s.status not in ("ok",)]}
            if w.source == "narrator" and style is None and audience == "casual":
                for lang in ("es", "hi"):
                    t = await desk.translate(w.cue, lang, 0.0)
                    runs[f"Personalizer {lang}"].append({"verified": t.source == "personalizer", "first_draft": t.source == "personalizer",
                                                         "drafts": 1, "ms": sum(s.ms for s in t.steps), "text": t.cue.text(),
                                                         "untraced": _untraced_numbers(t.cue.text(), list(t.cue.slots.values())),
                                                         "rejections": [s.detail for s in t.steps if s.status == "reject"]})
            runs[label].append(row)

    jobs = []
    for c in cases:
        jobs += [one(c, "Narrator casual", "casual", None), one(c, "Narrator analyst", "analyst", None)]
        jobs += [one(c, f"Commentator {s}", "casual" if s == "hype" else "analyst", s) for s in ("hype", "stats", "tactician")]
    await asyncio.gather(*jobs)
    return {"rows": [_summary(label, rs) for label, rs in sorted(runs.items())],
            "rejections": Counter(_reason_kind(r) for rs in runs.values() for row in rs for r in row["rejections"]).most_common(8),
            "examples": {label: rs[0]["text"] for label, rs in runs.items() if rs},
            "untraced": sum(len(row["untraced"]) for rs in runs.values() for row in rs),
            "failures": Counter(f for rs in runs.values() for row in rs for f in row.get("failures", [])).most_common(6)}


def _reason_kind(reason: str) -> str:
    return re.sub(r"claim c\d+: |\{[^}]*\}|\d+(\.\d+)?|\"[^\"]*\"", "", reason).split(";")[0].strip()


def _summary(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ms = sorted(r["ms"] for r in rows)
    return {"agent": label, "lines": len(rows),
            "verified": sum(r["verified"] for r in rows),
            "first_draft": sum(r["first_draft"] for r in rows),
            "avg_drafts": round(statistics.mean(r["drafts"] for r in rows), 2),
            "p50_ms": ms[len(ms) // 2], "p95_ms": ms[min(len(ms) - 1, int(len(ms) * 0.95))]}


# Live: Ask the match, against a running app, with answers checked against the MCP tools

# Each question with the tool reads that hold its true answer. The answer is right when every true
# value appears in it (a list such as "1-0" or "49% / 51%" counts part by part).
QUESTIONS: list[tuple[str, list[tuple[str, dict[str, Any], str]]]] = [
    ("What is the score?", [("get_match_state", {}, "score")]),
    ("How many expected goals has each team created?", [("get_match_state", {}, "xg")]),
    ("What is the home team's chance of winning right now?", [("get_match_state", {}, "win_probability.home")]),
    ("How is possession split?", [("get_match_state", {}, "possession")]),
    ("How many players does each side have on the pitch?", [("get_match_state", {}, "men")]),
    ("Who has added the most win value so far?", [("get_leverage_table", {}, "rows.0.name")]),
    ("Which player has the most gravity?", [("get_gravity", {}, "rows.0.name")]),
    ("What is Rafael Okafor's top speed?", [("get_player_live", {"player": "KR10"}, "name"),
                                             ("get_player_live", {"player": "KR10"}, "top_speed_kmh")]),
    ("How far has Dani Mensah run?", [("get_player_live", {"player": "KR09"}, "name"),
                                      ("get_player_live", {"player": "KR09"}, "distance_km")]),
    ("What defensive block are Ashford Vale in?", [("get_team_shape", {"team": "away"}, "state")]),
    ("How many shots has Tobias Brandt taken?", [("get_player_live", {"player": "AV09"}, "name"),
                                                 ("get_player_live", {"player": "AV09"}, "shots")]),
    ("What is the away team's chance of winning?", [("get_match_state", {}, "win_probability.away")]),
]
UNANSWERABLE = ["Who will win the league this season?", "How many fans are in the stadium?",
                "Which player has the most yellow cards in their career?"]


def live_analyst(url: str) -> dict[str, Any]:
    import httpx

    http = httpx.Client(base_url=url, timeout=60)
    room = http.post("/api/rooms", json={"start_minute": 70, "speed": 1}).json()["room_id"]
    for _ in range(120):  # the room fast-forwards to minute 70 first; read nothing until it has
        if http.get(f"/api/rooms/{room}").json().get("status") != "catching_up":
            break
        time.sleep(1)
    http.post(f"/api/rooms/{room}/control", json={"action": "pause"})
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    http.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "eval", "version": "1"}}})

    def tool(name: str, args: dict[str, Any]) -> Any:
        r = http.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                      "params": {"name": name, "arguments": {"room": room, **args}}}).json()
        res = r["result"]
        return res.get("structuredContent", {}).get("result", res.get("structuredContent")) or json.loads(res["content"][0]["text"])

    def ask(question: str) -> tuple[dict[str, Any], int]:
        time.sleep(ASK_GAP_S)  # stay under the app's 12 questions a minute
        started = time.perf_counter()
        body = http.post(f"/api/rooms/{room}/ask", json={"question": question}).json()
        return body, round((time.perf_counter() - started) * 1000)

    rows = []
    for question, truths in QUESTIONS:
        expected = [analyst._format(analyst._read(tool(n, a), f), f) for n, a, f in truths]
        body, ms = ask(question)
        answer = body.get("answer", "")
        parts = [p for e in expected for p in re.split(r" / |(?<=\d)-(?=\d)", e)]
        def said(p: str) -> bool:
            if re.search(rf"(?<![\d.]){re.escape(p)}(?![\d])", answer):
                return True
            return p == "0" and re.search(r"\b(no|not any|none|zero)\b", answer.lower()) is not None
        correct = body.get("source") == "analyst" and all(said(p) for p in parts)
        rows.append({"question": question, "expected": expected, "answer": answer, "correct": correct,
                     "source": body.get("source"), "ms": ms,
                     "read": [f"{e['tool']}.{e['field']}" for e in body.get("evidence", [])],
                     "rejections": [s["detail"] for s in body.get("steps", []) if s.get("status") == "reject"]})
    refusals = []
    for question in UNANSWERABLE:
        body, _ = ask(question)
        honest = body.get("source") == "analyst" and not body.get("evidence") and not NUMBER.search(body.get("answer", ""))
        refusals.append({"question": question, "answer": body.get("answer", ""), "honest": honest})
    return {"room": room, "url": url, "questions": rows, "correct": sum(r["correct"] for r in rows),
            "refusals": refusals, "honest": sum(r["honest"] for r in refusals),
            "p50_ms": sorted(r["ms"] for r in rows)[len(rows) // 2]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--analyst", action="store_true", help="only the Ask the match questions, against --url")
    ap.add_argument("--refresh-moments", action="store_true")
    args = ap.parse_args()
    if args.refresh_moments or not MOMENTS_PATH.exists():
        refresh_moments()
    cases = load_cases()
    report: dict[str, Any] = json.loads(REPORT_PATH.read_text(encoding="utf-8")) if REPORT_PATH.exists() else {}
    if args.analyst:
        report["analyst"] = live_analyst(args.url)
        a = report["analyst"]
        print(f"Ask the match: {a['correct']}/{len(a['questions'])} correct, {a['honest']}/{len(a['refusals'])} honest refusals")
        REPORT_PATH.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        return
    report["planted"] = planted(cases)
    report["planted"]["at"] = time.strftime("%Y-%m-%d %H:%M")
    p = report["planted"]
    print(f"planted errors caught {p['caught']}/{p['planted']}, clean lines passed {p['clean_passed']}/{p['clean']}")
    for r in p["rows"]:
        print(f"  {r['caught']:>4}/{r['planted']:<4} {r['check']}")
    if args.live:
        from app.env import load_env

        load_env()
        writers = asyncio.run(live_writers(_sample(cases, LIVE_SAMPLE)))
        writers["at"] = time.strftime("%Y-%m-%d %H:%M")
        report["live"] = writers
        for r in writers["rows"]:
            print(f"  {r['agent']:<22} verified {r['verified']}/{r['lines']}, first draft {r['first_draft']}, "
                  f"p50 {r['p50_ms']} ms")
        print("untraced numbers in published lines:", writers["untraced"])
        try:
            report["analyst"] = live_analyst(args.url)
            a = report["analyst"]
            print(f"Ask the match: {a['correct']}/{len(a['questions'])} correct, {a['honest']}/{len(a['refusals'])} honest refusals")
        except Exception as e:  # the app is not running: keep the writers' results
            print("Ask the match skipped:", e)
    REPORT_PATH.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
