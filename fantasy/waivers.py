"""Who is actually unowned, now that every roster is known.

The whole structural edge in an 8-team league is that ~56 players who would
be rostered in a 12-team league are sitting free. That is only actionable once
you know all eight rosters, which is what data/league_rosters.json is for.

    python3 waivers.py         # best available, by position
    python3 waivers.py 40      # deeper
"""
from __future__ import annotations
import json, os, sys
from collections import defaultdict
from engine import HERE, load_league, load_players, build_board
from last_season import norm

def npos(p): return "DEF" if p in ("DST", "D/ST") else p

def main() -> int:
    lg = load_league(); board = build_board(lg, load_players())
    teams = json.load(open(os.path.join(HERE, "data", "league_rosters.json")))

    owned = set()
    for r in teams.values():
        for n in r["starters"] + r.get("bench", []):
            owned.add(norm(n))
    for k in lg.get("keepers", []):
        owned.add(norm(k["player"]))

    free = [p for p in board
            if norm(p.name) not in owned and npos(p.pos) in ("QB", "RB", "WR", "TE")]
    depth = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8

    print(f"\n{len(owned)} players owned across {len(teams)} teams. "
          f"Best of what's left:\n")
    by = defaultdict(list)
    for p in free:
        by[npos(p.pos)].append(p)
    for pos in ("QB", "RB", "WR", "TE"):
        pool = sorted(by[pos], key=lambda p: -p.points)[:depth]
        print(f"  {pos}")
        for p in pool:
            flag = "  <- startable now" if p.vorp > 0 else ""
            print(f"    {p.name:<26}{pos}{p.pos_rank:<4} ECR {p.adp:>6.1f}  "
                  f"VORP {p.vorp:>+7.1f}{flag}")
        print()
    print("VORP above 0 means he would beat the last man you can start at that")
    print("position. In this league those are sitting free — that is the edge.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
