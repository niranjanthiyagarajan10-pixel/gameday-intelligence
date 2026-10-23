"""Read-only match tools: what agents (and GitHub Copilot) may know about a live match.

Each tool is a plain function over a match room, so the agents can call it in-process and the MCP
server (`mcp_server/server.py`) can expose the same function over the Model Context Protocol.
Nothing here changes the match.
"""

from __future__ import annotations

from typing import Any

from agents.fallback import slots_for
from agents.verifier import verify
from app.blueprint import MIN_GRAVITY_FRAMES
from app.payloads import player_summary, shot_dict
from engine.gravity import CATEGORIES
from engine.models import Claim, Moment, Side

SIDES: tuple[Side, Side] = ("home", "away")


def _side(room: Any, team: str | None) -> Side | None:
    """'home', 'away', a club name or a club code to a side; None for both teams."""
    if not team:
        return None
    t = team.strip().lower()
    for side in SIDES:
        club = room.roster["clubs"][side]
        if t in (side, club["name"].lower(), club["short"].lower(), club["id"].lower()):
            return side
    raise ValueError(f"unknown team {team!r}; use home, away, a club name or a club code")


def _player(room: Any, player: str) -> str:
    """A player id or a (part of a) name to the player's id."""
    players = room.roster["players"]
    if player in players:
        return player
    p = player.strip().lower()
    hits = [pid for pid, info in players.items() if p and (p == info["name"].lower() or p in info["name"].lower())]
    if len(hits) == 1:
        return hits[0]
    raise ValueError(f"no single player matches {player!r}" + (f"; candidates {hits[:5]}" if hits else ""))


def _name(room: Any, pid: str) -> str:
    return room.roster["players"].get(pid, {}).get("name", pid)


def _moment(room: Any, moment_id: str) -> Moment:
    for card in room.cards:
        if card["moment"]["moment_id"] == moment_id:
            return Moment.model_validate(card["moment"])
    raise ValueError(f"no moment {moment_id!r} in this match yet")


def get_match_state(room: Any) -> dict[str, Any]:
    """Score, minute, xG, possession, win probability, momentum, control and chaos, men on the pitch,
    and the latest key moments."""
    s = room.live.stats()
    clubs = room.roster["clubs"]
    return {
        "status": room.status,
        "minute": int(s.t // 60),
        "home": clubs["home"]["name"],
        "away": clubs["away"]["name"],
        "score": list(s.score),
        "xg": list(s.xg),
        "possession": [round(p, 3) for p in s.possession],
        "win_probability": {"home": round(s.win_prob[0], 3), "draw": round(s.win_prob[1], 3), "away": round(s.win_prob[2], 3)},
        "momentum": s.momentum,
        "control_index": s.control_index,
        "chaos_index": s.chaos_index,
        "men": list(room.live.men),
        "latest_moments": [
            {"moment_id": c["moment"]["moment_id"], "minute": c["moment"]["minute"], "kind": c["moment"]["kind"],
             "text": c["cues"]["casual"]["text"]}
            for c in room.cards[-5:]
        ],
    }


def get_moment_evidence(room: Any, moment_id: str) -> dict[str, Any]:
    """Everything behind one key moment: its evidence numbers, the formatted slot values a card may
    use, and the events it came from."""
    m = _moment(room, moment_id)
    return {
        "moment": m.model_dump(mode="json"),
        "slots": slots_for(m, room.names, room.teams),
        "events": [room.event_log[e] for e in m.event_ids if e in room.event_log],
    }


def get_player_live(room: Any, player: str) -> dict[str, Any]:
    """A player's live numbers: shots, xG and goals above expected, distance, top speed, sprints,
    leverage, press resistance, gravity and the defender who marked them most."""
    pid = _player(room, player)
    summary = player_summary(room.live, pid)
    summary.pop("heatmap", None)
    summary["list"] = summary["list"][-5:]
    row = room.live.gravity.rows.get(pid)
    gravity = None
    if row is not None and row.total_frames >= MIN_GRAVITY_FRAMES:
        gravity = {"overall": round(row.overall or 0.0, 1),
                   **{name: (round(v, 1) if (v := row.mean(i)) is not None else None) for i, name in enumerate(CATEGORIES)}}
    marker = room.live.marking.main_marker(pid)
    return {
        "player": pid,
        "name": _name(room, pid),
        "team": room.roster["players"][pid]["side"],
        **summary,
        "gravity": gravity,
        "marked_most_by": None if marker is None else {
            "defender": _name(room, marker.defender), "seconds": marker.seconds, "share": marker.share},
    }


def compare_windows(room: Any, start_minute: int, end_minute: int, vs_start_minute: int, vs_end_minute: int) -> dict[str, Any]:
    """Compare two stretches of the match: threat (xT), shots, xG, goals and possession per team."""
    live = room.live

    def window(a: int, b: int) -> dict[str, Any]:
        if b <= a:
            raise ValueError("each window must end after it starts")
        buckets = live.by_minute[max(a, 0):b]
        share = live.timeline.share(a * 60.0, min(b * 60.0, live.t)) if live.t > a * 60.0 else (0.5, 0.5)
        out: dict[str, Any] = {"minutes": [a, b]}
        for k, side in enumerate(SIDES):
            out[side] = {
                "xt": round(sum(x.xt[k] for x in buckets), 3),
                "shots": sum(x.shots[k] for x in buckets),
                "xg": round(sum(x.xg[k] for x in buckets), 3),
                "goals": sum(x.goals[k] for x in buckets),
                "possession": round(share[k], 3),
            }
        return out

    return {"window": window(start_minute, end_minute), "versus": window(vs_start_minute, vs_end_minute)}


def list_supporting_events(room: Any, moment_id: str, seconds_before: float = 20.0) -> dict[str, Any]:
    """The events in the build-up to a key moment, oldest first."""
    m = _moment(room, moment_id)
    t = float(m.state_ref.rsplit("@", 1)[1])
    events = [e for e in room.event_log.values() if t - seconds_before <= e["t"] <= t + 1.0]
    return {"moment_id": moment_id, "events": events[-40:]}


def get_shot_map(room: Any, team: str | None = None) -> dict[str, Any]:
    """Every shot so far with xG, outcome, distance, angle, nearest defender and pressure."""
    side = _side(room, team)
    shots = [shot_dict(s) for s in room.live.shots if side is None or s.team == side]
    for s in shots:
        s["player_name"] = _name(room, s["player"])
    return {"shots": shots}


def get_leverage_table(room: Any, team: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Players ranked by leverage (win value added), with shot making, creation, defending and turnovers."""
    side = _side(room, team)
    rows = [r for r in room.live.leverage_table() if side is None or r.team == side][:max(1, min(limit, 30))]
    return {"rows": [
        {"player": r.player_id, "name": _name(room, r.player_id), "team": r.team, "total": round(r.total, 3),
         "shot_making": round(r.shot_making, 3), "creation": round(r.creation, 3),
         "defending": round(r.defending, 3), "turnovers": round(r.turnovers, 3)}
        for r in rows
    ], "scale": "1.0 leverage is 10 points of win value"}


def get_team_shape(room: Any, team: str) -> dict[str, Any]:
    """A team's defensive block now (low block, mid block or high press), its line height,
    compactness and pressers, and when it changed."""
    side = _side(room, team)
    if side is None:
        raise ValueError("name one team")
    tracker = room.live.shape.teams[side]
    return {"team": side, "state": tracker.state, "window": room.live.shape.window(side),
            "timeline": [[round(t), s] for t, s in tracker.timeline]}


def get_press_resistance(room: Any, team: str | None = None) -> dict[str, Any]:
    """How often players kept the ball when pressed, with attempts so small samples are obvious."""
    side = _side(room, team)
    return {"rows": [
        {"player": r.player_id, "name": _name(room, r.player_id), "team": r.team, "attempts": r.attempts,
         "retained": r.retained, "rate": r.rate}
        for r in room.live.press_table() if side is None or r.team == side
    ]}


def get_gravity(room: Any, team: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Gravity: defenders a player pulls close beyond the league average for the same spot and role
    (+100 is one extra defender), for players measured at least five minutes with the ball."""
    side = _side(room, team)
    rows = []
    for pid, row in room.live.gravity.rows.items():
        if row.total_frames < MIN_GRAVITY_FRAMES or row.overall is None:
            continue
        if side is not None and room.live.gravity.teams.get(pid) != side:
            continue
        rows.append({"player": pid, "name": _name(room, pid), "team": room.live.gravity.teams.get(pid),
                     "overall": round(row.overall, 1)})
    rows.sort(key=lambda r: -r["overall"])
    return {"rows": rows[:max(1, min(limit, 30))]}


def verify_claims(room: Any, moment_id: str, template: str, claims: list[dict[str, Any]] | None = None,
                  audience: str = "casual") -> dict[str, Any]:
    """Check a draft card template and its claims against a moment's evidence. Returns pass or the
    reasons it fails. Deterministic: the same draft always gets the same verdict."""
    m = _moment(room, moment_id)
    parsed = [Claim(claim_id=f"c{i + 1}", metric=str(c.get("metric", "")), subject=str(c.get("subject", "")),
                    slot=c.get("slot"), direction=c.get("direction") if c.get("direction") in ("up", "down", "level") else None)
              for i, c in enumerate(claims or [])]
    allowed = slots_for(m, room.names, room.teams)
    verdict = verify(template, parsed, m, allowed, room.desk.forbidden, audience if audience in ("casual", "analyst") else "casual")
    return {"pass": verdict.ok, "reasons": verdict.reasons}


TOOLS = [get_match_state, get_moment_evidence, get_player_live, compare_windows, list_supporting_events,
         get_shot_map, get_leverage_table, get_team_shape, get_press_resistance, get_gravity, verify_claims]
