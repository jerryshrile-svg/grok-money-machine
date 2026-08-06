"""Does chasing opportunity beat chasing points on the waiver wire?

`season_value.py` measured the wire: a manager reacting to recent fantasy points
captures about +17 points a season, while a manager with hindsight captures
+275. Most of that gap is unreachable — the hindsight arm knows in week 3 what a
player will average through week 17 — but some of it is not.

The standing claim — made before any of this was built and never tested — is
that the gap exists because **points are the wrong signal**. A player's snaps,
targets and expected points move a week or two before his scoring does, so a
manager watching usage should get there first.

This tests exactly that. Same drafted rosters, same one-add-a-week budget, same
roster rules. The only thing that changes is what the manager looks at:

  POINTS        recent fantasy points, shrunk towards preseason expectation
  OPPORTUNITY   recent *expected* points — what the usage was worth, before
                the touchdown luck lands on top
  BLENDED       both, averaged
  PERFECT       hindsight, as the ceiling

Measured over 320 paired seasons, the answer is yes, and by a real margin:

    points        +17 ± 3     6% of the ceiling
    opportunity   +28 ± 4    10%
    blended       +30 ± 4    11%

    opportunity vs points:  +11 ± 3  -> real
    blended vs opportunity:  +2 ± 2  -> inside the noise

So watch expected points rather than the scoreboard, and don't bother blending
the two — the extra complexity buys nothing measurable.

Expected-points data starts in 2022, so this runs on four seasons rather than
five.

    python3 waiver_signal.py           # all four seasons
    python3 waiver_signal.py 2024 20   # one season, 20 drafts
"""

from __future__ import annotations

import csv
import os
import random
import sys
from collections import defaultdict

import backtest
import season_value
import sim
from engine import load_league
from last_season import PAIRS, _f, norm

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw")
SEASONS = (2022, 2023, 2024, 2025)


def weekly_expected(season: int, scoring: dict) -> dict[int, dict[str, float]]:
    """Expected fantasy points per player per week, in this league's scoring.

    This is what a player's usage was worth before the bounces landed: the
    receptions, yards and touchdowns an average player would have produced from
    the same opportunities.
    """
    path = os.path.join(RAW, f"expected_points_{season}.csv")
    out: dict[int, dict[str, float]] = defaultdict(dict)
    if not os.path.exists(path):
        return out
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            wk = int(_f(r, "week"))
            if wk > 18:
                continue
            if (r.get("position") or "").upper() not in ("QB", "RB", "WR", "TE"):
                continue
            key = norm(r["full_name"])
            pts = sum(scoring.get(s, 0.0) * _f(r, exp) for _a, exp, s in PAIRS)
            out[wk][key] = out[wk].get(key, 0.0) + pts
    return out


def blended(a: dict, b: dict) -> dict:
    """Average two weekly signals, falling back to whichever exists."""
    out: dict[int, dict[str, float]] = {}
    for wk in set(a) | set(b):
        wa, wb = a.get(wk, {}), b.get(wk, {})
        merged = {}
        for k in set(wa) | set(wb):
            if k in wa and k in wb:
                merged[k] = (wa[k] + wb[k]) / 2
            else:
                merged[k] = wa.get(k, wb.get(k, 0.0))
        out[wk] = merged
    return out


def run(seasons, n, league):
    weeks = list(backtest.WEEKS)
    rows: dict[str, list[float]] = defaultdict(list)

    for season in seasons:
        board = backtest.season_board(season, league)
        actuals = backtest.weekly_actuals(season, league["scoring"])
        expected = weekly_expected(season, league["scoring"])
        if not expected:
            print(f"  (no expected-points data for {season}, skipping)")
            continue

        by_name = {norm(p.name): p for p in board}
        future = season_value.rest_of_season(actuals, weeks)
        mixed = blended(actuals, expected)

        # The manager's view of the world differs; the scoring never does.
        signals = {
            "points": actuals,
            "opportunity": expected,
            "blended": mixed,
        }

        for i in range(n):
            rng = random.Random(season * 1000 + i)
            drafted: list = []
            mine = sim.run_draft(board, league, ["WAIT"] * league["rounds"], rng,
                                 keeper_count=0, drafted_out=drafted)
            taken = {norm(p.name) for p in drafted}
            free = [by_name[k] for k in by_name
                    if k not in taken and by_name[k].pos in ("QB", "RB", "WR", "TE")
                    and any(k in actuals.get(w, {}) for w in weeks)]

            rows["no waivers"].append(_play(mine, free, actuals, actuals, league,
                                            weeks, "draft_only"))
            for label, signal in signals.items():
                rows[label].append(_play(mine, free, actuals, signal, league,
                                         weeks, "waivers"))
            rows["perfect"].append(_play(mine, free, actuals, actuals, league,
                                         weeks, "perfect", future))
    return rows


def _play(roster, free, actuals, signal, league, weeks, mode, future=None):
    """Score a season where the manager reads `signal` but is paid on `actuals`."""
    original = season_value.trailing_form
    if mode == "waivers":
        # The manager forms his view from the signal, not from the scoreboard.
        season_value.trailing_form = lambda _a, w: original(signal, w)
    try:
        return season_value.simulate_season(
            list(roster), list(free), actuals, league, weeks, mode, future
        )
    finally:
        season_value.trailing_form = original


def main() -> int:
    league = load_league()
    league = dict(league, keepers=[], opponent_keepers={"known": [], "unknown_count": 0})

    args = sys.argv[1:]
    if args and args[0].isdigit() and int(args[0]) in SEASONS:
        seasons = [int(args[0])]
    else:
        seasons = list(SEASONS)
    n = int(args[1]) if len(args) > 1 else 25

    rows = run(seasons, n, league)
    if not rows:
        print("no data")
        return 1

    import math

    mean = lambda xs: sum(xs) / len(xs)  # noqa: E731

    def paired(a, b):
        """Difference and its standard error, using the pairing across arms."""
        diffs = [x - y for x, y in zip(a, b)]
        mu = mean(diffs)
        if len(diffs) < 2:
            return mu, 0.0
        var = sum((d - mu) ** 2 for d in diffs) / (len(diffs) - 1)
        return mu, math.sqrt(var / len(diffs))

    floor_arm = rows["no waivers"]
    span = mean(rows["perfect"]) - mean(floor_arm)

    print(f"\nWaiver signal comparison — {n} drafts per season, "
          f"{len(seasons)} seasons, real results.\n")
    print(f"{'MANAGER READS':<16} {'SEASON PTS':>11} {'vs NO WAIVERS':>16} "
          f"{'% OF CEILING':>13}")
    print("-" * 62)
    for label in ("no waivers", "points", "opportunity", "blended", "perfect"):
        if label not in rows:
            continue
        gain, se = paired(rows[label], floor_arm)
        pct = (gain / span * 100) if span else 0.0
        se_txt = f"± {se:.0f}" if label != "no waivers" else "     "
        print(f"{label:<16} {mean(rows[label]):>11.0f} "
              f"{gain:>+11.0f} {se_txt:<5} {pct:>11.0f}%")

    # The comparison that the whole thesis rests on.
    gain, se = paired(rows["opportunity"], rows["points"])
    verdict = "real" if abs(gain) > 2 * se else "INSIDE THE NOISE"
    print(f"\nopportunity vs points: {gain:+.0f} ± {se:.0f}  -> {verdict}")
    gain, se = paired(rows["blended"], rows["opportunity"])
    verdict = "real" if abs(gain) > 2 * se else "inside the noise"
    print(f"blended vs opportunity: {gain:+.0f} ± {se:.0f}  -> {verdict}")

    print("\nEvery arm plays the same drafted rosters and is scored on the same")
    print("real production. Only what the manager looks at when deciding changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
