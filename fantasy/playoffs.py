"""Weeks 15-17: who your players face when the title is decided.

Six of eight teams make your playoffs, which changes what the draft is for.
Qualifying is nearly automatic — you only have to avoid finishing last or second
to last. So the regular season's real job is **seeding**, because a top-two bye
means winning two games instead of three, and that roughly doubles your title
odds. Everything after that is decided in three weeks.

That makes the weeks 15-17 schedule a genuine draft tiebreaker rather than
trivia. Between two players you rate closely, the one facing three soft defenses
in the only weeks that decide anything is the better pick.

How the difficulty is measured: total fantasy points each defense allowed to each
position in 2025, in your scoring, per game, expressed against the league
average. Positive means that defense gave up more than average — good for you.

    python3 playoffs.py            # schedule difficulty by team and position
    python3 playoffs.py board      # your draft board, sorted by playoff schedule

One honest caveat: last season's defensive performance is a moderate predictor of
this season's. Free agency, the draft and coaching turnover all move it. Treat
this as a tiebreaker between close players, never as a reason to reach.
"""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

from engine import HERE, build_board, load_league, load_players

RAW = os.path.join(HERE, "data", "raw")

# Confirmed against the 2026 calendar: NFL week 17 ends Monday 2027-01-04, which
# is when this league's playoffs end. Read from config so a format change can't
# leave this file silently analysing the wrong three weeks.
DEFAULT_PLAYOFF_WEEKS = (15, 16, 17)
SKILL = ("QB", "RB", "WR", "TE")

STAT_MAP = {
    "passing_yards": "pass_yd", "passing_tds": "pass_td",
    "passing_interceptions": "pass_int", "rushing_yards": "rush_yd",
    "rushing_tds": "rush_td", "receptions": "rec",
    "receiving_yards": "rec_yd", "receiving_tds": "rec_td",
}

# nflverse abbreviations that differ from the consensus feed's.
ALIAS = {"JAC": "JAX", "LA": "LAR", "WSH": "WAS", "SD": "LAC", "OAK": "LV", "STL": "LAR"}


def _f(row, key):
    v = row.get(key)
    if v in (None, "", "NA"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def team(abbr: str) -> str:
    a = (abbr or "").upper()
    return ALIAS.get(a, a)


def points_allowed(scoring: dict) -> dict[str, dict[str, float]]:
    """2025 fantasy points allowed per game, by defense and position."""
    path = os.path.join(RAW, "stats_2025.csv")
    totals: dict[tuple[str, str], float] = defaultdict(float)
    games: dict[tuple[str, str], set] = defaultdict(set)

    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("season_type") != "REG":
                continue
            pos = (row.get("position") or "").upper()
            if pos not in SKILL:
                continue
            defense = team(row.get("opponent_team"))
            if not defense:
                continue
            pts = sum(scoring.get(k, 0.0) * _f(row, c) for c, k in STAT_MAP.items())
            totals[(defense, pos)] += pts
            games[(defense, pos)].add(row.get("game_id"))

    out: dict[str, dict[str, float]] = defaultdict(dict)
    for (defense, pos), pts in totals.items():
        n = len(games[(defense, pos)]) or 1
        out[defense][pos] = pts / n
    return out


def league_average(allowed) -> dict[str, float]:
    avg = {}
    for pos in SKILL:
        vals = [d[pos] for d in allowed.values() if pos in d]
        avg[pos] = sum(vals) / len(vals) if vals else 0.0
    return avg


def playoff_weeks(league: dict) -> tuple[int, ...]:
    return tuple(league.get("playoff_weeks") or DEFAULT_PLAYOFF_WEEKS)


def playoff_opponents(league: dict | None = None) -> dict[str, list[str]]:
    """Each team's playoff-week opponents from the 2026 schedule."""
    weeks = playoff_weeks(league or {})
    path = os.path.join(RAW, "schedule_2026.csv")
    if not os.path.exists(path):
        return {}
    out: dict[str, list[str]] = defaultdict(list)
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") != "2026" or int(_f(r, "week")) not in weeks:
                continue
            home, away = team(r.get("home_team")), team(r.get("away_team"))
            out[home].append(away)
            out[away].append(home)
    return out


def difficulty(allowed, avg, opponents) -> dict[str, dict[str, float]]:
    """Points above league average a team's playoff opponents concede, by position."""
    out: dict[str, dict[str, float]] = {}
    for tm, opps in opponents.items():
        scores = {}
        for pos in SKILL:
            vals = [allowed[o][pos] for o in opps if o in allowed and pos in allowed[o]]
            scores[pos] = (sum(vals) / len(vals) - avg[pos]) if vals else 0.0
        out[tm] = scores
    return out


def show_teams(diff, opponents):
    print("Playoff-week schedule, points above league average conceded by the")
    print("defenses your players face. Positive is easier.\n")
    print(f"{'TEAM':<6} {'OPPONENTS':<16} {'QB':>7} {'RB':>7} {'WR':>7} {'TE':>7}")
    print("-" * 56)
    for tm in sorted(diff, key=lambda t: -sum(diff[t].values())):
        opps = " ".join(opponents[tm][:3])
        row = "".join(f"{diff[tm][p]:>+7.1f}" for p in SKILL)
        print(f"{tm:<6} {opps:<16}{row}")


def show_board(board, diff, league, show=12):
    """Only players who actually get drafted — a soft schedule for the 300th
    ranked receiver is not a tiebreaker, it is noise."""
    pool_size = league["teams"] * league["rounds"]
    rows = []
    for p in board[:pool_size]:
        if p.pos in ("K", "DST", "DEF"):
            continue
        d = diff.get(team(p.team), {}).get(p.pos)
        if d is not None:
            rows.append((d, p))
    rows.sort(key=lambda r: -r[0])

    def block(title, items):
        print(f"\n{title}")
        print(f"{'PLAYER':<24} {'POS':<5} {'ECR':>5} {'VORP':>7} {'TEAM':>5} {'WK15-17':>9}")
        print("-" * 60)
        for d, p in items:
            print(f"{p.name:<24} {p.pos + str(p.pos_rank):<5} {p.adp:>5.0f} "
                  f"{p.vorp:>7.1f} {p.team:>5} {d:>+9.1f}")

    print(f"Weeks 15-17 schedule for the {len(rows)} draftable players. "
          "A tiebreaker, never a reason to reach.")
    block("EASIEST PLAYOFF SCHEDULE", rows[:show])
    block("HARDEST PLAYOFF SCHEDULE", rows[-show:])


def main() -> int:
    league = load_league()
    opponents = playoff_opponents(league)
    if not opponents:
        print("missing data/raw/schedule_2026.csv — run: python3 fetch_data.py schedule")
        return 1

    allowed = points_allowed(league["scoring"])
    avg = league_average(allowed)
    diff = difficulty(allowed, avg, opponents)

    if len(sys.argv) > 1 and sys.argv[1] == "board":
        show_board(build_board(league, load_players()), diff, league)
    else:
        show_teams(diff, opponents)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
