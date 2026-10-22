"""Data contracts shared by the engine, agents, API and web app. See docs/SPEC.md section 6.

Units: meters on a 105 x 68 pitch, seconds from kickoff. All models are frozen and
reject unknown fields, so a typo in an agent or a test fails loudly.
"""

from __future__ import annotations

from enum import StrEnum
from string import Formatter
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.pitch import BALL_MARGIN, PITCH_LENGTH, PITCH_WIDTH

Side = Literal["home", "away"]
Audience = Literal["casual", "analyst"]
Lang = Literal["en", "es", "hi"]
Position = Literal["GK", "DF", "MF", "FW"]

Unit = Annotated[float, Field(ge=0.0, le=1.0)]
Seconds = Annotated[float, Field(ge=0.0)]
Minute = Annotated[int, Field(ge=0, le=130)]
PitchX = Annotated[float, Field(ge=0.0, le=PITCH_LENGTH)]
PitchY = Annotated[float, Field(ge=0.0, le=PITCH_WIDTH)]
BallX = Annotated[float, Field(ge=-BALL_MARGIN, le=PITCH_LENGTH + BALL_MARGIN)]
BallY = Annotated[float, Field(ge=-BALL_MARGIN, le=PITCH_WIDTH + BALL_MARGIN)]
NonNegPair = tuple[Annotated[float, Field(ge=0.0)], Annotated[float, Field(ge=0.0)]]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]

# Fastest recorded sprinters top out near 12.4 m/s. Anything above this is a simulator bug.
MAX_PLAYER_SPEED_MS = 12.5

SUM_TOLERANCE = 1e-6


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# League and hidden truth


class TeamTruth(Contract):
    """Hidden team strengths. The simulator samples from them; the metrics try to recover them."""

    attack: Unit
    defence: Unit
    press: Unit
    tempo: Unit


class PlayerTraits(Contract):
    pace: Unit
    passing: Unit
    finishing: Unit
    stamina: Unit


class Player(Contract):
    player_id: str = Field(pattern=r"^[A-Z0-9]{2,8}$")
    club_id: str
    name: str = Field(min_length=1)
    number: int = Field(ge=1, le=99)
    position: Position
    traits: PlayerTraits


class Club(Contract):
    club_id: str
    name: str = Field(min_length=1)
    short: str = Field(pattern=r"^[A-Z]{2,3}$")
    primary: HexColor
    secondary: HexColor
    formation: str = Field(pattern=r"^\d(-\d){2,3}$")
    truth: TeamTruth


class MatchMeta(Contract):
    match_id: str
    home: str
    away: str
    seed: int = Field(ge=0)
    scenario: str | None = None

    @model_validator(mode="after")
    def _different_clubs(self) -> MatchMeta:
        if self.home == self.away:
            raise ValueError("a club cannot play itself")
        return self


# Events and tracking


class EventType(StrEnum):
    PASS = "pass"
    CARRY = "carry"
    SHOT = "shot"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    FOUL = "foul"
    CARD = "card"
    GOAL = "goal"
    SUBSTITUTION = "substitution"
    POSSESSION_CHANGE = "possession_change"
    PRESSURE = "pressure"


Outcome = Literal[
    "complete", "incomplete", "won", "lost", "goal", "saved", "off_target", "blocked", "yellow", "red"
]
BodyPart = Literal["foot", "head", "other"]


class MatchEvent(Contract):
    event_id: str
    match_id: str
    t: Seconds
    minute: Minute
    period: Literal[1, 2]
    type: EventType
    team: Side
    player_id: str | None = None
    x: PitchX
    y: PitchY
    end_x: BallX | None = None
    end_y: BallY | None = None
    outcome: Outcome | None = None
    pressure: Unit = 0.0
    ball_speed_ms: float | None = Field(default=None, ge=0.0)
    body_part: BodyPart | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _end_point_complete(self) -> MatchEvent:
        if (self.end_x is None) != (self.end_y is None):
            raise ValueError("end_x and end_y must be set together")
        return self


class BallPos(Contract):
    x: BallX
    y: BallY
    z: float = Field(default=0.0, ge=0.0)


class PlayerPos(Contract):
    id: str
    team: Side
    x: PitchX
    y: PitchY
    speed_ms: float = Field(ge=0.0, le=MAX_PLAYER_SPEED_MS)


class TrackingFrame(Contract):
    t: Seconds
    ball: BallPos
    players: list[PlayerPos]

    @model_validator(mode="after")
    def _valid_players(self) -> TrackingFrame:
        ids = [p.id for p in self.players]
        if len(ids) != len(set(ids)):
            raise ValueError("a player appears twice in one frame")
        if len(ids) > 22:
            raise ValueError("more than 22 players on the pitch")
        return self


# Live state


class StatsUpdate(Contract):
    t: Seconds
    score: tuple[Annotated[int, Field(ge=0)], Annotated[int, Field(ge=0)]]
    xg: NonNegPair
    xt: tuple[float, float]
    possession: NonNegPair
    win_prob: tuple[Unit, Unit, Unit]
    momentum: float = Field(ge=-1.0, le=1.0)
    control_index: float = Field(ge=0.0)
    chaos_index: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _shares_sum_to_one(self) -> StatsUpdate:
        if abs(sum(self.win_prob) - 1.0) > SUM_TOLERANCE:
            raise ValueError("win_prob must sum to 1 (home, draw, away)")
        if abs(sum(self.possession) - 1.0) > SUM_TOLERANCE:
            raise ValueError("possession shares must sum to 1")
        return self


MomentKind = Literal[
    "goal",
    "red_card",
    "big_chance",
    "low_xg_goal",
    "leverage_swing",
    "top_speed",
    "control_flip",
    "shape_change",
]


class Moment(Contract):
    moment_id: str
    minute: Minute
    kind: MomentKind
    leverage: float
    team: Side | None = None
    players: list[str] = Field(default_factory=list)
    evidence: dict[str, float | int | str] = Field(default_factory=dict)
    event_ids: list[str] = Field(default_factory=list)
    state_ref: str


# Agent output. Agents write templates with slots; code fills the slots.


class Claim(Contract):
    claim_id: str
    metric: str
    subject: str
    slot: str | None = None
    direction: Literal["up", "down", "level"] | None = None
    minute: Minute | None = None


_FORMATTER = Formatter()


def template_slots(template: str) -> list[str]:
    """Slot names in a template, in order of appearance. Raises if a slot is malformed.

    Slots are plain names like {xg}. Format specs such as {xg:.2f} are not allowed,
    because formatting numbers is the code's job, not the agent's.
    """
    names: list[str] = []
    for _, field, spec, conversion in _FORMATTER.parse(template):
        if field is None:
            continue
        if not field.isidentifier():
            raise ValueError(f"slot {{{field}}} must be a plain name")
        if spec or conversion:
            raise ValueError(f"slot {{{field}}} must not carry a format spec or conversion")
        names.append(field)
    return names


def check_slots(template: str, slots: dict[str, str]) -> None:
    """Every slot in the template has a value, and every value is used."""
    used = set(template_slots(template))
    missing = used - slots.keys()
    unused = slots.keys() - used
    if missing:
        raise ValueError(f"template uses slots with no value: {sorted(missing)}")
    if unused:
        raise ValueError(f"slot values never used in the template: {sorted(unused)}")


def fill_template(template: str, slots: dict[str, str]) -> str:
    check_slots(template, slots)
    return template.format_map(slots)


CueKind = Literal[
    "key_moment",
    "goal",
    "red_card",
    "shape_change",
    "player_milestone",
    "pass_quality",
    "shot_quality",
    "control_chaos",
    "recap",
]


class OverlayEvent(Contract):
    """A timed, machine-readable cue that a broadcast renderer or the web app can draw."""

    cue_id: str
    match_id: str
    t_start: Seconds
    duration_s: float = Field(gt=0.0, le=60.0)
    kind: CueKind
    audience: Audience
    club: Side | None = None
    lang: Lang
    template: str = Field(min_length=1)
    slots: dict[str, str]
    verified: bool
    source_claims: list[str] = Field(default_factory=list)
    evidence_ref: str | None = None

    @model_validator(mode="after")
    def _slots_match_template(self) -> OverlayEvent:
        check_slots(self.template, self.slots)
        return self

    def text(self) -> str:
        return fill_template(self.template, self.slots)


class Answer(Contract):
    """A reply to an Ask the match question."""

    question: str = Field(min_length=1, max_length=500)
    template: str = Field(min_length=1)
    slots: dict[str, str]
    tools_used: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    verified: bool
    limits: str | None = None

    @model_validator(mode="after")
    def _slots_match_template(self) -> Answer:
        check_slots(self.template, self.slots)
        return self

    def text(self) -> str:
        return fill_template(self.template, self.slots)
