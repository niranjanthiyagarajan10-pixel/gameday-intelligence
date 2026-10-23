"""The Analyst agent: answers a fan's question about the live match ("Ask the match").

It explores the match through our MCP server's read-only tools, then answers with a template whose
slots each point at one tool, its arguments and the field to read. Code re-runs those tool calls and
reads the fields to fill the answer, so every number and name in it comes from the match data, never
from the model. If the data cannot answer, the agent must say so.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from agents.verifier import EM_DASH
from engine.models import template_slots
from mcp_server import tools

MAX_CHARS = 520
READ_TOOLS = {fn.__name__: fn for fn in tools.TOOLS if fn.__name__ != "verify_claims"}
PERCENT_KEYS = {"possession", "win_probability", "share", "rate", "press_rate"}

INSTRUCTIONS = """You are the Analyst for Gameday Intelligence. A fan asks a question about the live match.
Use the match tools to find the answer; always pass room="{room}".

Answer with JSON only, no prose and no code fence:
{"answer": "...", "slots": {"s1": {"tool": "get_player_live", "args": {"player": "Okafor"}, "field": "top_speed_kmh"}}, "limits": "..."}

Rules:
1. answer is a template. Every number and every player or club name is a slot like {s1}. Each slot names
   the tool, its arguments (without room) and the field of the tool's result to read. Fields can be paths:
   "rows.0.name", "win_probability.home", "shots.2.xg". Never type a digit or a name yourself.
2. Use only what the tools return. If they cannot answer the question, say so plainly, with no slots,
   and say what you can answer instead.
3. One to three short sentences, plain words, for a {audience} fan. No em dashes. Never use he, him, his, she or her for a player: use the player's slot or they.
   Scores, minutes, percentages and counts are numbers too: read the score from get_match_state "score",
   never write it yourself.
4. limits: one short phrase on what the data does not cover, or "".
"""


def instructions(room: str, audience: str) -> str:
    return INSTRUCTIONS.replace("{room}", room).replace("{audience}", "casual" if audience == "casual" else "data-hungry")


def parse(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    body = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = body.find("{"), body.rfind("}")
    try:
        data = json.loads(body[start:end + 1]) if start >= 0 else None
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("answer"), str):
        return None
    if not isinstance(data.get("slots", {}), dict):
        return None
    return {"answer": data["answer"].strip(), "slots": data.get("slots") or {}, "limits": str(data.get("limits") or "")}


def _read(value: Any, path: str) -> Any:
    for part in [p for p in path.split(".") if p]:
        if isinstance(value, list):
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise KeyError(part)
    return value


def _format(value: Any, path: str) -> str:
    keys = set(path.split("."))
    if isinstance(value, bool) or value is None:
        raise ValueError("not a value a fan can read")
    if isinstance(value, float):
        if keys & PERCENT_KEYS and 0.0 <= value <= 1.0:
            return f"{round(value * 100)}%"
        return f"{value:.1f}" if abs(value) >= 10 else f"{value:.2f}"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        if "score" in keys and len(value) == 2 and all(isinstance(v, int) for v in value):
            return f"{value[0]}-{value[1]}"
        if keys & PERCENT_KEYS and all(isinstance(v, float) for v in value):
            return " / ".join(f"{round(v * 100)}%" for v in value)
        return " / ".join(str(v) for v in value)
    text = str(value)
    if len(text) > 120:
        raise ValueError("too long to quote")
    return text


def resolve(room: Any, slots: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, Any]], list[str]]:
    """Re-run every slot's tool call and read its field. Returns values, evidence rows and problems."""
    values: dict[str, str] = {}
    evidence: list[dict[str, Any]] = []
    problems: list[str] = []
    for name, spec in slots.items():
        if not isinstance(spec, dict):
            problems.append(f"slot {name} needs tool, args and field")
            continue
        tool = READ_TOOLS.get(str(spec.get("tool", "")))
        args = {k: v for k, v in (spec.get("args") or {}).items() if k != "room"} if isinstance(spec.get("args"), dict) else {}
        field = str(spec.get("field", ""))
        if tool is None:
            problems.append(f"slot {name}: unknown tool {spec.get('tool')!r}")
            continue
        try:
            result = tool(room, **args)
            values[name] = _format(_read(result, field), field)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            problems.append(f"slot {name}: {tool.__name__}.{field} could not be read ({type(e).__name__})")
            continue
        evidence.append({"slot": name, "tool": tool.__name__, "args": args, "field": field, "value": values[name]})
    return values, evidence, problems


def check(answer: str, slots: dict[str, Any], names: Iterable[str], question: str = "") -> list[str]:
    """Names the fan typed in the question may be repeated; every other name must come from a tool."""
    names = [n for n in names if n.lower() not in question.lower()]
    reasons = []
    try:
        used = set(template_slots(answer))
    except ValueError as e:
        return [str(e)]
    if used != set(slots):
        reasons.append("every slot in the answer needs exactly one spec in slots, and every spec must be used")
    literal = re.sub(r"\{[^{}]*\}", " ", answer)
    if re.search(r"\d", literal):
        reasons.append("numbers must be slots read from a tool")
    for name in sorted({n for n in names if n and len(n) >= 3}, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", literal):
            reasons.append(f'names must be slots read from a tool: remove "{name}"')
            break
    if EM_DASH in answer:
        reasons.append("no em dashes")
    if len(literal) > MAX_CHARS:
        reasons.append("too long")
    return reasons
