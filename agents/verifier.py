"""The Verifier: deterministic checks on everything an agent writes, before a fan sees it.

It is code, not a model, so it cannot be talked out of a check. A draft passes only if:
- the template's slots are known for this moment, and the ones the moment needs are there;
- it types no number and no player or club name (those must be slots that code fills);
- every claim it declares matches the evidence (direction, size, minute);
- every claim it implies through its wording matches the evidence too ("equaliser" needs a level
  score, "late" needs the 75th minute or later), and it names no detail the evidence cannot support
  (a header, a penalty, an assist, a career record, an injury).

Each failure comes back as a short reason the author agent can act on.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from engine.models import Claim, Moment, template_slots

EM_DASH = chr(0x2014)
MAX_CHARS = {"casual": 240, "analyst": 320}
# "56 m meters", "74% percent": a unit written after a slot that already has one.
DOUBLE_UNIT = re.compile(r"\d\s?(m|km/h|%|km)\s+(meters?|metres?|percent|per cent|kilometres?|kilometers?|km/h|kph)\b",
                         re.IGNORECASE)
GOAL_KINDS = {"goal", "low_xg_goal"}
# Players are fictional and their genders unknown: agents use the player's slot or "they".
GENDERED = re.compile(r"\b(he|him|his|himself|she|her|hers|herself)\b", re.IGNORECASE)

REQUIRED_SLOTS: dict[str, set[str]] = {
    "goal": {"player", "score"},
    "low_xg_goal": {"player", "score"},
    "red_card": {"player"},
    "big_chance": {"player", "xg"},
    "top_speed": {"player", "speed"},
    "shape_change": {"team", "shape"},
    "leverage_swing": {"player"},
}

# Details the evidence for a moment never contains, so a draft may not state them.
UNVERIFIABLE = [
    r"\bhead(s|er|ers|ed|ing)?\b", r"volley", r"free[- ]kick", r"penalt", r"corner", r"long[- ]range", r"screamer",
    r"tap[- ]in", r"curl", r"left[- ]foot", r"right[- ]foot", r"assist", r"\bcross", r"rebound", r"deflect",
    r"hat[- ]trick", r"\bbrace\b", r"second goal", r"third goal", r"season", r"career", r"all[- ]time",
    r"history", r"injur", r"\bvar\b", r"offside", r"crowd", r"stadium", r"manager", r"weather",
]


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reasons: list[str]


def _score(m: Moment) -> tuple[int, int] | None:
    raw = m.evidence.get("score")
    if not isinstance(raw, str) or "-" not in raw:
        return None
    h, a = raw.split("-", 1)
    return int(h), int(a)


def _margin(m: Moment) -> int | None:
    """Goals ahead for the moment's team after it, negative when behind."""
    s = _score(m)
    if s is None or m.team is None:
        return None
    return s[0] - s[1] if m.team == "home" else s[1] - s[0]


def _xg(m: Moment) -> float | None:
    v = m.evidence.get("xg")
    return None if v is None else float(v)


def _shape(m: Moment) -> set[str]:
    return {str(m.evidence.get("to", "")), str(m.evidence.get("from", ""))}


def _chaos(m: Moment) -> bool:
    if m.kind != "control_flip":
        return False
    return m.evidence.get("now_in_control") == "nobody" or float(m.evidence.get("chaos_index", 0)) >= 1.4


# Phrase -> (what it claims, test on the moment). A test returning None means it cannot be checked.
IMPLIED: list[tuple[str, str, Any]] = [
    (r"\bequali[sz]|\blevel\b|all square", "the score is level", lambda m: None if _margin(m) is None else _margin(m) == 0),
    (r"\b(lead|leads|ahead|in front)\b", "the team leads", lambda m: None if _margin(m) is None else _margin(m) > 0),
    (r"\bwinner\b|winning goal", "a late winner", lambda m: None if _margin(m) is None else (_margin(m) == 1 and m.minute >= 80)),
    (r"\blate\b", "it came late", lambda m: m.minute >= 75),
    (r"\bearly\b", "it came early", lambda m: m.minute <= 15),
    (r"comeback|fight ?back|turn(s|ed)? (it|this|the game) around",
     "the team came from behind", lambda m: None if _margin(m) is None else (_margin(m) - 1 < 0 and m.kind in GOAL_KINDS)),
    (r"big chance|golden chance|should have scored|sitter|clear[- ]cut", "a big chance",
     lambda m: None if _xg(m) is None else _xg(m) >= 0.3),
    (r"against the odds|unlikely|improbable|wonder goal|low[- ]percentage|long odds", "a low-chance goal",
     lambda m: None if _xg(m) is None else _xg(m) < 0.1),
    (r"red card|sent off|ten men|down to ten", "a red card", lambda m: m.kind == "red_card"),
    (r"chaos(?! index)|chaotic|scrappy|end[- ]to[- ]end", "the match turned chaotic", _chaos),
    (r"low block", "a low block", lambda m: "low_block" in _shape(m)),
    (r"high press", "a high press", lambda m: "high_press" in _shape(m)),
    (r"mid block", "a mid block", lambda m: "mid_block" in _shape(m)),
    (r"fastest|top speed|quickest", "a top speed", lambda m: m.kind == "top_speed"),
    (r"\bopener\b|opening goal|first goal", "the first goal of the match",
     lambda m: None if _score(m) is None else sum(_score(m)) == 1),
    (r"doubles? (the|their|its) lead|two[- ]goal", "a two-goal lead", lambda m: None if _margin(m) is None else _margin(m) == 2),
    (r"\bdominat", "one team in control", lambda m: m.kind == "control_flip" and m.evidence.get("now_in_control") in ("home", "away")),
]


def _check_claim(c: Claim, m: Moment, used: set[str], team_name: str = "", rival_name: str = "") -> str | None:
    # A claim tied to a slot the text leaves out is checked on its facts all the same.
    ev = m.evidence
    metric = c.metric.lower()
    if metric == "win_probability":
        if "wp_after" in ev and "wp_before" in ev and c.direction in ("up", "down"):
            moved_up = float(ev["wp_after"]) > float(ev["wp_before"])
            # Win chance is the moment's team's unless the claim names the other side.
            rival = {"home", "away"} - {str(m.team)}
            about_rival = c.subject.strip().lower() in rival | ({rival_name.lower()} if rival_name else set())
            up = not moved_up if about_rival else moved_up
            if (c.direction == "up") != up:
                return f"claim {c.claim_id}: win chance did not go {c.direction}"
        return None
    if metric == "score":
        margin = _margin(m)
        if margin is None:
            return f"claim {c.claim_id}: no score in the evidence"
        # "up" on a goal means the team scored; otherwise it means the team leads.
        if c.direction == "up" and m.kind in GOAL_KINDS:
            return None
        expect = "up" if margin > 0 else "level" if margin == 0 else "down"
        return None if c.direction in (None, expect) else f"claim {c.claim_id}: the team is not {c.direction}"
    if metric == "xg":
        xg = _xg(m)
        if xg is None:
            return f"claim {c.claim_id}: no xG in the evidence"
        if c.direction == "up" and xg < 0.3:
            return f"claim {c.claim_id}: an xG of {xg:.2f} is not a big chance"
        if c.direction == "down" and xg >= 0.15:
            return f"claim {c.claim_id}: an xG of {xg:.2f} is not a low chance"
        return None
    if metric == "minute":
        return None if c.minute is None or abs(c.minute - m.minute) <= 1 else f"claim {c.claim_id}: wrong minute"
    if metric == "leverage":
        if c.direction in ("up", "down") and (m.leverage >= 0) != (c.direction == "up"):
            return f"claim {c.claim_id}: leverage went the other way"
        return None
    if metric == "speed":
        return None if m.kind == "top_speed" else f"claim {c.claim_id}: this moment is not a top speed"
    if metric == "shape":
        # The subject may name the shape ("low_block") or just the team the claim is about.
        if not c.subject or c.subject in _shape(m) or c.subject.lower() in ("team", "home", "away", str(m.team)):
            return None
        return f"claim {c.claim_id}: the shape was not {c.subject}"
    if metric == "control":
        return None if m.kind == "control_flip" else f"claim {c.claim_id}: this moment is not a control change"
    if metric == "red_card":
        return None if m.kind == "red_card" else f"claim {c.claim_id}: there was no red card"
    return f"claim {c.claim_id}: unknown metric {c.metric}"


def verify(
    template: str,
    claims: list[Claim],
    moment: Moment,
    allowed: dict[str, str],
    names: Iterable[str],
    audience: str = "casual",
) -> Verdict:
    """Check a draft against the moment it describes. `allowed` maps slot names to their values."""
    reasons: list[str] = []
    try:
        used = template_slots(template)
    except ValueError as e:
        return Verdict(False, [str(e)])
    unknown = sorted(set(used) - allowed.keys())
    if unknown:
        reasons.append("unknown slots " + ", ".join(f"{{{s}}}" for s in unknown) + "; use only the slots given")
    missing = sorted(REQUIRED_SLOTS.get(moment.kind, set()) - set(used))
    if missing:
        reasons.append("this moment needs " + ", ".join(f"{{{s}}}" for s in missing))

    literal = re.sub(r"\{[^{}]*\}", " ", template)
    if re.search(r"\d", literal):
        reasons.append("numbers must be slots, never typed")
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        if len(name) >= 3 and re.search(rf"\b{re.escape(name)}\b", literal):
            reasons.append(f'names must be slots: remove "{name}"')
            break
    if EM_DASH in template:
        reasons.append("no em dashes")
    if GENDERED.search(literal):
        reasons.append("never use he, him, his, she or her for a player: use the player's slot or they")
    if re.search(r"\}['’]s\b", template):
        reasons.append("never add 's to a slot: write \"the win chance of {team}\"")
    if not literal.strip():
        reasons.append("the template is empty")

    text = literal.lower()
    for pattern in UNVERIFIABLE:
        if re.search(pattern, text):
            word = re.search(pattern, text).group(0)  # type: ignore[union-attr]
            reasons.append(f'"{word}" is not in the evidence; describe only what the evidence shows')
    for pattern, meaning, test in IMPLIED:
        if re.search(pattern, text):
            result = test(moment)
            if result is None:
                reasons.append(f"the wording implies {meaning}, which the evidence cannot confirm")
            elif not result:
                reasons.append(f"the wording implies {meaning}, but the evidence says otherwise")

    for c in claims:
        problem = _check_claim(c, moment, set(used), allowed.get("team", ""), allowed.get("rival", ""))
        if problem:
            reasons.append(problem)

    if not reasons:
        rendered = template.format(**{k: allowed[k] for k in used})
        if len(rendered) > MAX_CHARS.get(audience, 240):
            reasons.append(f"too long: keep it under {MAX_CHARS.get(audience, 240)} characters")
        if DOUBLE_UNIT.search(rendered):
            reasons.append("a slot already carries its unit; do not write a unit word after it")
    return Verdict(not reasons, reasons)
