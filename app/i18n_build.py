"""Translate every template and every slot word once, ahead of time: `python -m app.i18n_build`.

1. Collect: play each scenario offline (no model, so every story is the template) and record every
   template that is filled, plus the words code puts into slots. Card templates come from
   agents/fallback.py.
2. Translate: the Personalizer writes each one in every language, in batches, on Foundry.
3. Check: each translation must pass the same check as live text (agents/personalizer.check): the
   same slots, no typed digits or names. A translation that fails is retried on its own, then left
   out, so that template stays in English.

Writes data/i18n/templates.json and data/i18n/values.json. Safe to re-run: kept translations are reused.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from typing import Any

from agents import fallback, i18n, personalizer, story
from agents.personalizer import LANGS

BATCH = 12
WORD = re.compile(r"^[a-z][a-z' -]{1,40}$")  # lower case words only: proper names and form strings stay as they are

BATCH_INSTRUCTIONS = """You are the Personalizer for Gameday Intelligence, a live football match companion.
You translate short on-screen lines for fans into another language.

Rules:
1. Keep every slot in curly braces exactly as it is, the same number of times. Never translate, rename,
   add or drop a slot.
2. Never type a digit, a player name or a club name.
3. Keep the meaning; add nothing. Never use he, him, his, she or her for a player.
4. Sound like a natural sports broadcast line in the language. No em dashes.
5. Reply with JSON only: {"items": ["...", "..."]}, the same number of items in the same order.
"""

WORD_INSTRUCTIONS = """Translate short football terms for an on-screen match companion. Each item is a short
phrase that will be placed inside a sentence (for example "a big chance", "low block", "interception").
Use the natural football term in the language, lower case unless the language requires otherwise.
No digits. Reply with JSON only: {"items": ["...", "..."]}, the same number of items in the same order.
"""


def collect() -> tuple[set[str], set[str], set[str]]:
    """Every template fans can see in English, every word code puts in a slot, and every name."""
    from app import explain as explain_facts
    from app import room as room_mod
    from app.room import MatchRoom, RoomConfig
    from engine.league import build_league
    from engine.scenarios import STORIES, path_for

    templates: set[str] = set()
    values: set[str] = set()
    names: set[str] = set()
    for by_aud in fallback.TEMPLATES.values():
        templates.update(by_aud.values())
    values.update(fallback.SHAPES.values())
    from app.explain import OUTCOME_WORD
    from engine.explain import RESTARTS
    values.update(RESTARTS.values())
    values.update(OUTCOME_WORD.values())
    values.update(("a tackle", "an interception", "a loose ball"))
    templates.add(room_mod.ASK_FALLBACK)

    real_fill = story.fill

    def recording_fill(template: str, facts: dict[str, str]) -> str:
        templates.add(template)
        for v in facts.values():
            if isinstance(v, str) and WORD.match(v):
                values.add(v)
        return real_fill(template, facts)

    story.fill = recording_fill  # type: ignore[assignment]
    try:
        league = build_league()
        for s in STORIES:
            room = MatchRoom(f"i18n-{s.scenario_id}", league,
                             RoomConfig.for_scenario(str(path_for(s.scenario_id)), half_s=2700.0))
            names.update(room.names.values())
            names.update(room.teams.values())

            async def stories(r: MatchRoom = room) -> None:
                await r.preview()
                for minute in (10, 30, 45, 60, 80, 90):
                    r.fast_forward(minute * 60.0)
                    if r.feed.finished:
                        r.status = "full_time"
                    await r.brief()
                    await r.postgame()
                    await r.write_deep()
                    await r.reel()
                for shot in r.live.shots:
                    page = r.shot(shot.event_id)
                    if page and page["clip"] and explain_facts.explainable(page["shot"]):
                        await r.explain(shot.event_id)

            asyncio.run(stories())
        # Every Explainer line the template can produce, for moves of up to five beats.
        from agents import explainer
        kinds = ("won", "foul_won", "restart", "pass", "carry", "tackle_beaten", "shot")
        for n in range(1, 6):
            for kind in kinds:
                for with_bypass in (True, False):
                    facts = {f"b{n}_bypassed": "x"} if with_bypass else {}
                    templates.add(explainer._line(kind, n, facts))
        for space in (True, False):
            templates.add(explainer.fallback({"space": "x"} if space else {}, {"kinds": []})["why"])
        from agents import newsdesk
        from app.newsdesk import matches
        for m in matches():
            parts = newsdesk.fallback(m["facts"], m["truths"])
            for v in parts.values():
                for tpl in v if isinstance(v, list) else [v]:
                    recording_fill(tpl, m["facts"])
    finally:
        story.fill = real_fill  # type: ignore[assignment]
    values = {v for v in values if v not in names}
    return templates, values, names


async def _translate(llm: Any, items: list[str], lang: str, instructions: str) -> list[str | None]:
    prompt = json.dumps({"language": LANGS[lang], "items": items}, ensure_ascii=False)
    res = await llm.complete(agent="Personalizer", instructions=instructions, prompt=prompt, model=llm.fast)
    if not res.ok or not res.text:
        return [None] * len(items)
    text = res.text
    try:
        data = json.loads(text[text.find("{"):text.rfind("}") + 1])
        out = data.get("items")
    except (ValueError, AttributeError):
        return [None] * len(items)
    if not isinstance(out, list) or len(out) != len(items):
        return [None] * len(items)
    return [x.strip() if isinstance(x, str) and x.strip() else None for x in out]


async def translate_all(templates: set[str], values: set[str], names: set[str]) -> None:
    from agents.llm import LLM
    from app.env import load_env

    load_env()
    llm = LLM.from_env()
    if not llm.live:
        raise SystemExit("no Foundry endpoint configured")
    await llm.warm()
    i18n.ROOT.mkdir(parents=True, exist_ok=True)
    kept_t = json.loads(i18n.TEMPLATES_FILE.read_text(encoding="utf-8")) if i18n.TEMPLATES_FILE.exists() else {}
    kept_v = json.loads(i18n.VALUES_FILE.read_text(encoding="utf-8")) if i18n.VALUES_FILE.exists() else {}
    tpl_list, val_list = sorted(templates), sorted(values)
    for lang in LANGS:
        done_t = {k: v for k, v in kept_t.get(lang, {}).items() if k in templates}
        todo = [t for t in tpl_list if t not in done_t]
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            outs = await _translate(llm, chunk, lang, BATCH_INSTRUCTIONS)
            for src, out in zip(chunk, outs):
                if out is not None and not personalizer.check(src, out, names):
                    done_t[src] = out
        for src in [t for t in todo if t not in done_t]:  # one at a time, with the live Personalizer prompt
            for _ in range(2):
                res = await llm.complete(agent="Personalizer", instructions=personalizer.INSTRUCTIONS,
                                         prompt=personalizer.prompt(src, lang, "fan"), model=llm.fast)
                out = personalizer.parse(res.text) if res.ok else None
                if out is not None and not personalizer.check(src, out, names):
                    done_t[src] = out
                    break
        done_v = {k: v for k, v in kept_v.get(lang, {}).items() if k in values}
        todo_v = [v for v in val_list if v not in done_v]
        for i in range(0, len(todo_v), BATCH * 2):
            chunk = todo_v[i:i + BATCH * 2]
            outs = await _translate(llm, chunk, lang, WORD_INSTRUCTIONS)
            for src, out in zip(chunk, outs):
                if out is not None and not personalizer.DIGITS.search(out) and "{" not in out:
                    done_v[src] = out
        kept_t[lang], kept_v[lang] = done_t, done_v
        print(f"{lang}: {len(done_t)}/{len(tpl_list)} templates, {len(done_v)}/{len(val_list)} words", flush=True)
        i18n.TEMPLATES_FILE.write_text(json.dumps(kept_t, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        i18n.VALUES_FILE.write_text(json.dumps(kept_v, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def main() -> None:
    templates, values, names = collect()
    print(f"collected {len(templates)} templates and {len(values)} slot words", flush=True)
    if "--collect-only" in sys.argv:
        for t in sorted(templates)[:20]:
            print(" ", t)
        print(sorted(values))
        return
    asyncio.run(translate_all(templates, values, names))


if __name__ == "__main__":
    main()
