"""Value-based draft board calibrated to a specific league's settings.

The whole point: public rankings are built for 12-team full-PPR leagues. This
recomputes every player's value against *your* scoring and *your* starting
lineup requirements, which is where the mispricings live.

Pure stdlib so it runs anywhere with `python3 engine.py`.
"""

from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass, field
from typing import Iterable

HERE = os.path.dirname(os.path.abspath(__file__))

# Positions that can actually be drafted meaningfully. K/DEF are handled
# separately because their value is ~zero until the last two rounds.
SKILL = ("QB", "RB", "WR", "TE")

# Only these columns are scoring inputs. Everything else in a projections CSV
# (bye week, yahoo_id, ceiling, ...) is metadata and must not be scored.
STAT_KEYS = frozenset(
    (
        "pass_yd", "pass_td", "pass_int", "rush_yd", "rush_td",
        "rec", "rec_yd", "rec_td", "fumble_lost", "two_pt",
    )
)


@dataclass
class Player:
    name: str
    pos: str
    team: str
    adp: float
    stats: dict[str, float] = field(default_factory=dict)
    points: float = 0.0
    ceiling: float = 0.0
    floor: float = 0.0
    bye: str = ""
    ecr_best: float = 0.0
    ecr_worst: float = 0.0
    vorp: float = 0.0
    tier: int = 0
    pos_rank: int = 0

    @property
    def value_rank_vs_adp(self) -> float:
        """Positive means the field is letting them slide past their value."""
        return self.adp - self.vorp_rank

    vorp_rank: int = 0


def load_league(path: str | None = None) -> dict:
    path = path or os.path.join(HERE, "league.json")
    with open(path) as fh:
        return json.load(fh)


def load_players(path: str | None = None) -> list[Player]:
    """Read a projections CSV.

    Required columns: name, pos, team, adp
    Optional stat columns (any subset): pass_yd, pass_td, pass_int, rush_yd,
    rush_td, rec, rec_yd, rec_td, fumble_lost, two_pt

    If a `points` column is present it overrides the computed total, so you can
    drop in a source that only publishes fantasy points.
    """
    if path is None:
        path = os.path.join(HERE, "data", "projections.csv")
    if not os.path.exists(path):
        raise SystemExit(
            f"no projections at {path}\n"
            "build them from free public data first:\n"
            "    python3 fetch_data.py\n"
            "    python3 build_projections.py"
        )
    players: list[Player] = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if not row.get("name"):
                continue
            stats = {}
            for key, raw in row.items():
                if key not in STAT_KEYS or raw in (None, "", "NA"):
                    continue
                try:
                    stats[key] = float(raw)
                except ValueError:
                    continue
            p = Player(
                name=row["name"].strip(),
                pos=row["pos"].strip().upper(),
                team=(row.get("team") or "").strip().upper(),
                adp=float(row["adp"]) if row.get("adp") else 999.0,
                stats=stats,
            )
            if row.get("points"):
                p.points = float(row["points"])
            for attr in ("ceiling", "floor", "ecr_best", "ecr_worst"):
                if row.get(attr):
                    setattr(p, attr, float(row[attr]))
            p.bye = (row.get("bye") or "").strip()
            players.append(p)
    return players


def score(player: Player, scoring: dict[str, float]) -> float:
    if player.points:  # explicit projection wins
        return player.points
    return sum(scoring.get(k, 0.0) * v for k, v in player.stats.items())


def replacement_levels(players: Iterable[Player], league: dict) -> dict[str, float]:
    """Flex-aware replacement baselines.

    Fill every team's dedicated starting slots first, then hand the FLEX slots
    to whichever RB/WR/TE are next-best overall. Replacement level for a
    position is the *next* player after league-wide starter demand is met.

    This is the step that makes an 8-team league look so different from the
    rankings everyone else is drafting off of: with only 8 QB and 8 TE starters,
    those baselines sit absurdly high.
    """
    teams = league["teams"]
    roster = league["roster"]
    flex_ok = set(league.get("flex_eligible", ["RB", "WR", "TE"]))

    by_pos: dict[str, list[Player]] = {}
    for p in players:
        by_pos.setdefault(p.pos, []).append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: -x.points)

    # Dedicated starters consumed league-wide.
    demand = {pos: roster.get(pos, 0) * teams for pos in by_pos}

    # Distribute flex slots greedily to the best remaining flex-eligible player.
    cursor = {pos: demand.get(pos, 0) for pos in by_pos}
    for _ in range(roster.get("FLEX", 0) * teams):
        best_pos, best_pts = None, float("-inf")
        for pos in flex_ok:
            pool = by_pos.get(pos, [])
            idx = cursor.get(pos, 0)
            if idx < len(pool) and pool[idx].points > best_pts:
                best_pos, best_pts = pos, pool[idx].points
        if best_pos is None:
            break
        cursor[best_pos] += 1

    levels: dict[str, float] = {}
    for pos, pool in by_pos.items():
        idx = min(cursor.get(pos, 0), len(pool) - 1)
        levels[pos] = pool[idx].points if pool else 0.0
    return levels


def assign_tiers(players: list[Player], sensitivity: float = 1.0) -> None:
    """Break the board into tiers.

    Tiers matter more than ranks on draft day: inside a tier you take whoever
    will be gone soonest, across a tier break you don't wait.

    Preferred signal is expert *disagreement*. Each player carries a best- and
    worst-case consensus rank; while those ranges keep overlapping, the panel
    can't separate the players and neither should you. A tier ends where the
    overlap does.

    Falls back to gaps in VORP when rank ranges aren't in the data.
    """
    for pos in {p.pos for p in players}:
        pool = sorted([p for p in players if p.pos == pos], key=lambda x: -x.vorp)
        for i, p in enumerate(pool, 1):
            p.pos_rank = i

        if len(pool) < 3:
            for p in pool:
                p.tier = 1
            continue

        if all(p.ecr_best and p.ecr_worst for p in pool):
            # Compare against the tier *leader's* worst case, not a running max:
            # carrying the max forward lets one high-variance player chain every
            # remaining player into the same tier.
            tier, leader_worst = 1, pool[0].ecr_worst
            for p in pool:
                if p.ecr_best > leader_worst:  # no overlap with the tier leader
                    tier += 1
                    leader_worst = p.ecr_worst
                p.tier = tier
            continue

        gaps = [pool[i].vorp - pool[i + 1].vorp for i in range(len(pool) - 1)]
        mean = sum(gaps) / len(gaps)
        sd = math.sqrt(sum((g - mean) ** 2 for g in gaps) / len(gaps)) or 1e-9
        threshold = mean + sensitivity * sd
        tier = 1
        for i, p in enumerate(pool):
            p.tier = tier
            if i < len(gaps) and gaps[i] > threshold:
                tier += 1


def build_board(league: dict, players: list[Player]) -> list[Player]:
    scoring = league["scoring"]
    for p in players:
        p.points = score(p, scoring)

    levels = replacement_levels(players, league)
    for p in players:
        # K/DEF get pinned to ~zero value: in an 8-team league the gap between
        # the best and 10th-best of either is noise. Never spend real capital.
        if p.pos in ("K", "DEF", "DST"):
            p.vorp = 0.0
        else:
            p.vorp = p.points - levels.get(p.pos, 0.0)

    assign_tiers(players)
    board = sorted(players, key=lambda x: -x.vorp)
    for i, p in enumerate(board, 1):
        p.vorp_rank = i
    return board


def snake_picks(slot: int, teams: int, rounds: int) -> list[int]:
    """Overall pick numbers for a draft slot in a snake draft."""
    picks = []
    for rnd in range(1, rounds + 1):
        if rnd % 2 == 1:
            picks.append((rnd - 1) * teams + slot)
        else:
            picks.append((rnd - 1) * teams + (teams - slot + 1))
    return picks


if __name__ == "__main__":
    league = load_league()
    players = load_players()
    board = build_board(league, players)

    levels = replacement_levels(players, league)
    print(f"League: {league['teams']} teams | replacement baselines (pts):")
    for pos in SKILL:
        if pos in levels:
            print(f"  {pos}: {levels[pos]:.1f}")
    print()

    picks = snake_picks(league["my_draft_slot"], league["teams"], league["rounds"])
    print(f"Your picks: {', '.join(str(p) for p in picks)}\n")

    print(f"{'#':>3} {'PLAYER':<24} {'POS':<4} {'TIER':>4} {'PTS':>7} {'VORP':>7} {'ADP':>6} {'EDGE':>6}")
    for i, p in enumerate(board[:60], 1):
        edge = p.adp - i
        print(
            f"{i:>3} {p.name:<24} {p.pos + str(p.pos_rank):<4} {p.tier:>4} "
            f"{p.points:>7.1f} {p.vorp:>7.1f} {p.adp:>6.1f} {edge:>+6.1f}"
        )
