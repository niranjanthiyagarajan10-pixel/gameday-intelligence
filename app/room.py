"""Match rooms: one simulated match running live, fanned out to every connected viewer.

The main room is the shared broadcast. Private rooms let one viewer (a judge following a jump
link, say) start a replay from any minute without changing what anyone else sees.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from agents import story
from agents.desk import CardDesk, TraceStep, name_list
from agents.workflow import card_workflow, run_card
from agents.llm import LLM
from agents import analyst, commentator, deep, newsdesk, personalizer, postgame, preview, recap, summarizer
from agents.personalizer import LANGS
from app import matchday
from app.blueprint import build_blueprint
from app.league import season as league_season
from app.speech import Speech
from app.payloads import (
    analyst_message,
    anim_event,
    card_message,
    clip_event,
    event_record,
    frame_message,
    player_summary,
    roster,
    shot_dict,
    stats_message,
)
from engine.feed import Feed, SimulatorFeed
from engine.league import League
from engine.live import LiveStats
from engine.models import MatchEvent, MatchMeta, Moment, OverlayEvent, TrackingFrame
from engine.scenarios import BY_ID, live_match_id, path_for
from engine.season import CURRENT_MATCHDAY
from engine.sim import MatchSimulator, SimConfig, load_scenario

ROOT = Path(__file__).resolve().parent.parent


def moment_time_of(moment: Moment) -> float:
    return float(moment.state_ref.rsplit("@", 1)[1])

DEMO_SCENARIO = str(ROOT / "data" / "scenarios" / "demo.json")

SPEEDS = (1.0, 2.0, 4.0, 10.0, 30.0)
FRAME_INTERVAL_S = 0.1  # at most 10 frames a second to each viewer
STATS_INTERVAL_S = 0.25
ANALYST_INTERVAL_S = 2.0
HISTORY_EVERY_S = 30.0
QUEUE_MAX = 500
PRIVATE_IDLE_S = 15 * 60
MAX_PRIVATE_ROOMS = 20
CLIP_BEFORE_S = 12.0
CLIP_AFTER_S = 3.0
TRACE_MAX = 400
MCP_URL = os.getenv("ANALYST_MCP_URL", f"http://127.0.0.1:{os.getenv('PORT', '8000')}/mcp")
ASKS_PER_MINUTE = 12  # the app is public and every question costs model calls
SPEECH_PER_MINUTE = 40  # voiced lines per room, to keep the Speech bill small
ASK_FALLBACK = ("I could not check that against the match data just now. "
                "Try a question about the score, a player or a team.")
NARRATE_BACKLOG = 4  # at high speed, older cards keep their template rather than queue for the Narrator
ANIM_MAX = 60  # events held for the next frame message; at high speed older ones are dropped


@dataclass
class _PendingClip:
    event_id: str
    shot_t: float
    frames: list[dict[str, Any]]
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RoomConfig:
    home: str = "KR"
    away: str = "AV"
    seed: int = 7
    scenario: str | None = DEMO_SCENARIO
    speed: float = 1.0
    start_minute: float = 0.0
    half_s: float = 2700.0

    @classmethod
    def for_scenario(cls, path: str, **kw: Any) -> RoomConfig:
        """A library scenario fixes its own fixture and seed."""
        s = load_scenario(path)
        return cls(home=s.home or cls.home, away=s.away or cls.away, seed=cls.seed if s.seed is None else s.seed,
                   scenario=path, **kw)

    @classmethod
    def from_env(cls) -> RoomConfig:
        return cls(
            home=os.getenv("DEMO_HOME", "KR"),
            away=os.getenv("DEMO_AWAY", "AV"),
            seed=int(os.getenv("DEMO_SEED", "7")),
            scenario=os.getenv("DEMO_SCENARIO", DEMO_SCENARIO) or None,
            speed=float(os.getenv("DEMO_SPEED", "1")),
        )


class MatchRoom:
    def __init__(self, room_id: str, league: League, config: RoomConfig, llm: LLM | None = None,
                 speech: Speech | None = None) -> None:
        self.room_id = room_id
        self.llm = llm or LLM()
        self.speech = speech
        self.league = league
        self.config = config
        self.speed = config.speed
        self.paused = False
        self.subscribers: set[asyncio.Queue] = set()
        self.last_seen = time.monotonic()
        self.task: asyncio.Task | None = None
        self._reset()

    def _reset(self) -> None:
        c = self.config
        # The match id (and so its random streams) depends only on the fixture and seed, never on
        # the room, so every replay of the demo is the same match the main room broadcasts.
        meta = MatchMeta(match_id=live_match_id(c.home, c.away, c.seed), home=c.home, away=c.away, seed=c.seed,
                         scenario=c.scenario)
        scenario = load_scenario(c.scenario) if c.scenario else None
        sim = MatchSimulator(meta, self.league, SimConfig(mode="full", half_s=c.half_s), scenario)
        # The room only ever reads the match through the feed: the ingest boundary.
        self.feed: Feed = SimulatorFeed(sim)
        self.live = LiveStats(meta, self.league)
        self.roster = roster(self.feed, self.league)
        self.names = {pid: p["name"] for pid, p in self.roster["players"].items()}
        self.teams = {side: club["name"] for side, club in self.roster["clubs"].items()}
        self.desk = CardDesk(self.llm, self.names, self.teams, meta.match_id)
        self.workflow = card_workflow(self.desk)
        self.trace: deque[dict[str, Any]] = deque(maxlen=TRACE_MAX)
        self._to_narrate: deque[dict[str, Any]] = deque()
        self.event_log: dict[str, dict[str, Any]] = {}
        self.recap: dict[str, Any] | None = None  # the Recap agent's report, when it has written one
        self._asked: deque[float] = deque()
        self._spoken: deque[float] = deque()
        self._commentary: dict[tuple[str, str, str], asyncio.Future] = {}
        self._preview: dict[str, Any] | None = None
        self._postgame: dict[str, Any] | None = None
        self._brief: dict[str, Any] | None = None
        self.deep_cards: list[dict[str, Any]] = []
        self._next_deep = deep.EVERY_MINUTES
        self._last_deep = -99
        self._deep_event = False
        self._story_lock = asyncio.Lock()
        self._recap_lock = asyncio.Lock()
        self.cards: list[dict[str, Any]] = []
        self.history: list[list[float]] = []
        self.last_frame: dict[str, Any] | None = None
        self.status = "live"
        self._next_history_t = 0.0
        # Rolling buffers for shot replays, and the finished clips by shot event id.
        keep = int(CLIP_BEFORE_S / self.feed.dt) + 1
        self._recent_frames: deque[dict[str, Any]] = deque(maxlen=keep)
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=400)
        self._anim: deque[dict[str, Any]] = deque(maxlen=ANIM_MAX)
        self._pending_clips: list[_PendingClip] = []
        self._shots_clipped = 0
        self.clips: dict[str, dict[str, Any]] = {}

    # Snapshots

    def hello(self) -> dict[str, Any]:
        return {
            "type": "hello",
            "room": self.room_id,
            "status": self.status,
            "speed": self.speed,
            "paused": self.paused,
            "half_s": self.config.half_s,
            "roster": self.roster,
            "stats": stats_message(self.live.stats()),
            "frame": self.last_frame,
            "history": self.history,
            "cards": self.cards,
            "deep": self.deep_cards,
            "analyst": analyst_message(self.live),
            "trace": list(self.trace)[-150:],
            "agents": self.agent_info(),
        }

    def agent_info(self) -> dict[str, Any]:
        return {"backend": self.llm.backend.name, "model": self.llm.strong, "live": self.llm.live}

    def cues(self) -> list[dict[str, Any]]:
        """Every cue in every language it exists in, English first."""
        out = [cue for card in self.cards for cue in card["cues"].values()]
        out += [cue for card in self.cards for by_aud in card.get("langs", {}).values() for cue in by_aud.values()]
        return out

    def shot(self, event_id: str) -> dict[str, Any] | None:
        record = next((s for s in self.live.shots if s.event_id == event_id), None)
        if record is None:
            return None
        clip = self.clips.get(event_id)
        if clip is None:  # still recording its last seconds, or the match ended first
            pending = next((p for p in self._pending_clips if p.event_id == event_id), None)
            if pending is not None:
                clip = {"shot_t": pending.shot_t, "dt": self.feed.dt, "frames": list(pending.frames),
                        "events": pending.events}
        return {
            "shot": shot_dict(record),
            "clip": clip,
            "roster": self.roster,
            "match_id": self.feed.meta.match_id,
        }

    def blueprint(self) -> dict[str, Any]:
        """The Match Blueprint page: the whole match story so far."""
        bp = build_blueprint(self.live, self.roster, self.status, self.config.half_s)
        bp["overview"].pop("facts", None)
        bp["overview"]["langs"] = {}
        if self.recap is not None:
            bp["overview"].update({k: self.recap[k] for k in ("headline", "text", "source", "langs", "t")})
        return {**bp, "roster": self.roster}

    # The commentator

    def _card(self, moment_id: str) -> dict[str, Any] | None:
        return next((c for c in self.cards if c["moment"]["moment_id"] == moment_id), None)

    @staticmethod
    def _classic(card: dict[str, Any], lang: str) -> dict[str, Any]:
        """The Narrator's casual line, in the fan's language when the Personalizer has written it."""
        cue = card.get("langs", {}).get(lang, {}).get("casual") or card["cues"]["casual"]
        return {"text": cue["text"], "lang": cue.get("lang", "en"), "style": "classic", "source": "classic"}

    async def commentary(self, moment_id: str, style: str, lang: str = "en") -> dict[str, Any] | None:
        """One moment in the fan's commentator style. Written once per style and language, then shared."""
        card = self._card(moment_id)
        if card is None:
            return None
        if style == "classic" or not self.llm.live:
            return self._classic(card, lang)
        key = (moment_id, style, lang)
        if key not in self._commentary:
            self._commentary[key] = asyncio.ensure_future(self._comment(card, style, lang))
        return await asyncio.shield(self._commentary[key])

    async def _comment(self, card: dict[str, Any], style: str, lang: str) -> dict[str, Any]:
        moment = Moment.model_validate(card["moment"])
        written = await self.desk.write(moment, commentator.audience(style), style)  # type: ignore[arg-type]
        self._log(written.steps)
        if written.source != "narrator":
            return self._classic(card, lang)
        cue = written.cue
        if lang != "en":
            translated = await self.desk.translate(cue, lang, moment_time_of(moment))
            self._log(translated.steps)
            if translated.source != "personalizer":
                return self._classic(card, lang)
            cue = translated.cue
        return {"text": cue.text(), "lang": cue.lang, "style": style, "source": "commentator"}

    async def speak(self, said: dict[str, Any], moment_id: str) -> bytes | None:
        """The line as audio from Azure AI Speech, or None so the browser reads it instead."""
        if self.speech is None:
            return None
        now = time.monotonic()
        while self._spoken and now - self._spoken[0] > 60:
            self._spoken.popleft()
        if len(self._spoken) >= SPEECH_PER_MINUTE:
            return None
        self._spoken.append(now)
        audio, ms, status = await self.speech.speak(said["text"], said["style"], said["lang"])
        if status != "cached":
            card = self._card(moment_id)
            t = moment_time_of(Moment.model_validate(card["moment"])) if card else self.live.t
            self._log([TraceStep(moment_id, "casual", "Voice", f"speak {said['style']} {said['lang']}",
                                 "ok" if audio else "fallback", ms,
                                 "Azure AI Speech" if audio else f"{status}, browser voice instead", t)])
        return audio

    # Before and after the match

    async def _write_story(self, tag: str, agent: str, module: Any, facts: dict[str, str], truths: dict[str, Any],
                           ask: str, names: Any = None) -> tuple[dict[str, Any], str, dict[str, dict[str, Any]]]:
        """An agent writes a story over facts: draft, check, at most one retry, else the template.
        Returns the filled parts, the source and the Personalizer's languages. `names` are the names
        the story may not type; by default this room's players and clubs."""
        names = self.desk.forbidden if names is None else names
        t = self.live.t
        steps: list[TraceStep] = []
        feedback: list[str] = []
        previous: str | None = None
        parts = None
        if self.llm.live:
            for attempt in range(3):  # long stories get two retries
                prompt = ask
                if feedback:
                    # Show the draft being fixed: without it the model starts over and often writes plain prose.
                    prompt += ("\n\nYour last draft:\n" + (previous or "") + "\n\nIt was rejected because: "
                               + "; ".join(feedback) + "\nFix only those problems. Keep every name and number "
                               "as a {slot} from the facts; type none of them.")
                result = await self.llm.complete(agent=agent, instructions=module.INSTRUCTIONS, prompt=prompt,
                                                 model=self.llm.strong)
                if not result.ok:
                    steps.append(TraceStep(tag, "both", agent, f"draft {attempt + 1}", self.desk._status(result.error),
                                           result.ms, result.error or "", t))
                    break
                parsed = module.parse(result.text)
                previous = result.text
                feedback = ["reply was not usable JSON"] if parsed is None else module.check(parsed, facts, names, truths)
                steps.append(TraceStep(tag, "both", agent, f"draft {attempt + 1}", "ok", result.ms,
                                       f"{result.backend} {result.model}", t))
                steps.append(TraceStep(tag, "both", "Verifier", f"check {attempt + 1}", "reject" if feedback else "pass",
                                       0, "; ".join(feedback) or f"{len(facts)} facts, every slot from the engine", t))
                if not feedback:
                    parts = parsed
                    break
        source = "agent"
        if parts is None:
            parts = module.fallback(facts, truths)
            source = "template"
            steps.append(TraceStep(tag, "both", "Fallback", "template", "fallback", 0,
                                   "template story, every value a fact" if self.llm.live else "no model: template story", t))
        fill = lambda tpl: story.fill(tpl, facts)  # noqa: E731
        filled = {k: [fill(x) for x in v] if isinstance(v, list) else fill(v) for k, v in parts.items()}
        langs: dict[str, dict[str, Any]] = {}
        if self.llm.live and source == "agent":
            for lang in LANGS:
                out: dict[str, Any] = {}
                for key, value in parts.items():
                    written = []
                    for template in value if isinstance(value, list) else [value]:
                        res = await self.llm.complete(agent="Personalizer", instructions=personalizer.INSTRUCTIONS,
                                                      prompt=personalizer.prompt(template, lang, "fan"), model=self.llm.fast)
                        tr = personalizer.parse(res.text) if res.ok else None
                        reasons = ([res.error or "no reply"] if not res.ok else ["reply was not usable JSON"] if tr is None
                                   else personalizer.check(template, tr, names))
                        steps.append(TraceStep(tag, "both", "Personalizer", f"write {lang}", "pass" if not reasons else "reject",
                                               res.ms, "; ".join(reasons), t))
                        written.append(None if reasons else fill(tr))
                    out[key] = written if isinstance(value, list) else written[0]
                if all(x is not None for v in out.values() for x in (v if isinstance(v, list) else [v])):
                    langs[lang] = out
        self._log(steps)
        return filled, source, langs

    async def preview(self) -> dict[str, Any]:
        """The Preview agent's story for this fixture, with the table, form, head to head and players to watch."""
        async with self._story_lock:
            if self._preview is None:
                c = self.config
                pack = matchday.preview(self.league, league_season(), c.home, c.away)
                filled, source, langs = await self._write_story(
                    "preview", "Preview", preview, pack["facts"], pack["truths"], preview.prompt(pack["facts"], pack["watch"]))
                self._preview = {**{k: v for k, v in pack.items() if k != "truths"}, **filled,
                                 "source": source, "langs": langs, "home": c.home, "away": c.away}
            return self._preview

    async def postgame(self) -> dict[str, Any]:
        """What decided the match and what each club should watch next time. Rewritten as the match moves on."""
        async with self._story_lock:
            stale = self._postgame is None or self._postgame["status"] != self.status or (
                self.status != "full_time" and self.live.t - self._postgame["t"] > 300)
            if stale:
                pack = matchday.postgame(self, self.league)
                filled, source, langs = await self._write_story(
                    "postgame", "Post-game", postgame, pack["facts"], pack["truths"], postgame.prompt(pack["facts"]))
                self._postgame = {"decided": pack["decided"], "next": pack["next"], **filled, "source": source,
                                  "langs": langs, "status": self.status, "t": self.live.t,
                                  "home": self.config.home, "away": self.config.away}
            return self._postgame

    async def brief(self) -> dict[str, Any]:
        """Catch me up: the Summarizer's three points on the match so far. Rewritten when the match moves on."""
        async with self._story_lock:
            b = self._brief
            if b is None or len(self.cards) != b["cards"] or self.live.t - b["t"] > 120 or b["status"] != self.status:
                derby = matchday.PROFILES[self.config.home].rival == self.config.away
                pack = matchday.match_facts(self.live, self.names, self.teams, self.status == "full_time", derby)
                filled, source, langs = await self._write_story(
                    "brief", "Summarizer", summarizer, pack["facts"], pack["truths"], summarizer.prompt(pack["facts"]))
                self._brief = {**filled, "source": source, "langs": langs, "stats": pack["stats"],
                               "score": pack["truths"]["score"], "minute": int(self.live.t // 60), "status": self.status,
                               "t": self.live.t, "cards": len(self.cards)}
            return self._brief

    async def ask(self, question: str, lang: str = "en", audience: str = "casual") -> dict[str, Any]:
        """Ask the match: the Analyst answers through the MCP tools; code fills every number and name."""
        t = self.live.t
        now = time.monotonic()
        while self._asked and now - self._asked[0] > 60:
            self._asked.popleft()
        out: dict[str, Any] = {"question": question, "answer": ASK_FALLBACK, "source": "fallback", "lang": "en",
                               "evidence": [], "tools_used": [], "limits": ""}
        if len(self._asked) >= ASKS_PER_MINUTE:
            out["answer"] = "Lots of questions right now. Try again in a minute."
            return out
        self._asked.append(now)
        steps: list[TraceStep] = []
        feedback: list[str] = []
        for attempt in range(2):
            prompt = json.dumps({"question": question}, ensure_ascii=False)
            if feedback:
                prompt += "\nYour last answer was rejected because: " + "; ".join(feedback)
            result, called = await self.llm.ask(agent="Analyst", instructions=analyst.instructions(self.room_id, audience),
                                                prompt=prompt, mcp_url=MCP_URL)
            label = f"answer {attempt + 1}"
            if not result.ok:
                steps.append(TraceStep("ask", audience, "Analyst", label, self.desk._status(result.error), result.ms,
                                       result.error or "", t))
                break
            out["tools_used"] = sorted(set(out["tools_used"]) | set(called))
            steps.append(TraceStep("ask", audience, "Analyst", label, "ok", result.ms,
                                   "MCP tools: " + (", ".join(called) or "none"), t))
            parsed = analyst.parse(result.text)
            values: dict[str, str] = {}
            evidence: list[dict[str, Any]] = []
            if parsed is None:
                feedback = ["reply was not usable JSON"]
            else:
                feedback = analyst.check(parsed["answer"], parsed["slots"], self.desk.forbidden, question)
                if not feedback:
                    values, evidence, feedback = analyst.resolve(self, parsed["slots"])
                if not feedback:
                    feedback = analyst.check_filled(parsed["answer"].format(**values), question, self.desk.forbidden)
            steps.append(TraceStep("ask", audience, "Verifier", f"check {attempt + 1}", "reject" if feedback else "pass",
                                   0, "; ".join(feedback) or f"{len(values)} values re-read from the tools", t))
            if feedback or parsed is None:
                continue
            template = parsed["answer"]
            out.update({"answer": template.format(**values), "source": "analyst", "evidence": evidence,
                        "limits": parsed["limits"], "lang": "en",
                        "tools_used": sorted(set(out["tools_used"]) | {e["tool"] for e in evidence})})
            if lang in LANGS:
                res = await self.llm.complete(agent="Personalizer", instructions=personalizer.INSTRUCTIONS,
                                              prompt=personalizer.prompt(template, lang, audience), model=self.llm.fast)
                written = personalizer.parse(res.text) if res.ok else None
                reasons = ([res.error or "no reply"] if not res.ok else ["reply was not usable JSON"] if written is None
                           else personalizer.check(template, written, self.desk.forbidden))
                steps.append(TraceStep("ask", audience, "Personalizer", f"write {lang}", "pass" if not reasons else "reject",
                                       res.ms, "; ".join(reasons), t))
                if not reasons:
                    out.update({"answer": written.format(**values), "lang": lang})
            break
        else:
            steps.append(TraceStep("ask", audience, "Fallback", "answer", "fallback", 0, "the Verifier rejected every answer", t))
        if out["source"] == "fallback" and not any(s.agent == "Fallback" for s in steps):
            steps.append(TraceStep("ask", audience, "Fallback", "answer", "fallback", 0, "no verified answer", t))
        self._log(steps)
        out["steps"] = [s.to_json() for s in steps]
        return out

    async def write_recap(self) -> dict[str, Any] | None:
        """The Recap agent writes the match report over the engine's facts; the Personalizer writes it in
        Spanish and Hindi. Keeps the word-template overview if anything fails."""
        async with self._recap_lock:
            if self.recap is not None and self.live.t - self.recap["t"] < 30:
                return self.recap
            t = self.live.t
            overview = build_blueprint(self.live, self.roster, self.status, self.config.half_s)["overview"]
            facts = overview["facts"]
            feedback: list[str] = []
            steps: list[TraceStep] = []
            draft = None
            for attempt in range(2):
                ask = recap.prompt(facts, overview["text"], self.status == "full_time")
                if feedback:
                    ask += "\nYour last draft was rejected because: " + "; ".join(feedback)
                result = await self.llm.complete(agent="Recap", instructions=recap.INSTRUCTIONS, prompt=ask,
                                                 model=self.llm.strong)
                if not result.ok:
                    steps.append(TraceStep("recap", "both", "Recap", f"draft {attempt + 1}",
                                           self.desk._status(result.error), result.ms, result.error or "", t))
                    break
                parsed = recap.parse(result.text)
                feedback = ["reply was not usable JSON"] if parsed is None else recap.check(*parsed, facts, self.desk.forbidden)
                steps.append(TraceStep("recap", "both", "Recap", f"draft {attempt + 1}", "ok", result.ms,
                                       f"{result.backend} {result.model}", t))
                steps.append(TraceStep("recap", "both", "Verifier", f"check {attempt + 1}",
                                       "reject" if feedback else "pass", 0,
                                       "; ".join(feedback) or f"{len(facts)} facts, every slot from the engine", t))
                if not feedback:
                    draft = parsed
                    break
            if draft is None:
                steps.append(TraceStep("recap", "both", "Fallback", "template", "fallback", 0,
                                       "word-template overview kept", t))
                self._log(steps)
                return None
            head, body = draft
            fill = lambda tpl: tpl.format(**facts).replace("%%", "%")  # noqa: E731
            written: dict[str, Any] = {"headline": fill(head), "text": fill(body),
                                       "source": "recap", "t": t, "langs": {}}
            for lang in LANGS:
                parts = []
                for template in (head, body):
                    res = await self.llm.complete(agent="Personalizer", instructions=personalizer.INSTRUCTIONS,
                                                  prompt=personalizer.prompt(template, lang, "fan"), model=self.llm.fast)
                    out = personalizer.parse(res.text) if res.ok else None
                    reasons = ([res.error or "no reply"] if not res.ok else ["reply was not usable JSON"] if out is None
                               else personalizer.check(template, out, self.desk.forbidden))
                    steps.append(TraceStep("recap", "both", "Personalizer", f"write {lang}",
                                           "pass" if not reasons else "reject", res.ms, "; ".join(reasons), t))
                    parts.append(None if reasons else fill(out))
                if all(parts):
                    written["langs"][lang] = {"headline": parts[0], "text": parts[1]}
            self._log(steps)
            self.recap = written
            self.publish({"type": "recap", **written})
            return written

    def player(self, player_id: str) -> dict[str, Any] | None:
        if player_id not in self.roster["players"]:
            return None
        return {"player": player_id, "summary": player_summary(self.live, player_id), "roster": self.roster}

    # Viewers

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self.subscribers.add(q)
        self.last_seen = time.monotonic()
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)
        self.last_seen = time.monotonic()

    def publish(self, msg: dict[str, Any]) -> None:
        for q in list(self.subscribers):
            if q.full():  # a slow viewer drops its oldest message rather than holding up the match
                q.get_nowait()
            q.put_nowait(msg)

    # Running the match

    def advance(self) -> list[dict[str, Any]]:
        """One simulator tick through the live engine. Returns the cards it produced."""
        produced: list[dict[str, Any]] = []
        frame = None
        for item in self.feed.step():
            for moment in self.live.push(item):
                if moment.kind in ("goal", "low_xg_goal", "red_card"):
                    self._deep_event = True
                card = card_message(moment, self.names, self.teams, self.feed.meta.match_id)
                self.cards.append(card)
                produced.append(card)
                self._record_history()
            if isinstance(item, TrackingFrame):
                frame = item
            elif isinstance(item, MatchEvent):
                self.event_log[item.event_id] = event_record(item)
                if (ev := clip_event(item)) is not None:
                    self._recent_events.append(ev)
                if (anim := anim_event(item)) is not None:
                    self._anim.append(anim)
        if frame is not None:
            self.last_frame = frame_message(frame)
            self._clip(self.last_frame)
        if self.live.t >= self._next_history_t:
            self._record_history()
            self._next_history_t = self.live.t + HISTORY_EVERY_S
        return produced

    def _clip(self, frame: dict[str, Any]) -> None:
        """Keep a replay of every shot: 12 s of tracking before it and 3 s after."""
        compact = {"t": frame["t"], "ball": frame["ball"], "players": frame["players"]}
        while self._shots_clipped < len(self.live.shots):
            shot = self.live.shots[self._shots_clipped]
            self._shots_clipped += 1
            t0 = shot.t - CLIP_BEFORE_S
            self._pending_clips.append(_PendingClip(
                event_id=shot.event_id,
                shot_t=shot.t,
                frames=[f for f in self._recent_frames if f["t"] >= t0],
                events=[e for e in self._recent_events if t0 <= e["t"] <= shot.t],
            ))
        self._recent_frames.append(compact)
        still: list[_PendingClip] = []
        for clip in self._pending_clips:
            clip.frames.append(compact)
            if compact["t"] >= clip.shot_t + CLIP_AFTER_S:
                self.clips[clip.event_id] = {
                    "shot_t": clip.shot_t,
                    "dt": self.feed.dt,
                    "frames": clip.frames,
                    "events": clip.events,
                }
            else:
                still.append(clip)
        self._pending_clips = still

    def _record_history(self) -> None:
        s = self.live.stats()
        self.history.append([round(s.t, 1), *(round(p, 4) for p in s.win_prob)])

    def fast_forward(self, until_t: float) -> None:
        while not self.feed.finished and self.feed.t < until_t:
            self.advance()

    def _log(self, steps: list[TraceStep]) -> None:
        rows = [s.to_json() for s in steps]
        self.trace.extend(rows)
        self.publish({"type": "trace", "steps": rows})

    async def _narrate_worker(self) -> None:
        """Hands each new card to the card desk; swaps in the Narrator's text once it passes the Verifier."""
        while True:
            if not self._to_narrate:
                await asyncio.sleep(0.05)
                continue
            while len(self._to_narrate) > NARRATE_BACKLOG:
                skipped = self._to_narrate.popleft()
                m = skipped["moment"]
                self._log([TraceStep(m["moment_id"], "both", "Desk", "skip", "skipped", 0,
                                     "backlog at high speed, template kept", float(m["state_ref"].rsplit("@", 1)[1]))])
            card = self._to_narrate.popleft()
            moment = Moment.model_validate(card["moment"])
            # The card desk is an Agent Framework workflow: two Narrators in parallel, the Verifier
            # inside each, then the Personalizer. See agents/workflow.py.
            try:
                done = await run_card(self.workflow, moment, self.llm.live)
            except Exception as e:  # the card keeps its verified template; the live match never stops
                self._log([TraceStep(moment.moment_id, "both", "Desk", "workflow", "error", 0,
                                     f"{type(e).__name__}: {e}"[:200], moment_time_of(moment))])
                continue
            written = done.written
            for w in written:
                self._log(w.steps)
            if not any(c is card for c in self.cards):  # the match restarted while the Narrator worked
                continue
            changed = False
            for w in written:
                if w.source == "narrator":
                    card["cues"][w.cue.audience] = {**w.cue.model_dump(mode="json"), "text": w.cue.text()}
                    card["sources"][w.cue.audience] = "narrator"
                    changed = True
            if changed:
                card["source"] = "narrator"
            if done.translated:  # the Personalizer wrote the settled English cues in Spanish and Hindi
                for w in done.translated:
                    self._log(w.steps)
                    if w.source == "personalizer":
                        card["langs"].setdefault(w.cue.lang, {})[w.cue.audience] = {
                            **w.cue.model_dump(mode="json"), "text": w.cue.text()}
                        changed = True
            if changed:
                self.publish({"type": "card_update", "moment_id": moment.moment_id, "cues": card["cues"],
                              "source": card["source"], "sources": card["sources"], "langs": card["langs"]})

    async def run(self) -> None:
        narrating = asyncio.create_task(self._narrate_worker())
        analysing = asyncio.create_task(self._deep_worker())
        try:
            await self._run()
        finally:
            narrating.cancel()
            analysing.cancel()

    async def _deep_worker(self) -> None:
        """The In-depth Analyst: a card every fifteen minutes, and soon after a goal or a red card."""
        while True:
            await asyncio.sleep(0.5)
            minute = int(self.live.t // 60)
            due = minute >= self._next_deep or (self._deep_event and minute - self._last_deep >= deep.AFTER_EVENT_GAP_MINUTES)
            if not due or minute < 10 or self.status != "live":
                continue
            self._deep_event = False
            self._last_deep = minute
            self._next_deep = (minute // deep.EVERY_MINUTES + 1) * deep.EVERY_MINUTES
            await self.write_deep()

    async def write_deep(self) -> dict[str, Any]:
        derby = matchday.PROFILES[self.config.home].rival == self.config.away
        pack = matchday.deep_facts(self.live, self.names, self.teams, derby)
        filled, source, langs = await self._write_story("deep", "Deep Analyst", deep, pack["facts"], pack["truths"],
                                                        deep.prompt(pack["facts"]))
        card = {"type": "deep", "id": f"deep-{pack['minute']}-{len(self.deep_cards)}", "minute": pack["minute"],
                "window": [pack["facts"]["window_start"], pack["facts"]["window_end"]], **filled, "source": source,
                "langs": langs, "chart": pack["chart"]}
        self.deep_cards.append(card)
        self.publish(card)
        return card

    async def _run(self) -> None:
        if self.config.start_minute > 0:
            self.status = "catching_up"
            await asyncio.to_thread(self.fast_forward, self.config.start_minute * 60)
            self._anim.clear()
            self.status = "live"
            self.publish(self.hello())
        dt = self.feed.dt
        last_frame = last_stats = last_analyst = 0.0
        next_tick = time.monotonic()
        while True:
            if self.feed.finished:
                if self.status != "full_time":
                    self.status = "full_time"
                    if self.llm.live:
                        asyncio.create_task(self.write_recap())
                    self.publish(stats_message(self.live.stats()))
                    self.publish(analyst_message(self.live))
                    self.publish(self._control_message())
                await asyncio.sleep(0.5)
                next_tick = time.monotonic()
                continue
            if self.paused:
                await asyncio.sleep(0.1)
                next_tick = time.monotonic()
                continue

            for card in self.advance():
                self.publish(card)
                self._to_narrate.append(card)
            now = time.monotonic()
            if self.last_frame and now - last_frame >= FRAME_INTERVAL_S:
                if self._anim:
                    self.publish({"type": "events", "events": list(self._anim)})
                    self._anim.clear()
                self.publish(self.last_frame)
                last_frame = now
            if now - last_stats >= STATS_INTERVAL_S:
                self.publish(stats_message(self.live.stats()))
                last_stats = now
            if now - last_analyst >= ANALYST_INTERVAL_S:
                self.publish(analyst_message(self.live))
                last_analyst = now

            next_tick += dt / self.speed
            delay = next_tick - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                if delay < -1.0:  # cannot keep up at this speed: stop trying to catch up
                    next_tick = time.monotonic()
                await asyncio.sleep(0)

    # Controls

    def _control_message(self) -> dict[str, Any]:
        return {"type": "control", "status": self.status, "speed": self.speed, "paused": self.paused}

    def control(self, action: str, value: float | None = None) -> dict[str, Any]:
        if action == "speed":
            if value not in SPEEDS:
                raise ValueError(f"speed must be one of {SPEEDS}")
            self.speed = float(value)
        elif action == "pause":
            self.paused = True
        elif action == "resume":
            self.paused = False
        elif action == "restart":
            self._reset()
            self.paused = False
            self.publish(self.hello())
        else:
            raise ValueError(f"unknown action {action}")
        msg = self._control_message()
        self.publish(msg)
        return msg


class Hub:
    def __init__(self, league: League, default: RoomConfig) -> None:
        self.league = league
        self.default = default
        self.rooms: dict[str, MatchRoom] = {}
        self._reaper: asyncio.Task | None = None
        self.llm = LLM.from_env()  # one model client for every room
        self.speech = Speech.from_env()  # one voice for every room
        self._news: dict[str, dict[str, Any]] | None = None
        self._news_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._warming = asyncio.create_task(self.llm.warm())
        self._launch("main", self.default)
        self._reaper = asyncio.create_task(self._reap())

    async def stop(self) -> None:
        tasks = [r.task for r in self.rooms.values() if r.task] + ([self._reaper] if self._reaper else [])
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def newsdesk(self) -> dict[str, Any]:
        """Every matchday report. Templates at once; the Newsdesk agent's versions replace them as they pass."""
        from app import newsdesk as news_data

        if self._news is None:
            self._news = {}
            for m in news_data.matches():
                parts = newsdesk.fallback(m["facts"], m["truths"])
                filled = {k: [x.format(**m["facts"]) for x in v] if isinstance(v, list) else v.format(**m["facts"])
                          for k, v in parts.items()}
                self._news[m["scenario"]] = {**{k: m[k] for k in ("scenario", "title", "home", "away", "forecast",
                                                                  "stats", "goals")},
                                             "score": m["truths"]["score"], "ground": m["facts"]["ground"],
                                             **filled, "source": "template", "langs": {}}
                done = news_data.written().get(m["scenario"])
                if done:  # written ahead of time by the Newsdesk agent and verified (python -m app.newsdesk --write)
                    self._news[m["scenario"]].update({k: done[k] for k in ("headline", "standfirst", "body", "pull", "langs")}
                                                     | {"source": "agent"})
            self._news_task = asyncio.create_task(self._write_news())
        writing = self._news_task is not None and not self._news_task.done()
        return {"matchday": CURRENT_MATCHDAY, "writing": writing, "articles": list(self._news.values())}

    async def _write_news(self) -> None:
        from app import newsdesk as news_data

        room = self.rooms.get("main")
        if room is None or not self.llm.live:
            return
        for m in news_data.matches():
            if self._news is not None and self._news[m["scenario"]]["source"] == "agent":
                continue  # already written and verified
            names = name_list({p.player_id: p.name for c in (m["home"], m["away"]) for p in self.league.squads[c]},
                              {"home": m["facts"]["home"], "away": m["facts"]["away"]})
            try:
                filled, source, langs = await room._write_story(
                    "news", "Newsdesk", newsdesk, m["facts"], m["truths"], newsdesk.prompt(m["facts"], m["hint"]), names)
            except Exception:  # one report failing keeps its template; the rest carry on
                continue
            if source == "agent" and self._news is not None:
                self._news[m["scenario"]].update({**filled, "source": source, "langs": langs})

    def get(self, room_id: str) -> MatchRoom | None:
        return self.rooms.get(room_id)

    def private(self, start_minute: float, speed: float, scenario: str | None = None) -> MatchRoom:
        config = replace(self.default, start_minute=start_minute, speed=speed)
        if scenario:
            if scenario not in BY_ID:
                raise KeyError(scenario)
            config = RoomConfig.for_scenario(str(path_for(scenario)), start_minute=start_minute, speed=speed,
                                             half_s=self.default.half_s)
        if sum(1 for r in self.rooms if r != "main") >= MAX_PRIVATE_ROOMS:
            raise RuntimeError("too many replays running, try again in a few minutes")
        room_id = uuid.uuid4().hex[:8]
        return self._launch(room_id, config)

    def _launch(self, room_id: str, config: RoomConfig) -> MatchRoom:
        room = MatchRoom(room_id, self.league, config, self.llm, self.speech)
        room.task = asyncio.create_task(room.run())
        self.rooms[room_id] = room
        return room

    async def _reap(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()
            for room_id, room in list(self.rooms.items()):
                if room_id != "main" and not room.subscribers and now - room.last_seen > PRIVATE_IDLE_S:
                    if room.task:
                        room.task.cancel()
                    del self.rooms[room_id]
