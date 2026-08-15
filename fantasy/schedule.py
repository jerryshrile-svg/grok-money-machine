"""Your weekly opponent, and how tough that matchup actually is.

data/league_schedule.json holds the head-to-head schedule as it's shared
week by week — Yahoo doesn't expose the whole season until it plays out, so
this fills in as far as it's known. Paired with league_teams.py's roster
strength, it turns "who am I playing" into "how worried should I be".

    python3 schedule.py          # every known week
    python3 schedule.py 3        # one week
"""
from __future__ import annotations
import json, os, sys
from engine import HERE, load_league, load_players, build_board
from league_teams import npos

ME = "Bijan MUSTAAAAAAAADD (you)"

def team_strengths():
    lg = load_league(); board = build_board(lg, load_players())
    by = {p.name: p for p in board}
    from last_season import norm
    by = {norm(p.name): p for p in board}
    rosters = json.load(open(os.path.join(HERE, "data", "league_rosters.json")))
    out = {}
    for name, r in rosters.items():
        players, pos = [], {}
        for n in r["starters"] + r.get("bench", []):
            p = by.get(norm(n))
            if p is None:
                continue
            players.append(p)
            pos.setdefault(npos(p.pos), []).append(p)
        starters, used = 0.0, set()
        for slot, cnt in (("QB",1),("RB",2),("WR",2),("TE",1)):
            for p in sorted(pos.get(slot, []), key=lambda x: -x.points)[:cnt]:
                starters += p.points; used.add(id(p))
        flex = [p for p in players if npos(p.pos) in ("RB","WR","TE") and id(p) not in used]
        for p in sorted(flex, key=lambda x: -x.points)[:1]:
            starters += p.points
        out[name] = starters
    return out

def main() -> int:
    path = os.path.join(HERE, "data", "league_schedule.json")
    if not os.path.exists(path):
        print("no schedule recorded yet")
        return 1
    sched = json.load(open(path))
    strength = team_strengths()
    weeks = [sys.argv[1]] if len(sys.argv) > 1 else sorted(sched, key=int)

    print(f"{'WK':<4}{'OPPONENT':<34}{'THEIR PROJ':>11}{'YOUR PROJ':>11}{'EDGE':>8}")
    print("-" * 70)
    mine = strength.get(ME, 0.0)
    for wk in weeks:
        games = sched.get(wk)
        if not games:
            print(f"week {wk} not recorded"); continue
        opp = next((b if a == ME else a for a, b in games if ME in (a, b)), None)
        if opp is None:
            print(f"{wk:<4}(bye or not yet known)"); continue
        theirs = strength.get(opp, 0.0)
        edge = mine - theirs
        flag = "  <- close one" if abs(edge) < 40 else ("  <- favored" if edge > 0 else "  <- underdog")
        print(f"{wk:<4}{opp:<34}{theirs:>11.0f}{mine:>11.0f}{edge:>+8.0f}{flag}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
