"""Stream a simulated match to the terminal: live stats every minute and key moments as they happen.

    python -m engine.cli --home KR --away AV --seed 7 --scenario data/scenarios/demo.json
"""

from __future__ import annotations

import argparse

from engine.league import build_league
from engine.live import LiveStats
from engine.models import MatchMeta, Moment, TrackingFrame
from engine.sim import MatchSimulator, SimConfig, load_scenario


def _minute_line(live: LiveStats, home: str, away: str) -> str:
    s = live.stats()
    h, d, a = (round(p * 100) for p in s.win_prob)
    return (
        f"{int(s.t // 60):3d}'  {home} {s.score[0]}-{s.score[1]} {away}  "
        f"xG {s.xg[0]:.2f}-{s.xg[1]:.2f}  win {h}/{d}/{a}  "
        f"momentum {s.momentum:+.2f}  control {s.control_index:.2f}  chaos {s.chaos_index:.2f}"
    )


def _moment_line(m: Moment, names: dict[str, str]) -> str:
    who = ", ".join(names.get(p, p) for p in m.players)
    detail = " ".join(f"{k}={v}" for k, v in m.evidence.items() if k != "player")
    return f"      * {m.minute}' {m.kind.upper()} [{m.team or '-'}] {who}  leverage {m.leverage:+.2f}  {detail}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", default="KR")
    parser.add_argument("--away", default="AV")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--scenario")
    parser.add_argument("--mode", choices=["full", "events_only"], default="full")
    parser.add_argument("--half", type=float, default=2700.0, help="seconds per half")
    args = parser.parse_args()

    league = build_league()
    meta = MatchMeta(match_id="m001", home=args.home, away=args.away, seed=args.seed, scenario=args.scenario)
    scenario = load_scenario(args.scenario) if args.scenario else None
    sim = MatchSimulator(meta, league, SimConfig(mode=args.mode, half_s=args.half), scenario)
    live = LiveStats(meta, league)
    names = {p.player_id: p.name for squad in league.squads.values() for p in squad}
    home, away = league.clubs[args.home], league.clubs[args.away]
    print(f"{home.name} v {away.name}  (seed {args.seed})")

    next_minute = 0.0
    for item in sim.run():
        for m in live.push(item):
            print(_moment_line(m, names))
        t = item.t
        if t >= next_minute and (isinstance(item, TrackingFrame) or args.mode == "events_only"):
            print(_minute_line(live, home.short, away.short))
            next_minute = (int(t // 60) + 1) * 60.0

    print("\nFull time:", _minute_line(live, home.short, away.short))
    print("\nTop leverage")
    for r in live.leverage_table()[:5]:
        print(f"  {names[r.player_id]:22s} {r.team:5s} total {r.total:+.2f}  shot {r.shot_making:+.2f}  "
              f"create {r.creation:+.2f}  defend {r.defending:+.2f}  turnovers {r.turnovers:+.2f}")
    print("Press resistance (5+ attempts)")
    for r in [r for r in live.press_table() if r.rate is not None][:5]:
        print(f"  {names[r.player_id]:22s} {r.rate:.0%} of {r.attempts}")
    print("Shots")
    for s in live.shots:
        speed = f"{s.speed_ms * 3.6:.0f} km/h" if s.speed_ms else "-"
        print(f"  {s.minute:3d}' {names[s.player_id]:22s} xG {s.xg:.2f} {s.outcome:10s} {speed}")
    if args.mode == "full":
        print("Team shape")
        for side, team in live.shape.teams.items():
            print(f"  {side}: " + ", ".join(f"{int(t // 60)}' {state}" for t, state in team.timeline))
        fastest = sorted(live.kinematics.runs.items(), key=lambda kv: -kv[1].top_speed_ms)[:3]
        print("Fastest: " + ", ".join(f"{names[p]} {r.top_speed_ms * 3.6:.1f} km/h" for p, r in fastest))


if __name__ == "__main__":
    main()
