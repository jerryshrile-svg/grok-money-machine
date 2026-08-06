"""How much does the draft actually matter?

Every measurement in this toolkit so far has been about draft day. That is worth
checking, because the draft is only one of two levers. In an 8-team league you
roster 112 players out of a pool of 500-plus, which means genuinely startable
players sit unowned all season, and you get seventeen chances to go get them.

If competent waiver management is worth far more than a better draft, then the
right thing to do before August 15 is stop polishing the board and start building
the in-season tool.

The measurement replays real seasons and scores the same drafted roster twice:

  DRAFT ONLY    the fourteen players you drafted, nothing else, lineups set each
                week from what you knew at the time
  WITH WAIVERS  the same draft, plus one add per week, chosen from players nobody
                rostered using only production through the previous week

Both arms use the same manager: each week you start whoever your best available
estimate likes, where the estimate is trailing form once a player has games, and
preseason projection before that. The only difference between the arms is access
to the waiver wire, which isolates the lever.

A third arm marks the ceiling:

  PERFECT       one add per week with hindsight — the most the wire could ever
                have been worth, which nobody achieves

    python3 season_value.py            # all seasons
    python3 season_value.py 2024 20    # one season, 20 drafts
"""

from __future__ import annotations

import random
import sys
from collections import defaultdict

import backtest
import sim
from engine import load_league
from last_season import norm

TRAILING = 4       # games of recent form the manager reacts to
ADDS_PER_WEEK = 1  # rolling waiver priority means you are not churning five a week
SHRINK = 3.0       # games of preseason expectation a hot streak must outweigh
MIN_FUTURE_GAMES = 3  # ceiling arm ignores players with almost no season left

# A manager keeps a legal lineup. Without these floors the model happily drops
# its only quarterback for a hot receiver and scores nothing at the position for
# the rest of the year.
MIN_KEEP = {"QB": 1, "RB": 3, "WR": 3, "TE": 1}
MAX_HOLD = {"QB": 2, "RB": 6, "WR": 6, "TE": 2}


def trailing_form(actuals, weeks):
    """Recent scoring per week, as (total, games) so it can be shrunk.

    Uses only completed weeks, so a week-9 decision never sees week 9 or later.
    """
    form: dict[int, dict[str, tuple[float, int]]] = {}
    history: dict[str, list[float]] = defaultdict(list)
    for wk in weeks:
        form[wk] = {
            name: (sum(vals[-TRAILING:]), len(vals[-TRAILING:]))
            for name, vals in history.items()
            if vals
        }
        for name, pts in actuals.get(wk, {}).items():
            history[name].append(pts)
    return form


def _estimate(player, key, wk, form, preseason_pg):
    """What a manager thinks a player is worth going into a week.

    Deliberately stable: trailing form is computed over games actually played, so
    a bye week does not make a star look worthless. Ranking by a single week's
    score would have you dropping your best player the week he rests.
    """
    base = preseason_pg.get(key, player.points / 17.0)
    total, games = form.get(wk, {}).get(key, (0.0, 0))
    # Shrink towards preseason expectation. Without this, one 25-point game makes
    # a replacement-level player look like a star and you drop a real one for him.
    return (total + SHRINK * base) / (games + SHRINK)


def rest_of_season(actuals, weeks):
    """Points per game a player will average from each week onward.

    Only used by the hindsight ceiling arm, to mark the upper bound.
    """
    out: dict[int, dict[str, float]] = {}
    for wk in weeks:
        tally: dict[str, list[float]] = defaultdict(list)
        for later in weeks:
            if later < wk:
                continue
            for name, pts in actuals.get(later, {}).items():
                tally[name].append(pts)
        out[wk] = {
            n: sum(v) / len(v) for n, v in tally.items()
            if len(v) >= MIN_FUTURE_GAMES
        }
    return out


def simulate_season(roster, free_agents, actuals, league, weeks, mode, future=None):
    """Play one season with a given roster and waiver policy."""
    slots = league["roster"]
    flex_ok = set(league.get("flex_eligible", ["RB", "WR", "TE"]))
    cap = sum(slots.get(k, 0) for k in ("QB", "RB", "WR", "TE", "FLEX"))
    cap += slots.get("BN", 5)

    form = trailing_form(actuals, weeks)
    keys = {id(p): norm(p.name) for p in roster + free_agents}
    preseason_pg = {keys[id(p)]: p.points / 17.0 for p in roster + free_agents}

    squad = [p for p in roster if p.pos in ("QB", "RB", "WR", "TE")]
    available = list(free_agents)
    total = 0.0

    for wk in weeks:
        def value(p, _wk=wk):
            if mode == "perfect":
                return future[_wk].get(keys[id(p)], 0.0)
            return _estimate(p, keys[id(p)], _wk, form, preseason_pg)

        if mode != "draft_only" and wk > 1 and available:
            for _ in range(ADDS_PER_WEEK):
                counts: dict[str, int] = defaultdict(int)
                for p in squad:
                    counts[p.pos] += 1

                adds = [p for p in available
                        if counts[p.pos] < MAX_HOLD.get(p.pos, 6)]
                drops = [p for p in squad
                         if counts[p.pos] > MIN_KEEP.get(p.pos, 1)]
                if not adds or (len(squad) >= cap and not drops):
                    break

                best = max(adds, key=value)
                worst = min(drops, key=value) if len(squad) >= cap else None
                if worst is not None and value(best) <= value(worst):
                    break
                squad.append(best)
                available.remove(best)
                if worst is not None:
                    squad.remove(worst)
                    available.append(worst)

        week_pts = actuals.get(wk, {})
        playing = [p for p in squad if keys[id(p)] in week_pts]
        playing.sort(key=lambda p: -value(p))

        used, by_pos = set(), defaultdict(list)
        for p in playing:
            by_pos[p.pos].append(p)
        for pos in ("QB", "RB", "WR", "TE"):
            for p in by_pos[pos][: slots.get(pos, 0)]:
                total += week_pts[keys[id(p)]]
                used.add(id(p))
        flex = [p for p in playing if p.pos in flex_ok and id(p) not in used]
        for p in flex[: slots.get("FLEX", 0)]:
            total += week_pts[keys[id(p)]]
    return total


def run(seasons, n, league):
    weeks = list(backtest.WEEKS)
    rows = defaultdict(list)

    for season in seasons:
        board = backtest.season_board(season, league)
        actuals = backtest.weekly_actuals(season, league["scoring"])
        by_name = {norm(p.name): p for p in board}
        future = rest_of_season(actuals, weeks)
        rng = random.Random(31)

        for _ in range(n):
            drafted: list = []
            mine = sim.run_draft(
                board, league, ["WAIT"] * league["rounds"], rng,
                keeper_count=0, drafted_out=drafted,
            )
            taken = {norm(p.name) for p in drafted}
            # Anyone unrostered who actually produced that season.
            free = [
                by_name[k] for k in by_name
                if k not in taken
                and by_name[k].pos in ("QB", "RB", "WR", "TE")
                and any(k in actuals.get(w, {}) for w in weeks)
            ]
            for mode in ("draft_only", "waivers", "perfect"):
                rows[(season, mode)].append(
                    simulate_season(mine, free, actuals, league, weeks, mode, future)
                )
    return rows


def main() -> int:
    league = load_league()
    league = dict(league, keepers=[], opponent_keepers={"known": [], "unknown_count": 0})

    args = sys.argv[1:]
    seasons = [int(args[0])] if args and args[0].isdigit() else list(backtest.TEST_SEASONS)
    n = int(args[1]) if len(args) > 1 else 12

    rows = run(seasons, n, league)
    mean = lambda xs: sum(xs) / len(xs)  # noqa: E731

    print(f"Value of the waiver wire — {n} drafts per season, real results.")
    print("Same drafted roster, played with and without in-season adds.\n")
    print(f"{'SEASON':<8} {'DRAFT ONLY':>11} {'WITH WAIVERS':>13} {'GAIN':>7} "
          f"{'PERFECT':>9} {'CEILING':>8}")
    print("-" * 60)
    gains, ceilings = [], []
    for season in seasons:
        d = mean(rows[(season, "draft_only")])
        w = mean(rows[(season, "waivers")])
        p = mean(rows[(season, "perfect")])
        gains.append(w - d)
        ceilings.append(p - d)
        print(f"{season:<8} {d:>11.0f} {w:>13.0f} {w - d:>+7.0f} {p:>9.0f} {p - d:>+8.0f}")

    print("-" * 60)
    print(f"{'mean':<8} {'':>11} {'':>13} {mean(gains):>+7.0f} {'':>9} "
          f"{mean(ceilings):>+8.0f}")
    print("\nFor comparison, the draft-strategy edge measured by backtest.py is")
    print("roughly 25-45 points a season, winning 4 of 5 — the gap between the")
    print("wait-cost rule and simply drafting the consensus list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
