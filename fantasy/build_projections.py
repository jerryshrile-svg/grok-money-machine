"""Turn free public data into projections in your league's scoring.

The method, stated plainly so you know what you're trusting:

  1. Take three seasons of *actual* NFL results (nflverse) and score every
     player-season under your league's exact rules — 0.5 PPR, your TD values.
  2. For each position, build the historical curve of "what did the #N finisher
     at this position actually score?", averaged across those seasons.
  3. Take the current FantasyPros expert consensus ranking (updated weekly) as
     the market's opinion of *who* finishes where in 2026.
  4. Map each player's consensus positional rank onto that historical curve.

So the player ordering is the consensus's, and the points scale is real NFL
history in your scoring. That is exactly what a value-based draft board needs:
VORP and tiers depend on the *shape* of the points curve, not on nailing any one
player's total.

What this is not: an independent opinion on players. It cannot tell you the
consensus is wrong about someone. It inherits the market's read and converts it
into your format — which is where the edge is, since your leaguemates are using
that same consensus in a format it wasn't built for.

Ceiling and floor come from the experts' own disagreement: each player's best-
and worst-case rank across the panel, run through the same curve.

    python3 build_projections.py
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict

from engine import HERE, load_league

RAW = os.path.join(HERE, "data", "raw")
OUT = os.path.join(HERE, "data", "projections.csv")

SEASONS = (2023, 2024, 2025)
SKILL = ("QB", "RB", "WR", "TE")

# nflverse column -> scoring key in league.json
STAT_MAP = {
    "passing_yards": "pass_yd",
    "passing_tds": "pass_td",
    "passing_interceptions": "pass_int",
    "rushing_yards": "rush_yd",
    "rushing_tds": "rush_td",
    "receptions": "rec",
    "receiving_yards": "rec_yd",
    "receiving_tds": "rec_td",
}
FUMBLE_COLS = ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost")
TWOPT_COLS = (
    "passing_2pt_conversions",
    "rushing_2pt_conversions",
    "receiving_2pt_conversions",
)


def _f(row: dict, key: str) -> float:
    v = row.get(key)
    if v in (None, "", "NA"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def season_totals(season: int, scoring: dict) -> dict[str, tuple[str, float]]:
    """Score every player's regular season under the league's rules."""
    path = os.path.join(RAW, f"stats_{season}.csv")
    totals: dict[str, float] = defaultdict(float)
    pos_of: dict[str, str] = {}

    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("season_type") != "REG":
                continue
            pos = (row.get("position") or "").upper()
            if pos not in SKILL:
                continue
            name = row.get("player_display_name") or row.get("player_name") or ""
            if not name:
                continue

            pts = sum(
                scoring.get(skey, 0.0) * _f(row, col) for col, skey in STAT_MAP.items()
            )
            pts += scoring.get("fumble_lost", 0.0) * sum(_f(row, c) for c in FUMBLE_COLS)
            pts += scoring.get("two_pt", 0.0) * sum(_f(row, c) for c in TWOPT_COLS)

            totals[name] += pts
            pos_of[name] = pos

    return {n: (pos_of[n], p) for n, p in totals.items()}


def points_curve(scoring: dict) -> dict[str, list[float]]:
    """Historical points by positional finish, averaged over recent seasons."""
    per_season: dict[str, list[list[float]]] = defaultdict(list)

    for season in SEASONS:
        totals = season_totals(season, scoring)
        by_pos: dict[str, list[float]] = defaultdict(list)
        for _, (pos, pts) in totals.items():
            by_pos[pos].append(pts)
        for pos, vals in by_pos.items():
            vals.sort(reverse=True)
            per_season[pos].append(vals)

    curve: dict[str, list[float]] = {}
    for pos, seasons in per_season.items():
        depth = min(len(s) for s in seasons)
        avg = [sum(s[i] for s in seasons) / len(seasons) for i in range(depth)]
        # Light smoothing — individual finishes are noisy, the shape is not.
        smoothed = []
        for i in range(len(avg)):
            lo, hi = max(0, i - 2), min(len(avg), i + 3)
            smoothed.append(sum(avg[lo:hi]) / (hi - lo))
        curve[pos] = smoothed
    return curve


def at_rank(curve: list[float], rank: int) -> float:
    if not curve:
        return 0.0
    return curve[min(max(rank, 1), len(curve)) - 1]


def load_consensus() -> list[dict]:
    path = os.path.join(RAW, "fp_ecr.csv")
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("page_type") != "redraft-overall":
                continue
            if not r.get("ecr"):
                continue
            rows.append(r)
    return rows


def positional_ranks(rows: list[dict], key: str) -> dict[int, int]:
    """Rank within position by some ECR field. Returns row-index -> rank."""
    out: dict[int, int] = {}
    by_pos: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for i, r in enumerate(rows):
        raw = r.get(key) or r.get("ecr")
        try:
            val = float(raw)
        except (TypeError, ValueError):
            val = float(r["ecr"])
        by_pos[r["pos"].upper()].append((val, i))
    for pos, items in by_pos.items():
        items.sort()
        for rank, (_, i) in enumerate(items, 1):
            out[i] = rank
    return out


def main() -> int:
    league = load_league()
    scoring = league["scoring"]

    curve = points_curve(scoring)
    print("Historical points by positional finish (avg of "
          f"{', '.join(str(s) for s in SEASONS)}, in your scoring):")
    for pos in SKILL:
        c = curve.get(pos, [])
        marks = [1, 6, 12, 24, 36]
        parts = [f"{pos}{m}={at_rank(c, m):.0f}" for m in marks if m <= len(c)]
        print("  " + "  ".join(parts))
    print()

    rows = load_consensus()
    rank_ecr = positional_ranks(rows, "ecr")
    rank_best = positional_ranks(rows, "best")
    rank_worst = positional_ranks(rows, "worst")

    # Kickers and defenses get a flat nominal value; the engine zeroes their
    # VORP anyway, they just need to sort sanely for the last two rounds.
    flat = {"K": 130.0, "DST": 120.0}

    out_rows = []
    for i, r in enumerate(rows):
        pos = r["pos"].upper()
        prank = rank_ecr[i]
        if pos in flat:
            pts = ceil = floor = flat[pos] - prank * 0.5
        else:
            c = curve.get(pos, [])
            if not c:
                continue
            pts = at_rank(c, prank)
            ceil = at_rank(c, rank_best[i])
            floor = at_rank(c, rank_worst[i])

        out_rows.append(
            {
                "name": r["player"],
                "pos": pos,
                "team": r.get("team") or r.get("tm") or "",
                "adp": round(float(r["ecr"]), 1),
                "points": round(pts, 1),
                "ceiling": round(ceil, 1),
                "floor": round(floor, 1),
                "ecr_sd": r.get("sd") or "",
                "ecr_best": r.get("best") or "",
                "ecr_worst": r.get("worst") or "",
                "bye": r.get("bye") or "",
                "yahoo_id": r.get("yahoo_id") or "",
            }
        )

    out_rows.sort(key=lambda r: r["adp"])
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    scrape = rows[0].get("scrape_date", "?")
    counts: dict[str, int] = defaultdict(int)
    for r in out_rows:
        counts[r["pos"]] += 1
    print(f"Consensus scraped {scrape} — wrote {len(out_rows)} players to")
    print(f"  {OUT}")
    print("  " + "  ".join(f"{p}={counts[p]}" for p in ("QB", "RB", "WR", "TE", "K", "DST")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
