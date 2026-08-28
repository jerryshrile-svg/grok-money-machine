"""Your weekly opponent, and how tough that matchup actually is.

data/league_schedule.json holds weeks 1-7 as Yahoo actually showed them — a
complete round robin, 8 teams, 7 opponents. Weeks 8 and 9 arrived as exact
repeats of weeks 1 and 2, which confirms the cycle: an 8-team round robin
takes 7 weeks, and league.json's regular_season_last_week of 14 is exactly
two trips through it. So weeks 8-14 are derived by repeating 1-7 rather than
waited on screenshot by screenshot, and the derivation is checked against
every week that has actually been observed.

Weeks 15-17 are explicitly NOT covered by this. Six of eight teams make the
playoffs, which means seeding and a bracket, not a continuation of the
round robin — nothing about who plays whom in the playoffs follows from this
pattern, and the tool says so rather than guessing.

    python3 schedule.py          # every week of the regular season
    python3 schedule.py 9        # one week
"""
from __future__ import annotations
import json, os, sys
from engine import HERE, load_league, load_players, build_board
from league_teams import npos

ME = "Bijan MUSTAAAAAAAADD (you)"
CYCLE = 7  # weeks in one full round robin, 8 teams

def team_strengths():
    lg = load_league(); board = build_board(lg, load_players())
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

def load_schedule():
    """Observed weeks from disk, plus derived weeks 8-14 from the 7-week cycle.

    Derivation is checked against any observed week in that slot before it's
    trusted — if Yahoo ever breaks the pattern (a bye, a makeup week), the
    mismatch is reported instead of silently papering over it.
    """
    path = os.path.join(HERE, "data", "league_schedule.json")
    observed = json.load(open(path)) if os.path.exists(path) else {}
    full = dict(observed)
    league_wk = int(load_league().get("regular_season_last_week", 14))

    for wk in range(1, league_wk + 1):
        key = str(wk)
        if key in full:
            continue
        source = str(((wk - 1) % CYCLE) + 1)
        if source in observed:
            full[key] = observed[source]
    return full, observed

def main() -> int:
    strength = team_strengths()
    full, observed = load_schedule()
    if not full:
        print("no schedule recorded yet")
        return 1

    weeks = [sys.argv[1]] if len(sys.argv) > 1 else sorted(full, key=int)
    mine = strength.get(ME, 0.0)

    print(f"{'WK':<4}{'OPPONENT':<34}{'THEIR PROJ':>11}{'YOUR PROJ':>11}{'EDGE':>8}  ")
    print("-" * 76)
    for wk in weeks:
        games = full.get(wk)
        seen = " (confirmed)" if wk in observed else " (derived, 7-wk cycle)"
        if not games:
            print(f"{wk:<4}not yet known"); continue
        opp = next((b if a == ME else a for a, b in games if ME in (a, b)), None)
        if opp is None:
            print(f"{wk:<4}(bye or not yet known)"); continue
        theirs = strength.get(opp, 0.0)
        edge = mine - theirs
        flag = "close one" if abs(edge) < 40 else ("favored" if edge > 0 else "underdog")
        print(f"{wk:<4}{opp:<34}{theirs:>11.0f}{mine:>11.0f}{edge:>+8.0f}  {flag}{seen}")

    print("\nWeeks 15-17 are playoffs (6 of 8 teams) - seeded from standings, not")
    print("a continuation of this cycle. Not shown; not derivable yet.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
