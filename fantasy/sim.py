"""Monte Carlo draft simulator.

Answers the two questions that actually decide drafts:

  1. "If I pass on this guy, what's the chance he's still there at my next pick?"
  2. "Which draft strategy maximizes my expected starting lineup?"

Opponents are modelled as ADP-followers with noise plus roster-need constraints,
which is a good approximation of a casual 8-team league.

  python3 sim.py avail     # availability curves at each of your picks
  python3 sim.py strat     # head-to-head strategy comparison
"""

from __future__ import annotations

import random
import sys
from collections import defaultdict

from engine import Player, build_board, load_league, load_players, snake_picks

# How much opponents deviate from ADP. ~1 round of noise in an 8-team league.
ADP_NOISE = 8.0

# Soft caps on how many of each position a sane opponent rosters.
POS_CAP = {"QB": 2, "TE": 2, "K": 1, "DEF": 1, "RB": 6, "WR": 7}


def _opponent_pick(pool, roster_counts, round_no, rounds, rng):
    """Pick the lowest noisy-ADP player that doesn't violate roster sanity."""
    late = round_no >= rounds - 1  # K/DEF only come off the board at the end

    best, best_score = None, float("inf")
    for p in pool:
        if p.pos in ("K", "DEF", "DST") and not late:
            continue
        if roster_counts[p.pos] >= POS_CAP.get(p.pos, 8):
            continue
        s = p.adp + rng.gauss(0, ADP_NOISE)
        if s < best_score:
            best, best_score = p, s

    if best is None:  # everything capped out; just take best ADP
        best = min(pool, key=lambda p: p.adp)
    return best


def _my_pick(pool, roster_counts, round_no, rounds, strategy, league, rng):
    """Follow the strategy's positional preference, else best VORP available."""
    rounds_left = rounds - round_no + 1
    need_k = league["roster"].get("K", 0) - roster_counts["K"]
    need_d = league["roster"].get("DEF", 0) - roster_counts["DEF"]

    # Force K/DEF into the final rounds and never earlier.
    if rounds_left <= need_k + need_d:
        want = "K" if need_k else "DEF"
        cands = [p for p in pool if p.pos in (want, "DST" if want == "DEF" else want)]
        if cands:
            return min(cands, key=lambda p: p.adp)

    wanted = strategy[round_no - 1] if round_no - 1 < len(strategy) else "BPA"

    if wanted != "BPA":
        cands = [
            p
            for p in pool
            if p.pos == wanted and roster_counts[p.pos] < POS_CAP.get(p.pos, 8)
        ]
        if cands:
            return max(cands, key=lambda p: p.vorp)

    cands = [
        p
        for p in pool
        if p.pos not in ("K", "DEF", "DST")
        and roster_counts[p.pos] < POS_CAP.get(p.pos, 8)
    ]
    return max(cands or pool, key=lambda p: p.vorp)


def starting_lineup_points(roster: list[Player], league: dict) -> float:
    """Best legal starting lineup from a roster — the only thing that scores."""
    slots = league["roster"]
    flex_ok = set(league.get("flex_eligible", ["RB", "WR", "TE"]))
    by_pos = defaultdict(list)
    for p in roster:
        by_pos[p.pos].append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda x: -x.points)

    total, used = 0.0, set()
    for pos in ("QB", "RB", "WR", "TE"):
        for p in by_pos[pos][: slots.get(pos, 0)]:
            total += p.points
            used.add(id(p))

    flex_pool = sorted(
        (p for p in roster if p.pos in flex_ok and id(p) not in used),
        key=lambda x: -x.points,
    )
    for p in flex_pool[: slots.get("FLEX", 0)]:
        total += p.points
    return total


def run_draft(board, league, strategy, rng, track_availability=None):
    teams = league["teams"]
    rounds = league["rounds"]
    slot = league["my_draft_slot"]
    my_picks = set(snake_picks(slot, teams, rounds))

    # Keepers are off the board before anyone picks. In a keeper league this is
    # the single biggest reason published ADP lies to you.
    kept = {k["player"] for k in league.get("keepers", [])}
    mine = [p for p in board if p.name in kept and _is_mine(p, league)]
    pool = [p for p in board if p.name not in kept]

    rosters = defaultdict(lambda: defaultdict(int))
    for p in mine:
        rosters["ME"][p.pos] += 1

    overall = 0
    for rnd in range(1, rounds + 1):
        for _ in range(teams):
            overall += 1
            if not pool:
                break
            is_me = overall in my_picks

            if track_availability is not None and is_me:
                for p in pool:
                    track_availability[overall].add(p.name)

            if is_me:
                if any(k.get("pick_overall") == overall for k in league.get("keepers", [])):
                    continue  # keeper already occupies this pick
                pick = _my_pick(pool, rosters["ME"], rnd, rounds, strategy, league, rng)
                mine.append(pick)
                rosters["ME"][pick.pos] += 1
            else:
                team_id = f"T{overall % teams}"
                pick = _opponent_pick(pool, rosters[team_id], rnd, rounds, rng)
                rosters[team_id][pick.pos] += 1
            pool.remove(pick)

    return mine


def _is_mine(player, league):
    return any(
        k["player"] == player.name and k.get("team") == "ME"
        for k in league.get("keepers", [])
    )


def availability(board, league, n=3000, seed=7):
    rng = random.Random(seed)
    picks = snake_picks(league["my_draft_slot"], league["teams"], league["rounds"])
    counts = defaultdict(lambda: defaultdict(int))

    for _ in range(n):
        track = defaultdict(set)
        run_draft(board, league, ["BPA"] * league["rounds"], rng, track_availability=track)
        for pick_no, names in track.items():
            for name in names:
                counts[pick_no][name] += 1

    print(f"Availability over {n} simulated drafts — P(player is still on the board)\n")
    for pick_no in picks[:6]:
        rows = sorted(counts[pick_no].items(), key=lambda kv: -kv[1])
        board_by_name = {p.name: p for p in board}
        rows = [
            (name, c / n, board_by_name[name])
            for name, c in rows
            if name in board_by_name
        ]
        rows.sort(key=lambda r: -r[2].vorp)
        print(f"--- Pick {pick_no} ---")
        for name, prob, p in rows[:8]:
            bar = "#" * int(prob * 20)
            print(f"  {name:<24} {p.pos:<4} VORP {p.vorp:>6.1f}  {prob:>5.0%} {bar}")
        print()


STRATEGIES = {
    "BPA (pure value)": ["BPA"] * 14,
    "Hero RB -> WR wall": ["RB", "WR", "WR", "WR", "BPA", "BPA", "TE", "BPA", "QB", "BPA", "BPA", "BPA", "BPA", "BPA"],
    "RB heavy": ["RB", "RB", "RB", "WR", "WR", "BPA", "BPA", "TE", "QB", "BPA", "BPA", "BPA", "BPA", "BPA"],
    "Elite QB early": ["RB", "QB", "WR", "WR", "RB", "BPA", "TE", "BPA", "BPA", "BPA", "BPA", "BPA", "BPA", "BPA"],
    "Elite TE early": ["RB", "TE", "WR", "WR", "RB", "BPA", "BPA", "QB", "BPA", "BPA", "BPA", "BPA", "BPA", "BPA"],
    "Zero RB": ["WR", "WR", "WR", "TE", "BPA", "RB", "RB", "QB", "RB", "BPA", "BPA", "BPA", "BPA", "BPA"],
}


def compare_strategies(board, league, n=2000, seed=11):
    print(f"Expected starting-lineup points over {n} simulated drafts\n")
    results = []
    for label, strat in STRATEGIES.items():
        rng = random.Random(seed)
        totals = []
        for _ in range(n):
            roster = run_draft(board, league, strat, rng)
            totals.append(starting_lineup_points(roster, league))
        totals.sort()
        mean = sum(totals) / len(totals)
        p10 = totals[int(0.10 * len(totals))]
        p90 = totals[int(0.90 * len(totals))]
        results.append((mean, p10, p90, label))

    results.sort(reverse=True)
    best = results[0][0]
    print(f"{'STRATEGY':<22} {'MEAN':>8} {'FLOOR':>8} {'CEIL':>8} {'vs BEST':>9}")
    for mean, p10, p90, label in results:
        print(f"{label:<22} {mean:>8.1f} {p10:>8.1f} {p90:>8.1f} {mean - best:>+9.1f}")


if __name__ == "__main__":
    league = load_league()
    board = build_board(league, load_players())
    mode = sys.argv[1] if len(sys.argv) > 1 else "strat"
    if mode == "avail":
        availability(board, league, n=int(sys.argv[2]) if len(sys.argv) > 2 else 1500)
    else:
        compare_strategies(board, league, n=int(sys.argv[2]) if len(sys.argv) > 2 else 800)
