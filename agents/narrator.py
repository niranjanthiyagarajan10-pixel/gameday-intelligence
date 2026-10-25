"""The Narrator agent: turns one key moment into one on-screen line, written as a template.

It sees the evidence and the formatted slot values so it understands the moment, but it writes
only slot names. Code fills the slots, and the Verifier checks the draft before anyone sees it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from agents.verifier import MAX_CHARS, REQUIRED_SLOTS
from engine.models import Claim, Moment

CLAIM_METRICS = ("win_probability", "score", "xg", "minute", "leverage", "speed", "shape", "control", "red_card")

INSTRUCTIONS = """You are the Narrator for Gameday Intelligence, a live football match companion.
You turn one key moment into one short line shown on screen next to the match.

Rules:
1. Write a TEMPLATE, not finished text. Every number and every name is a slot in curly braces,
   taken only from the slots in the evidence pack, for example {player}, {team}, {xg}.
   Never type a digit, a player name or a club name yourself. Code fills the slots.
2. Say why the moment matters, not only what happened.
3. Describe only what the evidence shows. Never mention headers, volleys, penalties, set pieces,
   assists, crosses, the season, careers, records, injuries, the crowd or the manager.
4. Words such as equaliser, lead, late, early, comeback, big chance, against the odds, chaos,
   low block and high press are claims. Use one only when the evidence supports it.
5. Plain sentences. No em dashes, no emoji, no hype words. Never use he, him, his, she or her for a player: use the player's slot or they. Never add 's to a slot (club names
   can end in s): write "the win chance of {team}", not "{team}'s win chance".
6. Reply with JSON only, no prose and no code fence:
   {"template": "...", "claims": [{"metric": "...", "subject": "...", "direction": "up", "slot": "..."}]}
   Claim metrics: win_probability, score, xg, minute, leverage, speed, shape, control, red_card.
   direction is up, down or level. slot names the slot that carries the claim's number, if any.
   Meanings: win_probability is the win chance of the moment's team (subject "team"), up or down.
   score up means the team scored, level means the scores are level after, down means the team trails.
   xg up means a big chance (0.30 or more), down means a low chance. List only claims your text makes.
   Chaotic, scrappy and end to end need evidence now_in_control "nobody". A chaos index slot is a number,
   not permission to call the match chaotic. Lead, level and equaliser need a score in the evidence.
"""

AUDIENCE = {
    "casual": "Audience: a casual fan. One or two short sentences, at most {limit} characters once the slots are "
              "filled. Everyday words. The only metrics a casual fan hears about are chance quality and win chance.",
    "analyst": "Audience: an analyst. Lead with the numbers that explain the moment: xG, the win probability change, "
               "leverage, line height or pressers. At most {limit} characters once the slots are filled.",
}


def instructions(audience: str) -> str:
    return INSTRUCTIONS + "\n" + AUDIENCE[audience].format(limit=MAX_CHARS[audience])


def prompt(moment: Moment, slots: dict[str, str], feedback: list[str] | None = None, previous: str | None = None) -> str:
    pack: dict[str, object] = {
        "moment": {"kind": moment.kind, "minute": moment.minute, "leverage": round(moment.leverage, 3)},
        "evidence": moment.evidence,
        "slots": slots,
        "required_slots": sorted(REQUIRED_SLOTS.get(moment.kind, set())),
    }
    if feedback:
        pack["previous_attempt"] = {"template": previous, "rejected_because": feedback}
        pack["task"] = "Rewrite the template so it passes every check above."
    return json.dumps(pack, ensure_ascii=False)


@dataclass
class Draft:
    template: str = ""
    claims: list[Claim] = field(default_factory=list)
    error: str | None = None


def parse(text: str | None) -> Draft:
    """The model's JSON reply as a template and claims, or an error the Narrator can fix."""
    if not text:
        return Draft(error="empty reply")
    body = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return Draft(error="reply was not JSON")
    try:
        data = json.loads(body[start:end + 1])
    except json.JSONDecodeError:
        return Draft(error="reply was not valid JSON")
    template = data.get("template")
    if not isinstance(template, str) or not template.strip():
        return Draft(error="no template in the reply")
    claims = []
    for i, raw in enumerate(data.get("claims") or []):
        if not isinstance(raw, dict):
            continue
        direction = raw.get("direction")
        minute = raw.get("minute")
        try:
            claims.append(Claim(
                claim_id=f"c{i + 1}",
                metric=str(raw.get("metric", "")),
                subject=str(raw.get("subject", "")),
                slot=raw.get("slot") or None,
                direction=direction if direction in ("up", "down", "level") else None,
                minute=int(minute) if isinstance(minute, int | float) and 0 <= minute <= 130 else None,
            ))
        except ValueError:
            return Draft(error=f"claim {i + 1} is malformed")
    return Draft(template=template.strip(), claims=claims)
