"""Is total points the right thing to be maximising?

Everything measured so far scores a roster on its season total across weeks 1-17.
That is a proxy, and in this league it is a questionable one.

Six of eight teams make the playoffs. Qualifying is nearly free — you have to be
bad, not merely unlucky, to miss. So regular-season points past the qualifying
threshold buy very little, and the season is decided in weeks 15, 16 and 17.
A roster built to accumulate points from September could be the wrong roster.

Two questions, cheapest first:

  1. Does the strategy ranking change when you score only the playoff weeks?
     If wait-cost still wins there, the proxy was fine and there is nothing to fix.

  2. Does drafting for ceiling beat drafting for expected points? When
     qualification is close to free, variance is worth more than it looks —
     you need three good weeks, not sixteen average ones.

Both run on the same replayed seasons and the same paired seeds as backtest.py,
so the numbers are comparable to the +30 +/- 2 already on record.

    python3 objective.py            # both questions, 200 drafts per arm
    python3 objective.py 400
"""

from __future__ import annotations

import math
import random
import sys
from collections import defaultdict

import backtest
import sim
from engine import Player, build_board, load_league
from last_season import norm

# Weeks 15-17 in a replayed season are the same weeks this league plays its
# playoffs, so no mapping is needed.
PLAYOFF_WEEKS = (15, 16, 17)

ARMS = {
    "Wait-cost (live tool)": ["WAIT"] * 14,
    "Consensus list": ["ECR"] * 14,
    "Zero RB": sim.STRATEGIES["Zero RB"],
    "RB heavy": sim.STRATEGIES["RB heavy"],
}


def score_weeks(roster, actuals, league, weeks) -> float:
    """backtest.score_roster, restricted to a chosen set of weeks."""
    original = backtest.WEEKS
    backtest.WEEKS = weeks
    try:
        return backtest.score_roster(roster, actuals, league)
    finally:
        backtest.WEEKS = original


def ceiling_board(base, league, weight: float):
    """Rebuild the board valuing upside, using the experts' own disagreement.

    `ceiling` is a player's best-case rank run through the same points curve, so
    a player the panel argues about is worth more here than one they agree on.
    weight 0 is the current board; weight 1 drafts purely off the optimistic case.
    """
    if weight == 0.0:
        return base
    players = []
    for p in base:
        ceil = getattr(p, "ceiling", None) or p.points
        q = Player(name=p.name, pos=p.pos, team=p.team, adp=p.adp,
                   points=(1.0 - weight) * p.points + weight * ceil)
        q.ecr_best, q.ecr_worst = p.ecr_best, p.ecr_worst
        players.append(q)
    return build_board(league, players)


def paired(a, b):
    diffs = [x - y for x, y in zip(a, b)]
    mu = sum(diffs) / len(diffs)
    if len(diffs) < 2:
        return mu, 0.0
    var = sum((d - mu) ** 2 for d in diffs) / (len(diffs) - 1)
    return mu, math.sqrt(var / len(diffs))


def run_strategies(seasons, n, league):
    """Every strategy, scored twice: whole season, and playoff weeks only."""
    full: dict[str, list[float]] = defaultdict(list)
    post: dict[str, list[float]] = defaultdict(list)
    for season in seasons:
        board = backtest.season_board(season, league)
        actuals = backtest.weekly_actuals(season, league["scoring"])
        for label, strat in ARMS.items():
            for i in range(n):
                rng = random.Random(season * 100_003 + i)
                roster = sim.run_draft(board, league, strat, rng, keeper_count=0)
                full[label].append(
                    score_weeks(roster, actuals, league, range(1, 18)))
                post[label].append(
                    score_weeks(roster, actuals, league, PLAYOFF_WEEKS))
    return full, post


def run_ceiling(seasons, n, league, weights=(0.0, 0.25, 0.5)):
    """The same rule, drafting off boards that value upside differently."""
    full: dict[float, list[float]] = defaultdict(list)
    post: dict[float, list[float]] = defaultdict(list)
    for season in seasons:
        base = backtest.season_board(season, league)
        actuals = backtest.weekly_actuals(season, league["scoring"])
        boards = {w: ceiling_board(base, league, w) for w in weights}
        for i in range(n):
            for w in weights:
                rng = random.Random(season * 100_003 + i)
                roster = sim.run_draft(boards[w], league, ["WAIT"] * 14, rng,
                                       keeper_count=0)
                full[w].append(score_weeks(roster, actuals, league, range(1, 18)))
                post[w].append(score_weeks(roster, actuals, league, PLAYOFF_WEEKS))
    return full, post


def _table(rows, base_label, title, unit):
    print(f"\n{title}")
    print("-" * 68)
    print(f"{'ARM':<24} {'POINTS':>9} {'vs BASELINE':>16}  VERDICT")
    base = rows[base_label]
    ordered = sorted(rows.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))
    for label, vals in ordered:
        gain, se = paired(vals, base)
        if label == base_label:
            verdict = "baseline"
            pm = ""
        else:
            pm = f" ± {se:.1f}"
            verdict = ("real, better" if gain > 2 * se else
                       "real, worse" if gain < -2 * se else "inside the noise")
        print(f"{str(label):<24} {sum(vals) / len(vals):>9.0f} "
              f"{gain:>+11.1f}{pm:<5} {verdict}")
    print(f"({unit})")


def main() -> int:
    gone = backtest.missing_seasons()
    if gone:
        print(f"missing back-season data: {', '.join(gone)}")
        print("run 'python3 fetch_data.py history' first.")
        return 1

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(args[0]) if args else 200
    seasons = list(backtest.TEST_SEASONS)

    league = load_league()
    league = dict(league, keepers=[],
                  opponent_keepers={"known": [], "unknown_count": 0})

    print(f"Objective check — {n} paired drafts per arm per season, "
          f"{len(seasons)} seasons.")
    print("Six of eight teams make these playoffs, so weeks 15-17 decide the year.")

    full, post = run_strategies(seasons, n, league)
    _table(full, "Consensus list",
           "QUESTION 1a — strategies scored on the whole season",
           "points over the full 17 weeks")
    _table(post, "Consensus list",
           "QUESTION 1b — the same drafts, scored on weeks 15-17 only",
           "points over three playoff weeks")

    cfull, cpost = run_ceiling(seasons, n, league)
    _table({f"ceiling weight {w:.2f}": v for w, v in cfull.items()},
           "ceiling weight 0.00",
           "QUESTION 2a — drafting for upside, scored on the whole season",
           "points over the full 17 weeks")
    _table({f"ceiling weight {w:.2f}": v for w, v in cpost.items()},
           "ceiling weight 0.00",
           "QUESTION 2b — drafting for upside, scored on weeks 15-17 only",
           "points over three playoff weeks")

    print("\nA playoff-week edge is worth roughly six times a whole-season one "
          "per point,\nbecause it lands on three weeks instead of seventeen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
