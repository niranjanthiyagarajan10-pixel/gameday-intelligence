"""Explain this moment: the beats of the move that led to a shot, found in code from tracking and events.

A beat is one step a fan can see: where the ball was won, a pass that took defenders out of the game,
a carry, a tackle beaten, and the shot itself. Each beat carries its time, the players in it, what to
draw on the pitch and the facts an agent may use to explain it. Nothing here is written by a model.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from typing import Any

from engine.pitch import PITCH_LENGTH, PITCH_WIDTH, to_attacking

WINDOW_S = 30.0  # how far back the move may start (a free kick takes time to set up)
MIN_CARRY_M = 5.0  # a run with the ball is a beat when it moves the ball at least this far toward goal
KEY_PASS_MIN = 2  # a pass is the key pass when it takes at least this many defenders out of the game
MAX_MIDDLE = 3  # beats between the start of the move and the shot
RESTARTS = {"corner": "corner", "free_kick": "free kick", "throw_in": "throw-in", "goal_kick": "goal kick",
            "kickoff": "kick-off", "keeper": "keeper's ball"}


def _frame_at(frames: list[dict[str, Any]], t: float) -> dict[str, Any] | None:
    if not frames:
        return None
    times = [f["t"] for f in frames]
    i = bisect_left(times, t)
    if i == 0:
        return frames[0]
    if i == len(frames):
        return frames[-1]
    return frames[i] if times[i] - t < t - times[i - 1] else frames[i - 1]


def goal_side(frame: dict[str, Any] | None, bx: float, by: float, team: str, side_of: dict[str, str],
              keepers: set[str]) -> list[str]:
    """Opposition outfield players between the ball and the goal being attacked."""
    if frame is None:
        return []
    ball_x, _ = to_attacking(bx, by, team)
    out = []
    for pid, x, y, *_ in frame["players"]:
        if side_of.get(pid) in (None, team) or pid in keepers:
            continue
        if to_attacking(x, y, team)[0] > ball_x:
            out.append(pid)
    return out


def _nearest(frame: dict[str, Any] | None, x: float, y: float, ids: set[str]) -> tuple[str | None, float | None]:
    if frame is None:
        return None, None
    best = min(((math.hypot(px - x, py - y), pid) for pid, px, py, *_ in frame["players"] if pid in ids), default=None)
    return (best[1], round(best[0], 1)) if best else (None, None)


def _chain(shot: dict[str, Any], events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """The attacking team's events in the move, oldest first, and the event that started it (if seen)."""
    team, t0 = shot["team"], shot["t"] - WINDOW_S
    before = [e for e in events if t0 <= e["t"] <= shot["t"] and e.get("id") != shot["event_id"]
              and not (e["type"] in ("shot", "goal") and e["t"] >= shot["t"])]
    chain: list[dict[str, Any]] = []
    for e in reversed(before):
        mine = e["team"] == team
        if e["type"] == "possession_change":
            if not mine:
                break
            if e.get("meta", {}).get("reason") in ("tackle", "interception"):
                continue  # the tackle or interception itself comes next
            return list(reversed(chain)), e
        if e["type"] in ("tackle", "interception") and mine and e.get("outcome") == "won":
            return list(reversed(chain)), e
        if e["type"] == "foul" and not mine:
            return list(reversed(chain)), e
        if not mine:
            if e["type"] in ("pass", "carry", "shot"):
                break
            continue  # a missed tackle or a press: the move goes on
        chain.append(e)
    return list(reversed(chain)), None


def _merge_carries(chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One player's back-to-back carries are one run with the ball."""
    out: list[dict[str, Any]] = []
    for e in chain:
        prev = out[-1] if out else None
        if (prev is not None and e["type"] == "carry" and prev["type"] == "carry" and prev.get("player") == e.get("player")
                and e.get("end_x") is not None):
            out[-1] = {**prev, "end_x": e["end_x"], "end_y": e["end_y"]}
        else:
            out.append(e)
    return out


def find_beats(shot: dict[str, Any], events: list[dict[str, Any]], frames: list[dict[str, Any]],
               side_of: dict[str, str], keepers: set[str]) -> list[dict[str, Any]]:
    """The beats of the move behind a shot, in time order, the shot last.

    `shot` is the shot as the app serves it, `events` the event log (any order), `frames` the clip's
    tracking frames: {"t", "ball": [x, y, z], "players": [[id, x, y, speed], ...]}.
    """
    team = shot["team"]
    events = sorted(events, key=lambda e: e["t"])
    chain, start = _chain(shot, events)
    chain = _merge_carries(chain)
    opponents = {p for p, s in side_of.items() if s != team}
    beats: list[dict[str, Any]] = []

    if start is not None:
        if start["type"] in ("tackle", "interception"):
            gx, _ = to_attacking(start["x"], start["y"], team)
            beats.append({"kind": "won", "t": start["t"], "player": start.get("player"), "x": start["x"], "y": start["y"],
                          "facts": {"how": "tackle" if start["type"] == "tackle" else "interception",
                                    "to_goal_m": round(PITCH_LENGTH - gx)},
                          "draw": [{"ring": start.get("player")}, {"spot": [start["x"], start["y"]]}]})
        elif start["type"] == "foul":
            beats.append({"kind": "foul_won", "t": start["t"], "player": start.get("meta", {}).get("fouled") or shot["player"],
                          "x": start["x"], "y": start["y"], "facts": {"fouler": start.get("player")},
                          "draw": [{"spot": [start["x"], start["y"]]}]})
        elif start["type"] == "possession_change" and start.get("meta", {}).get("reason") == "loose_ball":
            gx, _ = to_attacking(start["x"], start["y"], team)
            beats.append({"kind": "won", "t": start["t"], "player": start.get("player"), "x": start["x"], "y": start["y"],
                          "facts": {"how": "loose ball", "to_goal_m": round(PITCH_LENGTH - gx)},
                          "draw": [{"ring": start.get("player")}, {"spot": [start["x"], start["y"]]}]})
        elif start["type"] == "possession_change" and start.get("meta", {}).get("reason") in RESTARTS:
            beats.append({"kind": "restart", "t": start["t"], "player": start.get("player"), "x": start["x"], "y": start["y"],
                          "facts": {"restart": RESTARTS[start["meta"]["reason"]]},
                          "draw": [{"spot": [start["x"], start["y"]]}]})

    # Every completed pass and long carry in the move, with the defenders it took out of the game.
    middle: list[dict[str, Any]] = []
    for i, e in enumerate(chain):
        nxt = chain[i + 1] if i + 1 < len(chain) else None
        arrive_t = nxt["t"] if nxt else shot["t"]
        if e["type"] == "pass" and e.get("outcome") == "complete" and e.get("end_x") is not None:
            ahead_before = goal_side(_frame_at(frames, e["t"]), e["x"], e["y"], team, side_of, keepers)
            ahead_after = goal_side(_frame_at(frames, arrive_t), e["end_x"], e["end_y"], team, side_of, keepers)
            passed = [p for p in ahead_before if p not in ahead_after]
            receiver = e.get("meta", {}).get("receiver") or (nxt["player"] if nxt else shot["player"])
            middle.append({"kind": "pass", "t": e["t"], "player": e.get("player"), "to": receiver,
                           "x": e["x"], "y": e["y"], "end_x": e["end_x"], "end_y": e["end_y"],
                           "facts": {"distance_m": round(math.hypot(e["end_x"] - e["x"], e["end_y"] - e["y"])),
                                     "bypassed": len(passed)},
                           "draw": [{"arrow": [e["x"], e["y"], e["end_x"], e["end_y"]]}]
                           + [{"ring": p, "tone": "beaten"} for p in passed]})
        elif e["type"] == "carry" and e.get("end_x") is not None:
            sx, _ = to_attacking(e["x"], e["y"], team)
            ex, _ = to_attacking(e["end_x"], e["end_y"], team)
            if ex - sx >= MIN_CARRY_M:
                middle.append({"kind": "carry", "t": e["t"], "player": e.get("player"),
                               "x": e["x"], "y": e["y"], "end_x": e["end_x"], "end_y": e["end_y"],
                               "facts": {"gain_m": round(ex - sx)},
                               "draw": [{"run": [e["x"], e["y"], e["end_x"], e["end_y"]]}]})
    for e in events:
        if (e["type"] == "tackle" and e["team"] != team and e.get("outcome") == "lost"
                and chain and chain[0]["t"] <= e["t"] <= shot["t"]):
            middle.append({"kind": "tackle_beaten", "t": e["t"], "player": next(
                (c["player"] for c in reversed(chain) if c["t"] <= e["t"]), shot["player"]),
                "x": e["x"], "y": e["y"], "facts": {"tackler": e.get("player")},
                "draw": [{"ring": e.get("player"), "tone": "beaten"}]})

    passes = [b for b in middle if b["kind"] == "pass"]
    key = max(passes, key=lambda b: (b["facts"]["bypassed"], b["t"]), default=None)
    if key is not None and key["facts"]["bypassed"] >= KEY_PASS_MIN:
        key["key"] = True
    last = passes[-1] if passes and passes[-1]["to"] == shot["player"] else None
    if last is not None:
        last["final"] = True
    # Keep what tells the story: the key pass, the final pass, a beaten tackle, the longest carry.
    ranked = sorted(middle, key=lambda b: (not b.get("key"), not b.get("final"), b["kind"] != "tackle_beaten",
                                           -b["facts"].get("gain_m", 0), -b["facts"].get("bypassed", 0)))
    beats += sorted(ranked[:MAX_MIDDLE], key=lambda b: b["t"])

    frame = _frame_at(frames, shot["t"])
    keeper, keeper_m = _nearest(frame, shot["x"], shot["y"], keepers & opponents)
    beats.append({"kind": "shot", "t": shot["t"], "player": shot["player"], "x": shot["x"], "y": shot["y"],
                  "end_x": shot.get("end_x", PITCH_LENGTH if team == "home" else 0.0), "end_y": shot.get("end_y", PITCH_WIDTH / 2),
                  "facts": {"xg": shot["xg"], "distance_m": shot["distance_m"], "angle_deg": shot["angle_deg"],
                            "speed_kmh": shot.get("speed_kmh"), "defender_m": shot.get("defender_m"),
                            "defender": shot.get("defender"), "keeper": keeper, "keeper_m": keeper_m,
                            "outcome": shot["outcome"]},
                  "draw": [{"shot": [shot["x"], shot["y"]]}]
                  + ([{"space": shot["player"], "radius_m": shot["defender_m"]}] if shot.get("defender_m") else [])})
    for b in beats:
        b["t"] = round(b["t"], 1)
    return beats
