"""What actually happened in 2025, and where it disagrees with the 2026 consensus.

This is the one place the toolkit forms an opinion the consensus hasn't handed it.

The core idea is **points over expected**. For every play in 2025, ffopportunity
models what an average player would have gained given the situation — down,
distance, air yards, field position — and turns that into expected receptions,
yards, and touchdowns. Compare that to what a player actually produced:

  POE strongly positive -> 2025 output ran ahead of the opportunity behind it.
      Usually touchdown luck, and touchdown rate regresses hard year to year.
      If the consensus is still paying for that season, you're buying the noise.

  POE strongly negative -> real usage, unlucky finish. If the consensus faded
      them for it, that's the cheapest edge on the board.

Usage (snap share, target share) is the sticky part and is shown alongside, because
POE only matters when the opportunity is real.

    python3 last_season.py              # 2025 context for the top of the board
    python3 last_season.py regression   # ran hottest vs opportunity — fade list
    python3 last_season.py values       # ran coldest vs opportunity — buy list
    python3 last_season.py player <name>
"""

from __future__ import annotations

import csv
import os
import re
import sys
from collections import defaultdict

from engine import HERE, build_board, load_league, load_players

RAW = os.path.join(HERE, "data", "raw")
LAST_WEEK = 18  # regular season only; the files carry playoff weeks too

SUFFIXES = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def norm(name: str) -> str:
    n = name.lower().replace(".", "").replace("'", "").replace("-", " ")
    return " ".join(SUFFIXES.sub("", n).split())


def _f(row: dict, key: str) -> float:
    v = row.get(key)
    if v in (None, "", "NA"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


# ffopportunity column pairs -> scoring key. Fumbles are excluded from both sides:
# there is no expected-fumbles model, so including them would bias the comparison.
PAIRS = (
    ("pass_yards_gained", "pass_yards_gained_exp", "pass_yd"),
    ("pass_touchdown", "pass_touchdown_exp", "pass_td"),
    ("pass_interception", "pass_interception_exp", "pass_int"),
    ("rush_yards_gained", "rush_yards_gained_exp", "rush_yd"),
    ("rush_touchdown", "rush_touchdown_exp", "rush_td"),
    ("receptions", "receptions_exp", "rec"),
    ("rec_yards_gained", "rec_yards_gained_exp", "rec_yd"),
    ("rec_touchdown", "rec_touchdown_exp", "rec_td"),
)


class Season:
    def __init__(self, scoring: dict):
        self.scoring = scoring
        self.rec: dict[str, dict] = defaultdict(
            lambda: {
                "name": "", "pos": "", "team": "", "games": 0,
                "pts": 0.0, "exp": 0.0, "td": 0.0, "td_exp": 0.0,
                "targets": 0.0, "carries": 0.0, "rec": 0.0,
                "tgt_share": [], "snap_pct": [],
            }
        )
        self._load_expected()
        self._load_stats()
        self._load_snaps()

    def _load_expected(self):
        path = os.path.join(RAW, "expected_points_2025.csv")
        for r in csv.DictReader(open(path, newline="")):
            if int(_f(r, "week")) > LAST_WEEK:
                continue
            pos = (r.get("position") or "").upper()
            if pos not in ("QB", "RB", "WR", "TE"):
                continue
            k = norm(r["full_name"])
            d = self.rec[k]
            d["name"] = d["name"] or r["full_name"]
            d["pos"] = pos
            d["team"] = r.get("posteam") or d["team"]
            d["games"] += 1
            for act, exp, skey in PAIRS:
                mult = self.scoring.get(skey, 0.0)
                d["pts"] += mult * _f(r, act)
                d["exp"] += mult * _f(r, exp)
            d["td"] += _f(r, "total_touchdown")
            d["td_exp"] += _f(r, "total_touchdown_exp")

    def _load_stats(self):
        path = os.path.join(RAW, "stats_2025.csv")
        for r in csv.DictReader(open(path, newline="")):
            if r.get("season_type") != "REG":
                continue
            k = norm(r.get("player_display_name") or "")
            if k not in self.rec:
                continue
            d = self.rec[k]
            d["targets"] += _f(r, "targets")
            d["carries"] += _f(r, "carries")
            d["rec"] += _f(r, "receptions")
            ts = _f(r, "target_share")
            if ts:
                d["tgt_share"].append(ts)

    def _load_snaps(self):
        path = os.path.join(RAW, "snap_counts_2025.csv")
        for r in csv.DictReader(open(path, newline="")):
            if r.get("game_type") != "REG":
                continue
            k = norm(r.get("player") or "")
            if k not in self.rec:
                continue
            pct = _f(r, "offense_pct")
            if pct:
                self.rec[k]["snap_pct"].append(pct)

    def get(self, name: str) -> dict | None:
        d = self.rec.get(norm(name))
        if not d or not d["games"]:
            return None
        g = d["games"]
        out = dict(d)
        out["ppg"] = d["pts"] / g
        out["ppg_exp"] = d["exp"] / g
        out["poe"] = d["pts"] - d["exp"]
        out["poe_pg"] = out["poe"] / g
        out["td_oe"] = d["td"] - d["td_exp"]
        out["tgt_share"] = (
            sum(d["tgt_share"]) / len(d["tgt_share"]) if d["tgt_share"] else 0.0
        )
        out["snap_pct"] = (
            sum(d["snap_pct"]) / len(d["snap_pct"]) if d["snap_pct"] else 0.0
        )
        return out

    def finishes(self) -> dict[str, int]:
        """2025 positional finish by total points."""
        by_pos = defaultdict(list)
        for k, d in self.rec.items():
            if d["games"]:
                by_pos[d["pos"]].append((d["pts"], k))
        out = {}
        for pos, items in by_pos.items():
            items.sort(reverse=True)
            for rank, (_, k) in enumerate(items, 1):
                out[k] = rank
        return out


def _rows(season: Season, board, limit: int):
    fin = season.finishes()
    out = []
    for p in board:
        if p.pos in ("K", "DST", "DEF"):
            continue
        d = season.get(p.name)
        out.append((p, d, fin.get(norm(p.name))))
        if len(out) >= limit:
            break
    return out


def show_board(season: Season, board, limit: int = 45):
    print(f"{'PLAYER':<23} {'POS':<5} {'ECR':>5} {'25FIN':>6} {'PPG':>6} "
          f"{'xPPG':>6} {'POE/G':>7} {'SNAP':>6} {'TGT%':>6}")
    print("-" * 78)
    for p, d, fin in _rows(season, board, limit):
        if d is None:
            print(f"{p.name:<23} {p.pos + str(p.pos_rank):<5} {p.adp:>5.1f} "
                  f"{'--':>6} {'no 2025 data (rookie / missed year)':>44}")
            continue
        flag = ""
        if d["poe_pg"] > 1.5:
            flag = "  hot"
        elif d["poe_pg"] < -1.5:
            flag = "  cold"
        print(
            f"{p.name:<23} {p.pos + str(p.pos_rank):<5} {p.adp:>5.1f} "
            f"{(p.pos + str(fin)) if fin else '--':>6} "
            f"{d['ppg']:>6.1f} {d['ppg_exp']:>6.1f} {d['poe_pg']:>+7.1f} "
            f"{d['snap_pct'] * 100:>5.0f}% {d['tgt_share'] * 100:>5.1f}%{flag}"
        )
    print("\nPPG/xPPG are per game in your 0.5 PPR scoring. POE/G is the gap: "
          "positive means\n2025 output ran ahead of the opportunity behind it.")


def _scan(season: Season, board, sign: int, limit: int, pool: int = 140):
    cands = []
    for p, d, fin in _rows(season, board, pool):
        if d is None or d["games"] < 8:
            continue
        cands.append((sign * d["poe_pg"], p, d, fin))
    cands.sort(reverse=True)
    return cands[:limit]


def regression(season: Season, board, limit: int = 15):
    print("Ran hottest vs opportunity in 2025 — touchdown rate regresses.")
    print("If the consensus is still paying up, you're buying last year's luck.\n")
    _print_scan(_scan(season, board, +1, limit))


def values(season: Season, board, limit: int = 15):
    print("Ran coldest vs opportunity in 2025 — the usage was real, the finish wasn't.")
    print("Check the snap and target columns: high usage plus a bad finish is the buy.\n")
    _print_scan(_scan(season, board, -1, limit))


def _print_scan(rows):
    print(f"{'PLAYER':<23} {'POS':<5} {'ECR':>5} {'POE/G':>7} {'TD':>5} "
          f"{'xTD':>6} {'SNAP':>6} {'TGT%':>6} {'G':>3}")
    print("-" * 72)
    for _, p, d, _fin in rows:
        print(
            f"{p.name:<23} {p.pos + str(p.pos_rank):<5} {p.adp:>5.1f} "
            f"{d['poe_pg']:>+7.1f} {d['td']:>5.0f} {d['td_exp']:>6.1f} "
            f"{d['snap_pct'] * 100:>5.0f}% {d['tgt_share'] * 100:>5.1f}% {d['games']:>3}"
        )


def player_card(season: Season, board, query: str):
    q = norm(query)
    match = [p for p in board if q in norm(p.name)]
    if not match:
        print(f"no player matching '{query}'")
        return
    p = min(match, key=lambda x: x.adp)
    d = season.get(p.name)
    fin = season.finishes().get(norm(p.name))

    print(f"\n{p.name}  ({p.pos}, {p.team})")
    print(f"  2026 consensus   #{p.adp:.1f} overall, {p.pos}{p.pos_rank}, tier {p.tier}")
    print(f"  your board       VORP {p.vorp:+.1f}, projected {p.points:.0f} pts")
    if p.ceiling or p.floor:
        print(f"  panel range      {p.floor:.0f} - {p.ceiling:.0f} pts "
              f"(experts' worst to best case)")
    if p.bye:
        print(f"  bye              week {p.bye}")

    if d is None:
        print("\n  no 2025 data — rookie, or missed the season.")
        print("  The consensus rank is the only signal here; treat it as such.")
        return

    print(f"\n  2025 ({d['games']} games, finished {p.pos}{fin})")
    print(f"    actual            {d['pts']:.0f} pts   ({d['ppg']:.1f}/g)")
    print(f"    expected          {d['exp']:.0f} pts   ({d['ppg_exp']:.1f}/g)")
    print(f"    over expected     {d['poe']:+.0f} pts   ({d['poe_pg']:+.1f}/g)")
    print(f"    touchdowns        {d['td']:.0f} actual vs {d['td_exp']:.1f} expected "
          f"({d['td_oe']:+.1f})")
    print(f"    usage             {d['snap_pct'] * 100:.0f}% snaps, "
          f"{d['tgt_share'] * 100:.1f}% target share, "
          f"{d['targets']:.0f} targets, {d['carries']:.0f} carries")

    verdict = []
    if d["poe_pg"] > 1.5:
        verdict.append("Outran its opportunity — expect touchdown regression.")
    elif d["poe_pg"] < -1.5:
        verdict.append("Underran its opportunity — positive regression candidate.")
    else:
        verdict.append("Production matched opportunity; last year was honest.")
    if d["snap_pct"] >= 0.70:
        verdict.append("Workload was locked in.")
    elif d["snap_pct"] and d["snap_pct"] < 0.50:
        verdict.append("Part-time snap share — the role has to grow for the rank to hold.")
    print("\n  " + " ".join(verdict))


def main() -> int:
    league = load_league()
    board = build_board(league, load_players())
    season = Season(league["scoring"])

    args = sys.argv[1:]
    mode = args[0] if args else "board"
    if mode == "regression":
        regression(season, board)
    elif mode == "values":
        values(season, board)
    elif mode == "player":
        if len(args) < 2:
            print("usage: python3 last_season.py player <name>")
            return 2
        player_card(season, board, " ".join(args[1:]))
    else:
        show_board(season, board)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
