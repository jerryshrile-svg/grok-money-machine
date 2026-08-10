"""Prior-season usage: snap share, target share, carry share.

The board these tools draft from knows nothing about usage. A player's value is
his expert-consensus positional rank mapped onto the historical points curve, so
two players ranked WR24 are worth exactly the same whether one played 90% of
snaps last year and the other 45%.

The standing argument for that is that the consensus has already priced usage in
— the panel knows who gets the targets. This module exists so that argument can
be tested instead of assumed. It builds, for any season, what each player's
usage was the year before, and how far that sits from what a player at his
current ranking normally has behind him.

The residual is the whole point. Raw usage would just re-rank the board by
target share, which is obviously wrong — the WR1 has both the most targets and
the highest rank. What might carry information is the *gap*: a player ranked
WR30 whose snaps and targets looked like a WR12's.

Nothing here reads the season being drafted. `for_season(2023)` reads 2022 only.

    python3 usage.py 2025        # who the 2024 usage flags, up and down
"""

from __future__ import annotations

import csv
import math
import os
import sys
from collections import defaultdict

from engine import HERE
from last_season import norm

RAW = os.path.join(HERE, "data", "raw")

MIN_GAMES = 6        # below this, a usage rate is a small-sample artefact
SKILL = ("QB", "RB", "WR", "TE")

# What "usage" means depends on the position. Target share is the right measure
# for a receiver and a poor one for a running back, who gets his volume on the
# ground. Snap share covers the part both have in common: whether he was on the
# field at all.
# A starting quarterback plays every snap and has no share to speak of, so no
# preset gives him one; there is no usage signal there that rank doesn't carry.
MEASURES = {
    # Everything, weighted by what drives fantasy points at each position.
    "composite": {
        "WR": {"snap": 0.4, "tgt": 0.6, "carry": 0.0},
        "TE": {"snap": 0.4, "tgt": 0.6, "carry": 0.0},
        "RB": {"snap": 0.4, "tgt": 0.3, "carry": 0.3},
        "QB": None,
    },
    # Target rate alone, which is the version most people mean.
    "target": {
        "WR": {"snap": 0.0, "tgt": 1.0, "carry": 0.0},
        "TE": {"snap": 0.0, "tgt": 1.0, "carry": 0.0},
        "RB": {"snap": 0.0, "tgt": 1.0, "carry": 0.0},
        "QB": None,
    },
    # Snap percentage alone — pure "was he on the field".
    "snap": {
        "WR": {"snap": 1.0, "tgt": 0.0, "carry": 0.0},
        "TE": {"snap": 1.0, "tgt": 0.0, "carry": 0.0},
        "RB": {"snap": 1.0, "tgt": 0.0, "carry": 0.0},
        "QB": None,
    },
}

WEIGHTS = MEASURES["composite"]


def set_measure(name: str) -> None:
    """Swap which definition of usage the residuals are built from."""
    global WEIGHTS
    WEIGHTS = MEASURES[name]


def _f(row, key):
    v = row.get(key)
    if v in (None, "", "NA"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def raw_usage(season: int) -> dict[str, dict]:
    """Per-game usage rates for one completed season.

    Target share comes straight from the weekly stats. Carry share has to be
    built, because the file has a player's carries but not his team's, so team
    rushing volume is summed per team-week first.
    """
    stats = os.path.join(RAW, f"stats_{season}.csv")
    if not os.path.exists(stats):
        return {}

    rows = []
    team_carries: dict[tuple[str, int], float] = defaultdict(float)
    with open(stats, newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("season_type") != "REG":
                continue
            if (r.get("position") or "").upper() not in SKILL:
                continue
            rows.append(r)
            team_carries[(r.get("team") or "", int(_f(r, "week")))] += _f(r, "carries")

    rec: dict[str, dict] = defaultdict(
        lambda: {"pos": "", "games": 0, "tgt": [], "carry": [], "snap": []}
    )
    for r in rows:
        key = norm(r.get("player_display_name") or "")
        if not key:
            continue
        d = rec[key]
        d["pos"] = (r.get("position") or "").upper()
        d["games"] += 1
        d["tgt"].append(_f(r, "target_share"))
        tc = team_carries[(r.get("team") or "", int(_f(r, "week")))]
        d["carry"].append(_f(r, "carries") / tc if tc else 0.0)

    snaps = os.path.join(RAW, f"snap_counts_{season}.csv")
    if os.path.exists(snaps):
        with open(snaps, newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("game_type") != "REG":
                    continue
                key = norm(r.get("player") or "")
                if key not in rec:
                    continue
                # nflverse stores this as a 0-1 fraction, not a percentage.
                rec[key]["snap"].append(_f(r, "offense_pct"))

    out = {}
    for key, d in rec.items():
        if d["games"] < MIN_GAMES:
            continue
        mean = lambda xs: (sum(xs) / len(xs)) if xs else 0.0  # noqa: E731
        out[key] = {
            "pos": d["pos"],
            "games": d["games"],
            "snap": mean(d["snap"]),
            "tgt": mean(d["tgt"]),
            "carry": mean(d["carry"]),
        }
    return out


def _z(values: list[float]) -> tuple[float, float]:
    """Mean and standard deviation, with a floor so a flat column can't blow up."""
    if not values:
        return 0.0, 1.0
    mu = sum(values) / len(values)
    if len(values) < 2:
        return mu, 1.0
    var = sum((v - mu) ** 2 for v in values) / (len(values) - 1)
    return mu, max(math.sqrt(var), 1e-6)


def usage_score(prior: dict[str, dict]) -> dict[str, float]:
    """Collapse the three rates into one number per player, scored within position.

    Comparing a running back's snap share against a receiver's would be
    meaningless, so every rate is standardised inside its own position first.
    """
    by_pos: dict[str, list[str]] = defaultdict(list)
    for key, d in prior.items():
        if WEIGHTS.get(d["pos"]):
            by_pos[d["pos"]].append(key)

    score: dict[str, float] = {}
    for pos, keys in by_pos.items():
        w = WEIGHTS[pos]
        stats = {}
        for field in ("snap", "tgt", "carry"):
            if w[field]:
                stats[field] = _z([prior[k][field] for k in keys])
        for k in keys:
            total = 0.0
            for field, (mu, sd) in stats.items():
                total += w[field] * ((prior[k][field] - mu) / sd)
            score[k] = total
    return score


POOL = 200      # overall ECR depth worth judging; below it, usage is noise
CLIP = 2.0      # standard deviations, so one odd player can't dominate a board


def residuals(board, prior: dict[str, dict]) -> dict[str, float]:
    """How far each player's prior usage sits from his current ranking's norm.

    Compares two orderings rather than fitting usage against rank: within a
    position, where a player sits on the usage list versus where he sits on the
    consensus list. Positive means he was used like someone drafted earlier.

    Fitting a curve was the first attempt and it failed in a way worth recording.
    Usage saturates — nobody commands 50% of the targets — so a line through log
    rank predicts impossible usage at the top of the board and charges every
    elite player for missing it. Ja'Marr Chase came out at -2.64 on 92% of snaps
    and a 27% target share, which is not a finding about Chase, it is the curve
    being wrong. Rank against rank has no such failure: it only asks who was
    ahead of whom.

    A player with no prior season gets zero, not a guess. Rookies are the single
    biggest group here and inventing a usage history for them would be worse
    than admitting there isn't one.
    """
    score = usage_score(prior)
    by_pos: dict[str, list] = defaultdict(list)
    for p in sorted(board, key=lambda p: p.adp)[:POOL]:
        if WEIGHTS.get(p.pos) and norm(p.name) in score:
            by_pos[p.pos].append(p)

    out: dict[str, float] = {}
    for pos, players in by_pos.items():
        if len(players) < 8:
            continue
        by_ecr = sorted(players, key=lambda p: p.adp)
        by_use = sorted(players, key=lambda p: -score[norm(p.name)])
        use_rank = {norm(p.name): i for i, p in enumerate(by_use)}

        gaps = [i - use_rank[norm(p.name)] for i, p in enumerate(by_ecr)]
        _mu, sd = _z([float(g) for g in gaps])
        for p, g in zip(by_ecr, gaps):
            out[norm(p.name)] = max(-CLIP, min(CLIP, g / sd))
    return out


def for_season(season: int, board) -> dict[str, float]:
    """Usage residuals for a draft happening before `season`, using season-1 only."""
    return residuals(board, raw_usage(season - 1))


def main() -> int:
    import backtest
    from engine import load_league

    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    league = load_league()
    board = backtest.season_board(season, league)
    prior = raw_usage(season - 1)
    resid = for_season(season, board)
    if not resid:
        print(f"no usage data for {season - 1} — run 'python3 fetch_data.py history'")
        return 1

    ranked = sorted(board, key=lambda p: p.adp)
    rows = [(resid[norm(p.name)], p) for p in ranked[:150] if norm(p.name) in resid]
    rows.sort(key=lambda t: -t[0])

    print(f"\n{season} board, judged on {season - 1} usage. Residual is in standard")
    print("deviations from what a player at that ranking normally has behind him.\n")
    for title, chunk in (("Used more than his rank suggests", rows[:12]),
                         ("Used less than his rank suggests", rows[-12:][::-1])):
        print(f"  {title}")
        print(f"    {'PLAYER':<24} {'POS':<5} {'ECR':>6} {'RESID':>7} "
              f"{'SNAP':>6} {'TGT%':>6}")
        for r, p in chunk:
            d = prior.get(norm(p.name), {})
            print(f"    {p.name:<24} {p.pos:<5} {p.adp:>6.1f} {r:>+7.2f} "
                  f"{d.get('snap', 0) * 100:>5.0f}% {d.get('tgt', 0) * 100:>5.1f}%")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
