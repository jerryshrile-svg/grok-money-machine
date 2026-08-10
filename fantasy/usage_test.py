"""Does prior-season usage add anything the consensus hasn't already priced?

The board ignores snap share and target share. The argument for that is that the
expert panel has had all offseason to look at the same numbers, so a player's
usage is already inside his ranking and adding it again double-counts. The
argument against is that markets are slow on workload, and `waiver_signal.py`
already measured opportunity beating raw points by +11 +/- 3 in-season.

Neither argument is evidence. This is the experiment.

Every arm drafts the same five real seasons with the same rule (wait-cost), the
same opponents and the same random seeds. The only difference is the board: one
arm uses the plain consensus board, the others nudge each player's projection by
his prior-year usage residual from `usage.py`, at increasing strength.

    points * (1 + k * residual)

k = 0 is the current toolkit. The sweep exists because a single hand-picked k
proves nothing — if the answer flips sign depending on a knob nobody measured,
that is worth knowing before trusting it.

Reading the result honestly: picking the best k after seeing all five seasons is
fitting the test set. `--loso` guards against that by choosing k on four seasons
and scoring it on the fifth, which is the only number that answers "would this
have helped me in a season I had not already seen".

A negative result invites the obvious objection: maybe the composite measure was
badly built, not the idea. So `--measure` runs the same experiment on target rate
alone and on snap percentage alone, which are the two things people actually mean
when they ask whether usage is in the board.

    python3 usage_test.py                      # sweep, 200 drafts per arm/season
    python3 usage_test.py 400                  # more drafts
    python3 usage_test.py 400 --loso           # leave-one-season-out honesty check
    python3 usage_test.py 300 --measure target # target rate on its own
    python3 usage_test.py 300 --measure snap   # snap share on its own
"""

from __future__ import annotations

import math
import random
import sys
from collections import defaultdict

import backtest
import sim
import usage
from engine import Player, build_board, load_league
from last_season import norm

STRENGTHS = (0.0, 0.03, 0.06, 0.10, 0.15)


def adjusted_board(season: int, league: dict, base, k: float):
    """Rebuild the board with each projection nudged by prior-year usage.

    Rebuilt rather than patched in place, because replacement levels, VORP and
    tiers are all derived from the points column — changing it and keeping the
    old tiers would measure a board that never existed.
    """
    if k == 0.0:
        return base
    resid = usage.for_season(season, base)
    players = []
    for p in base:
        r = resid.get(norm(p.name), 0.0)
        q = Player(name=p.name, pos=p.pos, team=p.team, adp=p.adp,
                   points=p.points * (1.0 + k * r))
        q.ecr_best, q.ecr_worst = p.ecr_best, p.ecr_worst
        players.append(q)
    return build_board(league, players)


def run(seasons, n, league):
    """Paired totals per arm. Same seeds across arms, so the noise cancels."""
    rows: dict[float, dict[int, list[float]]] = {k: defaultdict(list) for k in STRENGTHS}
    for season in seasons:
        base = backtest.season_board(season, league)
        actuals = backtest.weekly_actuals(season, league["scoring"])
        boards = {k: adjusted_board(season, league, base, k) for k in STRENGTHS}
        for i in range(n):
            for k in STRENGTHS:
                rng = random.Random(season * 100_003 + i)
                roster = sim.run_draft(boards[k], league, ["WAIT"] * league["rounds"],
                                       rng, keeper_count=0)
                rows[k][season].append(
                    backtest.score_roster(roster, actuals, league)
                )
    return rows


def paired(a: list[float], b: list[float]) -> tuple[float, float]:
    diffs = [x - y for x, y in zip(a, b)]
    mu = sum(diffs) / len(diffs)
    if len(diffs) < 2:
        return mu, 0.0
    var = sum((d - mu) ** 2 for d in diffs) / (len(diffs) - 1)
    return mu, math.sqrt(var / len(diffs))


def _pool(rows, k, seasons):
    out = []
    for s in seasons:
        out.extend(rows[k][s])
    return out


def report(rows, seasons):
    base = _pool(rows, 0.0, seasons)
    print(f"\n{'USAGE WEIGHT':<14} {'SEASON PTS':>11} {'vs PLAIN BOARD':>17} "
          f"{'WINS':>6}  VERDICT")
    print("-" * 66)
    for k in STRENGTHS:
        arm = _pool(rows, k, seasons)
        gain, se = paired(arm, base)
        wins = sum(1 for s in seasons
                   if paired(rows[k][s], rows[0.0][s])[0] > 0)
        if k == 0.0:
            verdict = "baseline (today's board)"
        elif abs(gain) <= 2 * se:
            verdict = "inside the noise"
        else:
            verdict = "real, and better" if gain > 0 else "real, and worse"
        pm = "" if k == 0.0 else f" ± {se:.0f}"
        print(f"k = {k:<10.2f} {sum(arm) / len(arm):>11.0f} "
              f"{gain:>+12.0f}{pm:<5} {wins}/{len(seasons):<4}  {verdict}")

    print(f"\n{'SEASON':<10} " + "  ".join(f"k={k:<5.2f}" for k in STRENGTHS[1:]))
    print("-" * 66)
    for s in seasons:
        cells = []
        for k in STRENGTHS[1:]:
            gain, _se = paired(rows[k][s], rows[0.0][s])
            cells.append(f"{gain:>+7.0f}")
        print(f"{s:<10} " + "  ".join(cells))


def loso(rows, seasons):
    """Pick the strength on every season but one, then score it on that one.

    This is the only column that isn't fitted. Choosing k after seeing all five
    seasons would report the best of five tries as though it were a prediction.
    """
    print("\nLeave-one-season-out — k chosen without seeing the season it is scored on")
    print("-" * 66)
    print(f"{'HELD OUT':<10} {'k PICKED':>9} {'GAIN THERE':>12}")
    held = []
    for s in seasons:
        rest = [x for x in seasons if x != s]
        best_k, best_gain = 0.0, 0.0
        for k in STRENGTHS[1:]:
            gain, _se = paired(_pool(rows, k, rest), _pool(rows, 0.0, rest))
            if gain > best_gain:
                best_k, best_gain = k, gain
        got, _se = paired(rows[best_k][s], rows[0.0][s]) if best_k else (0.0, 0.0)
        held.append(got)
        print(f"{s:<10} {best_k:>9.2f} {got:>+12.0f}")
    print("-" * 66)
    mean = sum(held) / len(held)
    print(f"{'mean':<10} {'':>9} {mean:>+12.0f}   <- the honest number")
    return mean


def main() -> int:
    gone = backtest.missing_seasons()
    if gone:
        print(f"missing back-season data: {', '.join(gone)}")
        print("run 'python3 fetch_data.py history' first.")
        return 1

    argv = sys.argv[1:]
    measure = "composite"
    if "--measure" in argv:
        measure = argv[argv.index("--measure") + 1]
        if measure not in usage.MEASURES:
            print(f"unknown measure '{measure}' "
                  f"(have: {', '.join(usage.MEASURES)})")
            return 2
        usage.set_measure(measure)
        argv = [a for i, a in enumerate(argv)
                if a != "--measure" and argv[i - 1] != "--measure"]

    args = [a for a in argv if not a.startswith("--")]
    n = int(args[0]) if args else 200
    seasons = list(backtest.TEST_SEASONS)

    league = load_league()
    league = dict(league, keepers=[],
                  opponent_keepers={"known": [], "unknown_count": 0})

    print(f"Usage-adjusted board vs plain board — measure '{measure}', {n} paired "
          f"drafts\nper arm per season, {len(seasons)} seasons, scored on real "
          f"weekly results.")

    rows = run(seasons, n, league)
    report(rows, seasons)
    if "--loso" in sys.argv:
        loso(rows, seasons)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
