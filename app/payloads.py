"""JSON messages sent to the dashboard. Frames are compact because they go out several times a second."""

from __future__ import annotations

from typing import Any

from agents.fallback import fallback_cue, hero_for
from engine.league import League
from engine.live import LiveStats
from engine.models import Moment, Side, StatsUpdate, TrackingFrame
from engine.sim import MatchSimulator

SIDES: tuple[Side, Side] = ("home", "away")


def roster(sim: MatchSimulator, league: League) -> dict[str, Any]:
    clubs = {}
    for side, club in zip(SIDES, sim.clubs):
        clubs[side] = {
            "id": club.club_id,
            "name": club.name,
            "short": club.short,
            "primary": club.primary,
            "secondary": club.secondary,
            "formation": club.formation,
            "lineup": [p.player_id for p in sim.lineups[side]],
        }
    players = {}
    for side, club in zip(SIDES, sim.clubs):
        for p in league.squads[club.club_id]:
            players[p.player_id] = {
                "name": p.name,
                "short": p.name.split(" ", 1)[-1],
                "number": p.number,
                "position": p.position,
                "side": side,
            }
    return {"clubs": clubs, "players": players}


def frame_message(frame: TrackingFrame) -> dict[str, Any]:
    return {
        "type": "frame",
        "t": frame.t,
        "ball": [frame.ball.x, frame.ball.y, frame.ball.z],
        "players": [[p.id, p.x, p.y, p.speed_ms] for p in frame.players],
    }


def stats_message(stats: StatsUpdate) -> dict[str, Any]:
    return {"type": "stats", **stats.model_dump(mode="json")}


def card_message(m: Moment, names: dict[str, str], teams: dict[Side, str], match_id: str) -> dict[str, Any]:
    cues = {aud: fallback_cue(m, aud, names, teams, match_id) for aud in ("casual", "analyst")}
    hero = hero_for(m)
    return {
        "type": "card",
        "moment": m.model_dump(mode="json"),
        "cues": {aud: {**cue.model_dump(mode="json"), "text": cue.text()} for aud, cue in cues.items()},
        "hero": {"value": hero.value, "label": hero.label},
        "source": "fallback",
    }


def analyst_message(live: LiveStats) -> dict[str, Any]:
    shots = [
        {
            "event_id": s.event_id, "team": s.team, "player": s.player_id, "minute": s.minute,
            "x": s.x, "y": s.y, "xg": s.xg, "outcome": s.outcome, "body_part": s.body_part,
            "speed_kmh": round(s.speed_ms * 3.6, 1) if s.speed_ms else None, "leverage": s.leverage,
        }
        for s in live.shots
    ]
    leverage = [
        {
            "player": r.player_id, "team": r.team, "total": round(r.total, 3),
            "shot_making": round(r.shot_making, 3), "creation": round(r.creation, 3),
            "defending": round(r.defending, 3), "turnovers": round(r.turnovers, 3),
        }
        for r in live.leverage_table()
    ]
    press = [
        {"player": r.player_id, "team": r.team, "attempts": r.attempts, "retained": r.retained, "rate": r.rate}
        for r in live.press_table()
    ]
    runs = {
        pid: {
            "distance_m": round(run.distance_m), "hsr_m": round(run.hsr_m), "sprints": run.sprints,
            "top_speed_kmh": round(run.top_speed_ms * 3.6, 1), "speed_kmh": round(run.speed_ms * 3.6, 1),
        }
        for pid, run in live.kinematics.runs.items()
    }
    shape = {
        side: {
            "timeline": [[t, state] for t, state in team.timeline],
            "state": team.state,
            "window": live.shape.window(side),
        }
        for side, team in live.shape.teams.items()
    }
    return {
        "type": "analyst",
        "t": live.t,
        "shots": shots,
        "leverage": leverage,
        "press": press,
        "runs": runs,
        "shape": shape,
        "passes": live.passes,
        "completed": live.completed,
        "men": live.men,
    }
