"""The Highlights reel: which clips it plays, in what order, and the facts the Producer writes over.

Selection is code, never the model: every goal, then the best other big chances by xG plus the size of
the win probability swing riding on them, at most MAX_CLIPS in all, played in match order.
"""

from __future__ import annotations

from typing import Any

from app import matchday
from app.explain import explainable

MAX_CLIPS = 6
OUTCOME_LABEL = {"goal": "Goal", "saved": "Saved", "blocked": "Blocked", "off_target": "Missed"}


def _swing(shot: Any) -> float:
    """How far the shooting team's win probability rested on this shot: scored against not scored."""
    return abs(shot.wp_if_goal - shot.wp_if_miss)


def select(shots: list[Any], recorded: set[str], cap: int = MAX_CLIPS) -> list[Any]:
    """The reel's clips in match order. Every goal is in; big chances fill what is left of the cap."""
    ready = [s for s in shots if s.event_id in recorded and explainable({"outcome": s.outcome, "xg": s.xg})]
    goals = [s for s in ready if s.outcome == "goal"]
    others = sorted((s for s in ready if s.outcome != "goal"), key=lambda s: (-(s.xg + _swing(s)), s.t, s.event_id))
    chosen = goals + others[:max(0, cap - len(goals))]
    return sorted(chosen, key=lambda s: (s.t, s.event_id))


def clip_dict(shot: Any, names: dict[str, str], teams: dict[str, str]) -> dict[str, Any]:
    """What the reel shows between clips: all of it from the shot record, none of it written by a model."""
    return {"event_id": shot.event_id, "minute": shot.minute, "team": shot.team, "player": shot.player_id,
            "player_name": names.get(shot.player_id, shot.player_id), "club": teams[shot.team],
            "outcome": shot.outcome, "label": OUTCOME_LABEL.get(shot.outcome, shot.outcome), "xg": round(shot.xg, 2)}


def pack(live: Any, names: dict[str, str], teams: dict[str, str], finished: bool, derby: bool,
         clips: list[Any]) -> dict[str, Any]:
    """Facts and truths for the intro and outro: the match facts plus the reel's own."""
    base = matchday.match_facts(live, names, teams, finished, derby)
    facts = dict(base["facts"])
    n = len(clips)
    facts["clips"] = f"{n} moment" if n == 1 else f"{n} moments"
    goals = [s for s in live.shots if s.outcome == "goal"]
    if goals:
        top = max(goals, key=lambda s: (_swing(s), -s.t))
        facts |= {"swing": f"{round(_swing(top) * 100)} points", "swing_player": names.get(top.player_id, top.player_id),
                  "swing_minute": f"{top.minute}'", "swing_team": teams[top.team]}
    return {"facts": facts, "truths": base["truths"]}
