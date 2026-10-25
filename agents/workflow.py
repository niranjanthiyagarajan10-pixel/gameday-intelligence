"""The card desk as a Microsoft Agent Framework workflow.

    moment ─► Dispatch ─┬─► Narrator (casual)  ──┐   each: draft ─► Verifier ─► retry or template
                        └─► Narrator (analyst) ──┴─► Settle ─► Personalizer (es, hi) ─► card

Dispatch fans the moment out to two Narrator executors that run in parallel, one per audience. Each
runs the draft, verify and retry loop of `CardDesk.write`. Settle fans their verified cues back in, and
the Personalizer writes them in Spanish and Hindi when a model is live. The workflow yields one
`CardResult`. Agent Framework traces every executor and model call with OpenTelemetry (`agents/tracing.py`).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler

from agents.desk import CardDesk, Written
from agents.personalizer import LANGS
from engine.models import Moment


@dataclass
class CardJob:
    moment: Moment
    translate: bool


@dataclass
class Drafted:
    job: CardJob
    written: Written


@dataclass
class Settled:
    job: CardJob
    written: list[Written]


@dataclass
class CardResult:
    moment_id: str
    written: list[Written]  # one per audience: the Narrator's verified cue, or its template
    translated: list[Written] = field(default_factory=list)  # Personalizer cues that passed their check


class Dispatch(Executor):
    @handler
    async def start(self, job: CardJob, ctx: WorkflowContext[CardJob]) -> None:
        await ctx.send_message(job)


class Narrate(Executor):
    def __init__(self, desk: CardDesk, audience: str) -> None:
        super().__init__(id=f"narrator_{audience}")
        self.desk = desk
        self.audience = audience

    @handler
    async def draft(self, job: CardJob, ctx: WorkflowContext[Drafted]) -> None:
        written = await self.desk.write(job.moment, self.audience)  # type: ignore[arg-type]
        await ctx.send_message(Drafted(job, written))


class Settle(Executor):
    @handler
    async def settle(self, drafts: list[Drafted], ctx: WorkflowContext[Settled]) -> None:
        order = {"casual": 0, "analyst": 1}
        written = sorted((d.written for d in drafts), key=lambda w: order.get(w.cue.audience, 9))
        await ctx.send_message(Settled(drafts[0].job, written))


class Personalize(Executor):
    def __init__(self, desk: CardDesk) -> None:
        super().__init__(id="personalizer")
        self.desk = desk

    @handler
    async def translate(self, settled: Settled, ctx: WorkflowContext[None, CardResult]) -> None:
        translated: list[Written] = []
        if settled.job.translate:
            t = settled.written[0].cue.t_start - 1.0
            translated = list(await asyncio.gather(*(self.desk.translate(w.cue, lang, t)
                                                     for lang in LANGS for w in settled.written)))
        await ctx.yield_output(CardResult(settled.job.moment.moment_id, settled.written, translated))


def card_workflow(desk: CardDesk) -> Workflow:
    """One workflow per match room: the desk carries that match's names and teams."""
    dispatch = Dispatch(id="dispatch")
    casual, analyst = Narrate(desk, "casual"), Narrate(desk, "analyst")
    settle, personalize = Settle(id="settle"), Personalize(desk)
    return (
        WorkflowBuilder(name="card_desk", description="Key moment to verified card in three languages",
                        start_executor=dispatch)
        .add_fan_out_edges(dispatch, [casual, analyst])
        .add_fan_in_edges([casual, analyst], settle)
        .add_edge(settle, personalize)
        .build()
    )


async def run_card(workflow: Workflow, moment: Moment, translate: bool) -> CardResult:
    result = await workflow.run(CardJob(moment, translate))
    outputs = [o for o in result.get_outputs() if isinstance(o, CardResult)]
    if not outputs:
        raise RuntimeError(f"card workflow ended without a card: {result.get_final_state()}")
    return outputs[0]
