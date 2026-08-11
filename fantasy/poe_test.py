"""Does acting on the regression signal actually beat the consensus?

`validate.py` established that points over expected barely repeats — about 4%
year to year — and that hot players give back 91% of the gap while cold ones
recover 31%. Every one of those numbers is about the *player*. None of them is
about the *market*.

That distinction was never checked, and it is the one that matters. If the
expert panel already discounts a receiver who scored nine touchdowns on six
expected, then adjusting his projection again double-counts and makes the board
worse — exactly what happened when prior-year usage was added in section 15. The
regression signal only pays if the consensus has not already priced it.

So: rebuild each replayed season's board with the validated adjustment applied
to every player, and see whether the resulting drafts score more real points.

    projection += -0.91 * poe   if the player ran hot last year
    projection += +0.31 * -poe  if he ran cold

Expected-points data starts in 2022, so a board for season S needs S-1 and this
runs on 2023, 2024 and 2025 — three seasons rather than five. The strength knob
is swept for the same reason as everywhere else: one hand-picked value proves
nothing.

    python3 poe_test.py            # 200 paired drafts per arm per season
    python3 poe_test.py 400
"""

from __future__ import annotations

import math
import random
import sys
from collections import defaultdict

import backtest
import sim
import waiver_signal
from engine import Player, build_board, load_league
from last_season import norm

SEASONS = (2023, 2024, 2025)

# From validate.py, measured over four seasons.
GIVEBACK = 0.91
RECOVERY = 0.31

# 0 is the board as it stands. 1.0 applies the measured adjustment in full.
STRENGTHS = (0.0, 0.5, 1.0)


def prior_poe(season: int, scoring: dict) -> dict[str, float]:
    """Season-total points over expected for the year before `season`.

    Nothing here reads the season being drafted.
    """
    prev = season - 1
    actuals = backtest.weekly_actuals(prev, scoring)
    expected = waiver_signal.weekly_expected(prev, scoring)
    if not expected:
        return {}
    got: dict[str, float] = defaultdict(float)
    exp: dict[str, float] = defaultdict(float)
    for wk, week in actuals.items():
        for name, pts in week.items():
            got[name] += pts
    for wk, week in expected.items():
        for name, pts in week.items():
            exp[name] += pts
    return {n: got[n] - exp[n] for n in got if n in exp}


def adjusted_board(base, league, poe: dict[str, float], weight: float):
    """The board with each player nudged toward what his opportunity earned."""
    if weight == 0.0:
        return base
    players = []
    for p in base:
        gap = poe.get(norm(p.name))
        delta = 0.0
        if gap is not None:
            delta = -GIVEBACK * gap if gap > 0 else -RECOVERY * gap
        q = Player(name=p.name, pos=p.pos, team=p.team, adp=p.adp,
                   points=p.points + weight * delta)
        q.ecr_best, q.ecr_worst = p.ecr_best, p.ecr_worst
        q.ceiling, q.floor = p.ceiling, p.floor
        players.append(q)
    return build_board(league, players)


def paired(a, b):
    diffs = [x - y for x, y in zip(a, b)]
    mu = sum(diffs) / len(diffs)
    if len(diffs) < 2:
        return mu, 0.0
    var = sum((d - mu) ** 2 for d in diffs) / (len(diffs) - 1)
    return mu, math.sqrt(var / len(diffs))


def run(seasons, n, league):
    rows: dict[float, dict[int, list[float]]] = {w: defaultdict(list) for w in STRENGTHS}
    covered = []
    for season in seasons:
        poe = prior_poe(season, league["scoring"])
        if not poe:
            print(f"  (no expected-points data for {season - 1}, skipping {season})")
            continue
        covered.append(season)
        base = backtest.season_board(season, league)
        actuals = backtest.weekly_actuals(season, league["scoring"])
        boards = {w: adjusted_board(base, league, poe, w) for w in STRENGTHS}
        hit = sum(1 for p in base[:120] if norm(p.name) in poe)
        print(f"  {season}: {hit}/120 of the top board has a prior-year POE reading")
        for i in range(n):
            for w in STRENGTHS:
                rng = random.Random(season * 100_003 + i)
                roster = sim.run_draft(boards[w], league, ["WAIT"] * league["rounds"],
                                       rng, keeper_count=0)
                rows[w][season].append(
                    backtest.score_roster(roster, actuals, league))
    return rows, covered


def main() -> int:
    gone = backtest.missing_seasons()
    if gone:
        print(f"missing back-season data: {', '.join(gone)}")
        print("run 'python3 fetch_data.py history' first.")
        return 1

    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 200
    league = load_league()
    league = dict(league, keepers=[],
                  opponent_keepers={"known": [], "unknown_count": 0})

    print(f"Regression signal vs the consensus — {n} paired drafts per arm "
          f"per season.\nScored on real weekly results.\n")
    rows, covered = run(SEASONS, n, league)
    if not covered:
        print("\nno usable seasons — run 'python3 fetch_data.py history'")
        return 1

    def pool(w):
        out = []
        for s in covered:
            out.extend(rows[w][s])
        return out

    base = pool(0.0)
    print(f"\n{'ADJUSTMENT':<14}{'SEASON PTS':>11}{'vs UNADJUSTED':>17}   VERDICT")
    print("-" * 62)
    for w in STRENGTHS:
        arm = pool(w)
        gain, se = paired(arm, base)
        if w == 0.0:
            verdict = "baseline (today's board)"
            pm = ""
        else:
            pm = f" ± {se:.0f}"
            verdict = ("real, better" if gain > 2 * se else
                       "real, worse" if gain < -2 * se else "inside the noise")
        print(f"{w:<14.2f}{sum(arm) / len(arm):>11.0f}{gain:>+12.0f}{pm:<5}   {verdict}")

    print(f"\n{'SEASON':<10}" + "".join(f"{w:>12.2f}" for w in STRENGTHS[1:]))
    print("-" * 62)
    for s in covered:
        cells = [f"{paired(rows[w][s], rows[0.0][s])[0]:>+12.0f}" for w in STRENGTHS[1:]]
        print(f"{s:<10}" + "".join(cells))

    print("\nIf this is positive the panel has not priced touchdown regression and")
    print("the fade and buy lists are worth acting on. If it is not, they are")
    print("commentary — read them, don't move players on them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
