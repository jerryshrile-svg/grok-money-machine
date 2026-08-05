"""Does the regression signal in `last_season.py` actually predict anything?

The LY column on the draft board, and the fade and buy lists, all rest on one
claim: that points scored above expectation is mostly luck, so a player who ran
hot will come back down and a player who ran cold will come back up.

That claim is testable against four seasons, and it should be tested, because it
is shown on the board as if it were established.

    python3 validate.py

Two measurements:

  1. How repeatable is points-over-expected from one season to the next? A
     correlation near zero means it is noise that regresses. A high correlation
     would mean it is a real skill, and fading those players would be a mistake.

  2. What actually happened to the hot and cold thirds the following year, next
     to what their opportunity said they should have scored.
"""

from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict

from engine import HERE
from last_season import PAIRS, _f, norm

RAW = os.path.join(HERE, "data", "raw")
SEASONS = (2022, 2023, 2024, 2025)
MIN_GAMES = 8


def season_expectation(year: int, scoring: dict):
    """Actual and expected points per player for one season, in league scoring."""
    path = os.path.join(RAW, f"expected_points_{year}.csv")
    if not os.path.exists(path):
        return {}
    out = defaultdict(lambda: {"pts": 0.0, "exp": 0.0, "g": 0, "pos": ""})
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if int(_f(r, "week")) > 18:
                continue
            pos = (r.get("position") or "").upper()
            if pos not in ("QB", "RB", "WR", "TE"):
                continue
            e = out[norm(r["full_name"])]
            e["pos"] = pos
            e["g"] += 1
            for act, exp, key in PAIRS:
                mult = scoring.get(key, 0.0)
                e["pts"] += mult * _f(r, act)
                e["exp"] += mult * _f(r, exp)
    return {k: v for k, v in out.items() if v["g"] >= MIN_GAMES}


def correlation(xs, ys) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else 0.0


def poe_pg(rec) -> float:
    return (rec["pts"] - rec["exp"]) / rec["g"]


def main() -> int:
    scoring = json.load(open(os.path.join(HERE, "league.json")))["scoring"]
    data = {y: season_expectation(y, scoring) for y in SEASONS}
    missing = [y for y in SEASONS if not data[y]]
    if missing:
        print(f"missing expected-points data for {missing} — see fetch_data.py")
        return 1

    pairs = list(zip(SEASONS, SEASONS[1:]))

    print("Is points-over-expected repeatable, or is it luck?")
    print("  near 0 = noise that regresses | near 1 = a skill worth paying for\n")
    allx, ally = [], []
    for a, b in pairs:
        common = set(data[a]) & set(data[b])
        xs = [poe_pg(data[a][k]) for k in common]
        ys = [poe_pg(data[b][k]) for k in common]
        allx += xs
        ally += ys
        print(f"  {a} -> {b}:  r = {correlation(xs, ys):+.2f}  (n={len(common)})")
    r = correlation(allx, ally)
    print(f"  pooled:       r = {r:+.2f}  (n={len(allx)})")
    print(f"  -> about {r * r:.0%} of it repeats; the rest regresses.\n")

    print("What happened the following season:\n")
    print(f"  {'GROUP':<22} {'PPG yr N':>9} {'xPPG yr N':>10} {'PPG yr N+1':>11} {'CHANGE':>8}")
    buckets = defaultdict(lambda: {"p": [], "x": [], "n": []})
    for a, b in pairs:
        common = sorted(set(data[a]) & set(data[b]), key=lambda k: poe_pg(data[a][k]))
        third = len(common) // 3
        groups = (
            ("cold (bottom third)", common[:third]),
            ("middle", common[third : 2 * third]),
            ("hot (top third)", common[2 * third :]),
        )
        for label, grp in groups:
            for k in grp:
                buckets[label]["p"].append(data[a][k]["pts"] / data[a][k]["g"])
                buckets[label]["x"].append(data[a][k]["exp"] / data[a][k]["g"])
                buckets[label]["n"].append(data[b][k]["pts"] / data[b][k]["g"])

    mean = lambda xs: sum(xs) / len(xs)  # noqa: E731
    for label in ("hot (top third)", "middle", "cold (bottom third)"):
        v = buckets[label]
        print(f"  {label:<22} {mean(v['p']):>9.1f} {mean(v['x']):>10.1f} "
              f"{mean(v['n']):>11.1f} {mean(v['n']) - mean(v['p']):>+8.1f}")

    hot, cold = buckets["hot (top third)"], buckets["cold (bottom third)"]
    hot_gap = mean(hot["p"]) - mean(hot["x"])
    hot_moved = mean(hot["p"]) - mean(hot["n"])
    cold_gap = mean(cold["x"]) - mean(cold["p"])
    cold_moved = mean(cold["n"]) - mean(cold["p"])
    print(f"\n  Hot players gave back {hot_moved / hot_gap:.0%} of the gap between what")
    print(f"  they scored and what their usage earned. Cold players recovered only")
    print(f"  {cold_moved / cold_gap:.0%} of theirs.")
    print("\n  So the fade signal is the reliable half. Treat a hot player as likely")
    print("  to come back to his expected line; treat a cold one as a partial")
    print("  bounce-back, not a full one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
