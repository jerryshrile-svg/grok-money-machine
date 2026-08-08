"""Would any of this actually have worked?

Everything else in this toolkit is checked for internal consistency. This is the
only file that checks it against reality: it replays five real drafts using only
what was knowable each August, then scores the resulting rosters on what those
players actually did.

The rules that keep it honest:

  - The points curve for season S is built from seasons S-3 to S-1 only. Using
    later results would leak the answer into the projection.
  - Player values come from that August's expert consensus, not this year's.
  - Lineups are set each week without hindsight: you start your highest-projected
    players who actually played, exactly as a manager would.
  - Scoring is that season's real weekly production in this league's rules.

Kickers and defenses are excluded from scoring — their weekly stats aren't in
this dataset — so the seven skill starting slots are what's measured. Every
strategy drafts K and DEF in the last two rounds, so the omission is uniform.

    python3 backtest.py            # all seasons, all strategies
    python3 backtest.py 2024       # one season
    python3 backtest.py 2024 40    # one season, 40 drafts per strategy
    python3 backtest.py all 800    # every season, 800 drafts per strategy
"""

from __future__ import annotations

import csv
import math
import os
import random
import sys
from collections import defaultdict

import sim
from build_projections import at_rank, points_curve
from engine import HERE, Player, build_board, load_league
from last_season import norm

HIST = os.path.join(HERE, "data", "history")
RAW = os.path.join(HERE, "data", "raw")

TEST_SEASONS = (2021, 2022, 2023, 2024, 2025)
CURVE_LOOKBACK = 3
WEEKS = range(1, 18)

STAT_MAP = {
    "passing_yards": "pass_yd", "passing_tds": "pass_td",
    "passing_interceptions": "pass_int", "rushing_yards": "rush_yd",
    "rushing_tds": "rush_td", "receptions": "rec",
    "receiving_yards": "rec_yd", "receiving_tds": "rec_td",
}
FUMBLES = ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost")

STRATEGIES = {
    "Consensus list": ["ECR"] * 14,
    "BPA (my board)": ["BPA"] * 14,
    "RB heavy": sim.STRATEGIES["RB heavy"],
    "Zero RB": sim.STRATEGIES["Zero RB"],
    "Wait-cost (live tool)": ["WAIT"] * 14,
}


def _f(row, key):
    v = row.get(key)
    if v in (None, "", "NA"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def weekly_actuals(season: int, scoring: dict) -> dict[int, dict[str, float]]:
    """What every player actually scored, by week, in this league's rules."""
    path = os.path.join(RAW, f"stats_{season}.csv")
    out: dict[int, dict[str, float]] = defaultdict(dict)
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("season_type") != "REG":
                continue
            if (row.get("position") or "").upper() not in ("QB", "RB", "WR", "TE"):
                continue
            wk = int(_f(row, "week"))
            name = norm(row.get("player_display_name") or "")
            if not name:
                continue
            pts = sum(scoring.get(k, 0.0) * _f(row, c) for c, k in STAT_MAP.items())
            pts += scoring.get("fumble_lost", 0.0) * sum(_f(row, c) for c in FUMBLES)
            out[wk][name] = out[wk].get(name, 0.0) + pts
    return out


def season_board(season: int, league: dict):
    """The board as it could have been built that August, with no lookahead."""
    scoring = league["scoring"]
    curve = points_curve(scoring, range(season - CURVE_LOOKBACK, season))

    path = os.path.join(HIST, f"ecr_{season}.csv")
    rows = [r for r in csv.DictReader(open(path, newline="")) if r.get("ecr")]

    by_pos: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_pos[r["pos"].upper()].append(float(r["ecr"]))
    rank = {}
    for pos, ecrs in by_pos.items():
        for i, e in enumerate(sorted(ecrs), 1):
            rank[(pos, e)] = i

    players = []
    for r in rows:
        pos = r["pos"].upper()
        ecr = float(r["ecr"])
        if pos in ("K", "DST", "DEF"):
            pts = 130.0 - rank.get((pos, ecr), 30) * 0.5
        else:
            c = curve.get(pos)
            if not c:
                continue
            pts = at_rank(c, rank[(pos, ecr)])
        p = Player(name=r["player"], pos=pos, team=(r.get("team") or "").upper(),
                   adp=ecr, points=pts)
        for attr, key in (("ecr_best", "best"), ("ecr_worst", "worst")):
            if r.get(key):
                try:
                    setattr(p, attr, float(r[key]))
                except ValueError:
                    pass
        players.append(p)
    return build_board(league, players)


def score_roster(roster, actuals, league) -> float:
    """Season total, with lineups set weekly and no hindsight.

    Each week you start your highest-projected players among those who actually
    played. That is what a manager does: you don't know in advance which of your
    starters is about to have a bad game, only which ones are on a bye or out.
    """
    slots = league["roster"]
    flex_ok = set(league.get("flex_eligible", ["RB", "WR", "TE"]))
    skill = [p for p in roster if p.pos in ("QB", "RB", "WR", "TE")]
    # Ranked by preseason projection — the only ordering available at the time.
    skill.sort(key=lambda p: -p.points)
    keys = {id(p): norm(p.name) for p in skill}

    total = 0.0
    for wk in WEEKS:
        week_pts = actuals.get(wk, {})
        available = [p for p in skill if keys[id(p)] in week_pts]
        used, by_pos = set(), defaultdict(list)
        for p in available:
            by_pos[p.pos].append(p)

        for pos in ("QB", "RB", "WR", "TE"):
            for p in by_pos[pos][: slots.get(pos, 0)]:
                total += week_pts[keys[id(p)]]
                used.add(id(p))
        flex = [p for p in available if p.pos in flex_ok and id(p) not in used]
        for p in flex[: slots.get("FLEX", 0)]:
            total += week_pts[keys[id(p)]]
    return total


def match_rate(board, actuals) -> float:
    played = set()
    for wk in actuals.values():
        played.update(wk)
    top = [p for p in board[:112] if p.pos in ("QB", "RB", "WR", "TE")]
    hit = sum(1 for p in top if norm(p.name) in played)
    return hit / len(top) if top else 0.0


def run_season(season: int, league: dict, n: int, seed: int = 99):
    """Score every strategy on the same n drafts.

    Draft i uses the same seed for every strategy, so all of them face the same
    opponent behaviour and the same board state. That pairing is what makes the
    comparison sharp: the noise from one lucky draft hits every strategy equally
    and cancels in the difference, instead of being mistaken for an edge.
    """
    board = season_board(season, league)
    actuals = weekly_actuals(season, league["scoring"])
    results = {}
    for label, strat in STRATEGIES.items():
        totals = []
        for i in range(n):
            rng = random.Random(seed * 100_003 + i)
            roster = sim.run_draft(board, league, strat, rng, keeper_count=0)
            totals.append(score_roster(roster, actuals, league))
        results[label] = totals
    return results, match_rate(board, actuals)


def _mean(xs):
    return sum(xs) / len(xs)


def _stderr(xs):
    """Standard error of the mean — how much this estimate would wobble."""
    n = len(xs)
    if n < 2:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var / n)


def missing_seasons() -> list[str]:
    """Season stat files this replay needs but that were never downloaded.

    Checked up front rather than discovered as a FileNotFoundError halfway
    through, because the fix is one command and a traceback doesn't say so.
    """
    needed = set()
    for season in TEST_SEASONS:
        needed.add(season)
        needed.update(range(season - CURVE_LOOKBACK, season))
    return sorted(
        f"stats_{y}.csv" for y in needed
        if not os.path.exists(os.path.join(HERE, "data", "raw", f"stats_{y}.csv"))
    )


def main() -> int:
    gone = missing_seasons()
    if gone:
        print(f"missing back-season data: {', '.join(gone)}")
        print("run 'python3 fetch_data.py history' first.")
        return 1

    league = load_league()
    # Keepers are unknown historically and irrelevant to what's being tested.
    league = dict(league, keepers=[], opponent_keepers={"known": [], "unknown_count": 0})

    args = sys.argv[1:]
    # A season number, or anything else ("all") to keep every season while still
    # setting the sample size. A bare "0" used to parse as a season and crash.
    if args and args[0].isdigit() and int(args[0]) in TEST_SEASONS:
        seasons = [int(args[0])]
    else:
        seasons = list(TEST_SEASONS)
    n = int(args[1]) if len(args) > 1 else 40

    print(f"Backtest — {n} drafts per strategy per season, scored on real results.")
    print("Points are the seven skill starting slots over weeks 1-17.\n")

    per_season = defaultdict(list)   # strategy -> per-season mean difference
    pooled = defaultdict(list)       # strategy -> every paired difference
    for season in seasons:
        res, mr = run_season(season, league, n)
        base = res["Consensus list"]
        print(f"--- {season} --- (name match {mr:.0%})")
        print(f"{'STRATEGY':<24} {'ACTUAL PTS':>11} {'vs CONSENSUS':>20}")
        ordered = sorted(res.items(), key=lambda kv: -_mean(kv[1]))
        for label, totals in ordered:
            diffs = [a - b for a, b in zip(totals, base)]
            per_season[label].append(_mean(diffs))
            pooled[label].extend(diffs)
            se = _stderr(diffs)
            print(f"{label:<24} {_mean(totals):>11.0f} "
                  f"{_mean(diffs):>+13.0f} ± {se:>4.0f}")
        print()

    if len(seasons) > 1:
        print("=== Across all seasons, points above simply drafting the list ===")
        print(f"{'STRATEGY':<24} {'MEAN':>8} {'± SE':>6} {'WINS':>7}  VERDICT")
        for label, diffs in sorted(per_season.items(), key=lambda kv: -sum(kv[1])):
            wins = sum(1 for d in diffs if d > 0)
            mu, se = _mean(pooled[label]), _stderr(pooled[label])
            if label == "Consensus list":
                verdict = "baseline"
            elif abs(mu) < 2 * se:
                verdict = "inside the noise"
            else:
                verdict = "real" if mu > 0 else "real, and bad"
            print(f"{label:<24} {mu:>+8.0f} {se:>6.0f} {wins:>4}/{len(diffs)}  {verdict}")
        print("\nSE is the standard error of the paired difference. A gap smaller")
        print("than about two standard errors is not distinguishable from noise.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
