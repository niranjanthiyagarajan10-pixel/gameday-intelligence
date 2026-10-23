"""JSON messages sent to the dashboard. Frames are compact because they go out several times a second."""

from __future__ import annotations

from typing import Any

from statistics import mean

from agents.fallback import fallback_cue, hero_for
from engine.feed import Feed
from engine.league import League
from engine.live import LiveStats, ShotRecord
from engine.models import MatchEvent, Moment, Side, StatsUpdate, TrackingFrame

SIDES: tuple[Side, Side] = ("home", "away")


def roster(feed: Feed, league: League) -> dict[str, Any]:
    club_ids = {"home": feed.meta.home, "away": feed.meta.away}
    clubs = {}
    for side in SIDES:
        club = league.clubs[club_ids[side]]
        clubs[side] = {
            "id": club.club_id,
            "name": club.name,
            "short": club.short,
            "primary": club.primary,
            "secondary": club.secondary,
            "formation": club.formation,
            "lineup": feed.lineups[side],
        }
    players = {}
    for side in SIDES:
        for p in league.squads[club_ids[side]]:
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


CLIP_EVENT_TYPES = {"pass", "carry", "shot", "tackle", "interception", "goal"}


def _event_dict(e: MatchEvent) -> dict[str, Any]:
    return {
        "t": e.t, "type": e.type.value, "team": e.team, "player": e.player_id,
        "x": e.x, "y": e.y, "end_x": e.end_x, "end_y": e.end_y, "outcome": e.outcome,
    }


def event_record(e: MatchEvent) -> dict[str, Any]:
    """Any event, compactly, for the event log the agents' tools read."""
    return {"id": e.event_id, "minute": e.minute, **_event_dict(e)}


def clip_event(e: MatchEvent) -> dict[str, Any] | None:
    if e.type.value not in CLIP_EVENT_TYPES:
        return None
    return _event_dict(e)


# What the live pitch draws: pass and shot lines, won tackles, interceptions, cards, goals.
ANIM_EVENT_TYPES = {"pass", "shot", "tackle", "interception", "card", "goal"}


def anim_event(e: MatchEvent) -> dict[str, Any] | None:
    if e.type.value not in ANIM_EVENT_TYPES or (e.type.value == "tackle" and e.outcome != "won"):
        return None
    return {"id": e.event_id, **_event_dict(e)}


def shot_dict(s: ShotRecord) -> dict[str, Any]:
    return {
        "event_id": s.event_id, "team": s.team, "player": s.player_id, "minute": s.minute, "t": s.t,
        "x": s.x, "y": s.y, "xg": s.xg, "outcome": s.outcome, "body_part": s.body_part,
        "speed_kmh": round(s.speed_ms * 3.6, 1) if s.speed_ms else None, "leverage": s.leverage,
        "shot_type": s.shot_type, "distance_m": s.distance_m, "angle_deg": s.angle_deg,
        "pressure": round(s.pressure, 2), "defender_m": s.defender_m, "defender": s.defender_id, "creator": s.creator,
        "score_before": s.score_before, "wp_if_goal": s.wp_if_goal, "wp_if_miss": s.wp_if_miss,
    }


MIN_NETWORK_PASSES = 2
MIN_NETWORK_FRAMES = 25  # 5 seconds in possession before a player gets a node


def pass_network(live: LiveStats) -> dict[str, Any]:
    """Per team: average positions in possession (from tracking) and completed passes between pairs."""
    side_of = {pid: ("home" if pid.startswith(live.meta.home) else "away") for pid in live.in_possession_pos}
    out: dict[str, Any] = {}
    for side in SIDES:
        nodes = []
        involvement: dict[str, int] = {}
        for (a, b), n in live.pass_pairs.items():
            if side_of.get(a, "home" if a.startswith(live.meta.home) else "away") == side:
                involvement[a] = involvement.get(a, 0) + n
                involvement[b] = involvement.get(b, 0) + n
        for pid, (sx, sy, frames) in live.in_possession_pos.items():
            if side_of[pid] == side and frames >= MIN_NETWORK_FRAMES:
                nodes.append({"player": pid, "x": round(sx / frames, 1), "y": round(sy / frames, 1),
                              "passes": involvement.get(pid, 0)})
        placed = {n["player"] for n in nodes}
        combined: dict[tuple[str, str], int] = {}
        for (a, b), n in live.pass_pairs.items():
            if a in placed and b in placed and side_of[a] == side:
                key = (a, b) if a < b else (b, a)
                combined[key] = combined.get(key, 0) + n
        edges = sorted(
            ({"a": a, "b": b, "n": n} for (a, b), n in combined.items() if n >= MIN_NETWORK_PASSES),
            key=lambda e: -e["n"],
        )[:40]
        out[side] = {"nodes": nodes, "edges": edges}
    return out


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 3) if values else None


def player_summary(live: LiveStats, player_id: str) -> dict[str, Any]:
    """Per-player game averages, in the spirit of the NBA player shot page."""
    shots = [s for s in live.shots if s.player_id == player_id]
    goals = [s for s in shots if s.outcome == "goal"]
    misses = [s for s in shots if s.outcome != "goal"]
    xg_total = sum(s.xg for s in shots)
    run = live.kinematics.runs.get(player_id)
    lev = live.leverage_rows.get(player_id)
    press = live.press.rows.get(player_id)
    return {
        "shots": len(shots),
        "goals": len(goals),
        "on_target": sum(1 for s in shots if s.outcome in ("goal", "saved")),
        "xg": round(xg_total, 3),
        "goals_minus_xg": round(len(goals) - xg_total, 3),
        "made_xg": _avg([s.xg for s in goals]),
        "missed_xg": _avg([s.xg for s in misses]),
        "avg_defender_m": _avg([s.defender_m for s in shots if s.defender_m is not None]),
        "distance_km": round(run.distance_m / 1000, 2) if run else 0.0,
        "top_speed_kmh": round(run.top_speed_ms * 3.6, 1) if run else 0.0,
        "sprints": run.sprints if run else 0,
        "leverage": round(lev.total, 3) if lev else 0.0,
        "press_rate": press.rate if press else None,
        "press_attempts": press.attempts if press else 0,
        "heatmap": run.heat.tolist() if run else [],
        "list": [shot_dict(s) for s in shots],
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
        "source": "template",  # until the Narrator's verified draft replaces it
        "sources": {"casual": "template", "analyst": "template"},
    }


def analyst_message(live: LiveStats) -> dict[str, Any]:
    shots = [shot_dict(s) for s in live.shots]
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
        "network": pass_network(live),
        "shots": shots,
        "leverage": leverage,
        "press": press,
        "runs": runs,
        "shape": shape,
        "passes": live.passes,
        "completed": live.completed,
        "men": live.men,
    }
