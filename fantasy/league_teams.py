"""Score every team in the league on the same board I drafted from.

Rosters are entered by hand in data/league_rosters.json as they get shared.
The point isn't the projected total — it's where each team is thin, because
that is what the waiver wire and the trade market are for.
"""
from __future__ import annotations
import json, os, sys
from collections import defaultdict
from engine import HERE, load_league, load_players, build_board
from last_season import norm

def npos(p): return "DEF" if p in ("DST", "D/ST") else p

def main() -> int:
    lg = load_league(); board = build_board(lg, load_players())
    by = {norm(p.name): p for p in board}
    path = os.path.join(HERE, "data", "league_rosters.json")
    teams = json.load(open(path))

    rows, missing = [], []
    for name, r in teams.items():
        players, pos = [], defaultdict(list)
        for n in r["starters"] + r.get("bench", []):
            p = by.get(norm(n))
            if p is None:
                missing.append((name, n)); continue
            players.append(p); pos[npos(p.pos)].append(p)
        starters = 0.0
        # Best legal lineup from whoever they own.
        used = set()
        for slot, cnt in (("QB",1),("RB",2),("WR",2),("TE",1)):
            for p in sorted(pos[slot], key=lambda x: -x.points)[:cnt]:
                starters += p.points; used.add(id(p))
        flex = [p for p in players if npos(p.pos) in ("RB","WR","TE") and id(p) not in used]
        for p in sorted(flex, key=lambda x: -x.points)[:1]:
            starters += p.points
        rows.append({"team": name, "pts": starters, "pos": pos, "n": len(players),
                     "def": r.get("def")})

    rows.sort(key=lambda r: -r["pts"])
    print(f"\n{'TEAM':<34}{'STARTERS':>10}{'QB':>4}{'RB':>4}{'WR':>4}{'TE':>4}  THIN AT")
    print("-" * 82)
    for i, r in enumerate(rows, 1):
        counts = {k: len(r["pos"][k]) for k in ("QB","RB","WR","TE")}
        thin = []
        if counts["RB"] <= 3: thin.append("RB")
        if counts["WR"] <= 3: thin.append("WR")
        if counts["TE"] <= 1: thin.append("TE")
        if counts["QB"] <= 1: thin.append("QB")
        if not r["def"]: thin.append("NO DEF")
        star = " *" if "(you)" in r["team"] else ""
        print(f"{i}. {r['team']:<31}{r['pts']:>10.0f}"
              f"{counts['QB']:>4}{counts['RB']:>4}{counts['WR']:>4}{counts['TE']:>4}"
              f"  {', '.join(thin) or '—'}{star}")

    if missing:
        print("\nunmatched (fix the name in league_rosters.json):")
        for t, n in missing: print(f"  {t}: {n}")
    print(f"\n{len(rows)} of {lg['teams']} teams entered.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
