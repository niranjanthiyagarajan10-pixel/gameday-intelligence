"""The card desk: how a key moment becomes a verified on-screen card.

    Narrator drafts a template  ->  Verifier checks it  ->  pass: code fills the slots, card goes live
                                        |
                                        fail: reasons go back to the Narrator (at most 2 retries)
                                        |
                                        still failing, slow or unreachable: the template fallback

Every step is recorded as a trace step, which the dashboard's trace panel shows live.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from agents import narrator
from agents.fallback import CUE_KIND, fallback_cue, moment_time, slots_for
from agents.llm import LLM
from agents.verifier import verify
from engine.models import Audience, Moment, OverlayEvent, Side, template_slots

MAX_RETRIES = 2


@dataclass(frozen=True)
class TraceStep:
    moment_id: str
    audience: str
    agent: str  # Narrator, Verifier, Fallback
    action: str
    status: str  # ok, pass, reject, timeout, error, offline, fallback
    ms: int
    detail: str
    t: float  # match time of the moment

    def to_json(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Written:
    cue: OverlayEvent
    source: str  # "narrator" or "template"
    steps: list[TraceStep]


def name_list(names: dict[str, str], teams: dict[Side, str], extra: Iterable[str] = ()) -> set[str]:
    """Everything the Verifier refuses to see typed: full names, surnames, club names."""
    out = set(names.values()) | set(teams.values()) | set(extra)
    for full in names.values():
        parts = full.split(" ", 1)
        if len(parts) == 2:
            out.add(parts[1])
    return out


class CardDesk:
    def __init__(self, llm: LLM, names: dict[str, str], teams: dict[Side, str], match_id: str,
                 extra_names: Iterable[str] = ()) -> None:
        self.llm = llm
        self.names = names
        self.teams = teams
        self.match_id = match_id
        self.forbidden = name_list(names, teams, extra_names)

    def _status(self, error: str | None) -> str:
        if not self.llm.live:
            return "offline"
        return "timeout" if error and "timed out" in error else "error"

    async def write(self, moment: Moment, audience: Audience) -> Written:
        allowed = slots_for(moment, self.names, self.teams)
        t = moment_time(moment)
        steps: list[TraceStep] = []
        feedback: list[str] | None = None
        previous: str | None = None
        reason = ""
        for attempt in range(1 + MAX_RETRIES):
            result = await self.llm.complete(
                agent="Narrator",
                instructions=narrator.instructions(audience),
                prompt=narrator.prompt(moment, allowed, feedback, previous),
                model=self.llm.strong,
            )
            label = f"draft {attempt + 1}"
            if not result.ok:
                steps.append(TraceStep(moment.moment_id, audience, "Narrator", label, self._status(result.error),
                                       result.ms, result.error or "", t))
                reason = result.error or "no reply"
                break
            steps.append(TraceStep(moment.moment_id, audience, "Narrator", label, "ok", result.ms,
                                   f"{result.backend} {result.model}", t))
            started = time.perf_counter()
            draft = narrator.parse(result.text)
            if draft.error:
                reasons = [draft.error]
            else:
                reasons = verify(draft.template, draft.claims, moment, allowed, self.forbidden, audience).reasons
            took = round((time.perf_counter() - started) * 1000)
            if not reasons:
                steps.append(TraceStep(moment.moment_id, audience, "Verifier", f"check {attempt + 1}", "pass", took,
                                       f"{len(draft.claims)} claims checked against the evidence", t))
                used = template_slots(draft.template)
                cue = OverlayEvent(
                    cue_id=moment.moment_id.replace("-mo-", "-cue-") + f"-{audience}",
                    match_id=self.match_id,
                    t_start=t + 1.0,
                    duration_s=8.0,
                    kind=CUE_KIND[moment.kind],
                    audience=audience,
                    club=moment.team,
                    lang="en",
                    template=draft.template,
                    slots={k: allowed[k] for k in dict.fromkeys(used)},
                    verified=True,
                    source_claims=[c.claim_id for c in draft.claims],
                    evidence_ref=moment.moment_id,
                )
                return Written(cue, "narrator", steps)
            steps.append(TraceStep(moment.moment_id, audience, "Verifier", f"check {attempt + 1}", "reject", took,
                                   "; ".join(reasons), t))
            feedback, previous = reasons, draft.template or previous
            reason = "the Verifier rejected every draft"
        steps.append(TraceStep(moment.moment_id, audience, "Fallback", "template", "fallback", 0, reason, t))
        return Written(fallback_cue(moment, audience, self.names, self.teams, self.match_id), "template", steps)
