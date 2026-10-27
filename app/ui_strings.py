"""Translate the interface once, ahead of time: `python -m app.ui_strings`.

Collects every interface string from the web app (each `t("...")` and `tx("...")`, every value in a
`labels({...})` map, label-like fields and row labels, and the box score labels the engine sends),
then the Personalizer on Foundry translates them into every language in batches. Each translation is
checked: the same {placeholders}, the same digits, no em dash. One that fails stays in English.
Writes web/src/i18n/<lang>.json. Safe to re-run: kept translations are reused.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from pathlib import Path

from agents.personalizer import EM_DASH, LANGS

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "src"
OUT = WEB / "i18n"
BATCH = 8
SKIP_FILES = {"i18n.ts", "Crest.tsx", "stadium.ts"}

CALL = re.compile(r'\bt[x]?\(\s*"((?:[^"\\]|\\.)+)"')
LABELS = re.compile(r"labels\(\{(.*?)\}\)", re.S)
VALUE = re.compile(r':\s*"((?:[^"\\]|\\.)+)"')
FIELD = re.compile(r'\b(?:label|name|blurb|title):\s*"([A-Z][^"]+)"')
ROW = re.compile(r'\[\s*(?:"[a-z_]+",\s*)?"([A-Z][^"]*[a-z][^"]*)"\s*[,\]]')
PH = re.compile(r"\{\w+\}")
DIG = re.compile(r"\d")

INSTRUCTIONS = """You translate the interface of Gameday Intelligence, a live football match companion app with
a black broadcast-style dashboard. Items are button labels, panel titles, stat names, hints and short notes.

Rules:
1. Keep every placeholder in curly braces exactly, for example {n} or {club}.
2. Keep every digit exactly as it is.
3. Keep these in English: Gameday Intelligence, Match Theatre, xG, xT, MCP, Foundry, Azure, AI, GK, DF, MF, FW, km/h, HT, FT.
4. Use the natural football and sports broadcast terms of the language. Keep each item about as short as the
   English: these are interface labels. Match the English capitalisation style where the language allows.
5. No em dashes. Reply with JSON only: {"items": ["...", "..."]}, the same number of items in the same order.
"""


def collect() -> list[str]:
    found: set[str] = set()
    for f in list(WEB.rglob("*.tsx")) + list(WEB.rglob("*.ts")):
        if f.name in SKIP_FILES:
            continue
        s = f.read_text(encoding="utf-8")
        found.update(m.group(1) for m in CALL.finditer(s))
        for block in LABELS.finditer(s):
            found.update(m.group(1) for m in VALUE.finditer(block.group(1)))
        if f.suffix == ".tsx":
            found.update(m.group(1) for m in FIELD.finditer(s))
            found.update(m.group(1) for m in ROW.finditer(s))
    box = (ROOT / "engine" / "boxscore.py").read_text(encoding="utf-8")
    found.update(re.findall(r'"label": "([^"]+)"', box))
    strings = {x.replace('\\"', '"') for x in found}
    return sorted(x for x in strings if re.search(r"[A-Za-z]{2}", x) and "/api" not in x and "var(" not in x)


def ok(src: str, out: str) -> bool:
    return (Counter(PH.findall(src)) == Counter(PH.findall(out)) and Counter(DIG.findall(src)) == Counter(DIG.findall(out))
            and EM_DASH not in out and 0 < len(out) <= 3 * len(src) + 30)


async def main() -> None:
    from agents.llm import LLM
    from app.env import load_env

    strings = collect()
    print(f"{len(strings)} interface strings", flush=True)
    load_env()
    llm = LLM.from_env()
    if not llm.live:
        raise SystemExit("no Foundry endpoint configured")
    await llm.warm()
    OUT.mkdir(parents=True, exist_ok=True)

    async def batch(lang: str, chunk: list[str]) -> list[str | None]:
        prompt = json.dumps({"language": LANGS[lang], "items": chunk}, ensure_ascii=False)
        res = await llm.complete(agent="Personalizer", instructions=INSTRUCTIONS, prompt=prompt, model=llm.fast)
        if not res.ok or not res.text:
            return [None] * len(chunk)
        try:
            items = json.loads(res.text[res.text.find("{"):res.text.rfind("}") + 1]).get("items")
        except (ValueError, AttributeError):
            return [None] * len(chunk)
        if not isinstance(items, list) or len(items) != len(chunk):
            return [None] * len(chunk)
        return [x.strip() if isinstance(x, str) else None for x in items]

    for lang in LANGS:
        path = OUT / f"{lang}.json"
        kept = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        table = {k: v for k, v in kept.items() if k in strings}
        for attempt in range(4):  # failed items get another try in smaller batches
            todo = [s for s in strings if s not in table]
            size = BATCH if attempt == 0 else max(2, BATCH // (2 * attempt))
            chunks = [todo[i:i + size] for i in range(0, len(todo), size)]
            results = await asyncio.gather(*(batch(lang, c) for c in chunks))
            for chunk, outs in zip(chunks, results):
                for src, out in zip(chunk, outs):
                    if out and ok(src, out):
                        table[src] = out
        path.write_text(json.dumps(dict(sorted(table.items())), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{lang}: {len(table)}/{len(strings)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
