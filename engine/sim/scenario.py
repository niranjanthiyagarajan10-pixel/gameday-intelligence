"""Scenario scripts: incidents injected at set minutes, so a demo match has a guaranteed story arc."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from engine.models import Contract, Minute, Side, Unit


class Incident(Contract):
    minute: Minute
    kind: Literal["red_card", "injury", "tactic"]
    team: Side
    player_number: int | None = Field(default=None, ge=1, le=99)
    press: Unit | None = None

    @model_validator(mode="after")
    def _fields_for_kind(self) -> Incident:
        if self.kind in ("red_card", "injury") and self.player_number is None:
            raise ValueError(f"{self.kind} needs player_number")
        if self.kind == "tactic" and self.press is None:
            raise ValueError("tactic needs press")
        return self


class Scenario(Contract):
    name: str
    incidents: list[Incident] = Field(default_factory=list)


def load_scenario(path: str | Path) -> Scenario:
    return Scenario.model_validate_json(Path(path).read_text(encoding="utf-8"))
