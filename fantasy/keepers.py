"""Who the other seven teams are probably keeping.

Your league's rule: a keeper costs the round that player was drafted in last
year. That makes the keeper decision a pure surplus calculation — a player who
went in round 10 last season and is a top-20 asset now is nearly free to keep,
while a player who went in round 1 and is still a round-1 asset is worth keeping
only if he's genuinely elite.

So the players most likely to disappear before your draft aren't the best players
outright. They're the ones whose value has moved furthest above what they cost:

    surplus = value now - value of the pick it costs

Last preseason's consensus rank stands in for "what round were they drafted",
which is the right proxy in a league that drafts near consensus: in an 8-team
league, consensus rank N went in round ceil(N / 8).

    python3 keepers.py            # ranked list of likely keepers
    python3 keepers.py 20         # show more

Nothing here is certain. It is a prior over a decision seven other people make
privately, and it beats assuming nobody keeps anyone.
"""

from __future__ import annotations

import csv
import math
import os
import sys

from engine import HERE, build_board, load_league, load_players
from last_season import norm

PREV = os.path.join(HERE, "data", "prev_season_ecr.csv")

# A player who wasn't drafted last year was a waiver add. Most keeper leagues
# charge those the last round; that assumption makes them the cheapest possible
# keeper, so it is the aggressive case. Confirm it with your commissioner.
UNDRAFTED_ROUND = 14


def prev_rounds(teams: int) -> dict[str, int]:
    """Map each player to the round they'd have gone in last year's draft."""
    if not os.path.exists(PREV):
        return {}
    out = {}
    with open(PREV, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                ecr = float(r["ecr"])
            except (TypeError, ValueError):
                continue
            out[norm(r["player"])] = max(1, math.ceil(ecr / teams))
    return out


def pick_value(board, teams: int, rnd: int) -> float:
    """Roughly what a pick in this round is worth, in VORP.

    Uses the middle of the round on your own board — the player you would
    realistically be giving up to spend that pick on a keeper.
    """
    idx = min(len(board) - 1, int(teams * (rnd - 1) + teams / 2))
    return board[idx].vorp


def candidates(board, league, played_last_year=None):
    """Rank players by keeper surplus.

    `played_last_year` is the set of players with 2025 NFL usage. Anyone absent
    from both it and last preseason's rankings is a 2026 rookie — they were never
    drafted last year, so they cannot be kept at any price.
    """
    teams = league["teams"]
    rounds = league["rounds"]
    rnd_of = prev_rounds(teams)
    mine = {norm(k["player"]) for k in league.get("keepers", [])}

    out = []
    for p in board:
        if p.pos in ("K", "DST", "DEF"):
            continue
        key = norm(p.name)
        rookie = key not in rnd_of and (
            played_last_year is not None and key not in played_last_year
        )
        if rookie:
            continue
        rnd = rnd_of.get(key, UNDRAFTED_ROUND)
        rnd = min(rnd, rounds)
        cost = pick_value(board, teams, rnd)
        out.append(
            {
                "player": p,
                "round": rnd,
                "cost": cost,
                "surplus": p.vorp - cost,
                "new": key not in rnd_of,
                "mine": key in mine,
            }
        )
    out.sort(key=lambda d: -d["surplus"])
    return out


def main() -> int:
    league = load_league()
    board = build_board(league, load_players())
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 14

    try:
        from last_season import Season

        played = set(Season(league["scoring"]).rec)
    except OSError:
        played = None
        print("note: no 2025 data, so 2026 rookies cannot be filtered out\n")

    rows = candidates(board, league, played)
    if not os.path.exists(PREV):
        print("missing data/prev_season_ecr.csv — cannot infer last year's rounds")
        return 1

    others = [r for r in rows if not r["mine"]][:limit]
    teams = league["teams"]

    print("Most likely keepers — highest value above what the pick costs.\n")
    print(f"{'PLAYER':<24} {'POS':<5} {'ECR':>5} {'KEPT AT':>8} {'COST':>7} "
          f"{'VALUE':>7} {'SURPLUS':>8}")
    print("-" * 70)
    for r in others:
        p = r["player"]
        tag = f"R{r['round']}" + ("*" if r["new"] else "")
        print(
            f"{p.name:<24} {p.pos + str(p.pos_rank):<5} {p.adp:>5.0f} "
            f"{tag:>8} {r['cost']:>7.1f} {p.vorp:>7.1f} {r['surplus']:>+8.1f}"
        )

    print(f"\n* = not in last preseason's top {len(prev_rounds(teams))}; assumed a "
          f"waiver add costing a round-{UNDRAFTED_ROUND} pick.")
    print(f"\nSeven other teams keep at most seven of these. The top {teams - 1} by "
          "surplus are the\nones to assume are gone — check them against your "
          "board before draft day.")

    mine = [r for r in rows if r["mine"]]
    for r in mine:
        p = r["player"]
        print(f"\nYours: {p.name} at R{r['round']} costs {r['cost']:.1f} VORP for "
              f"{p.vorp:.1f} — surplus {r['surplus']:+.1f}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
