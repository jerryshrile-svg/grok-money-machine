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

import math
import random
import sys
from collections import defaultdict

from engine import Player, build_board, load_league, load_players, snake_picks
from opponent import POS_CAP, RunTracker, choose, norm_pos, starter_needs


def _cheap_survival(pool, horizon):
    """P(each player lasts `horizon` more picks), without a nested simulation.

    A player's rank within the remaining pool by consensus is a good predictor of
    how soon he goes. Rank well inside the horizon and he's gone; well outside and
    he keeps. The logistic just smooths the boundary. Good enough to choose
    between candidates, and cheap enough to run inside every simulated pick.
    """
    if horizon <= 0:
        return {id(p): 1.0 for p in pool}
    ordered = sorted(pool, key=lambda p: p.adp)
    out = {}
    for rank, p in enumerate(ordered):
        out[id(p)] = 1.0 / (1.0 + math.exp((horizon - rank) / 3.0))
    return out


def _expected_best(pool, probs, league, positions=("QB", "RB", "WR", "TE")):
    """Expected best VORP still available at each position after the horizon."""
    exp = {}
    for pos in positions:
        cands = sorted(
            (p for p in pool if norm_pos(p.pos) == pos), key=lambda x: -x.vorp
        )
        ev, carry = 0.0, 1.0
        for p in cands[:25]:
            s = probs.get(id(p), 1.0)
            ev += carry * s * p.vorp
            carry *= 1 - s
            if carry < 0.001:
                break
        exp[pos] = ev
    return exp


def _wait_cost_pick(pool, roster_counts, round_no, league, rng, horizon=0):
    """The live assistant's rule: take whoever costs most to wait on.

    Not "best available" — best available ignores that some positions will still
    have a comparable player at your next pick and some won't.
    """
    probs = _cheap_survival(pool, horizon)
    exp_next = _expected_best(pool, probs, league)
    need = starter_needs(roster_counts, league)

    best, best_score = None, float("-inf")
    for p in pool:
        pos = norm_pos(p.pos)
        if pos in ("K", "DEF"):
            continue
        if roster_counts.get(pos, 0) >= POS_CAP.get(pos, 8):
            continue
        cost = p.vorp - exp_next.get(pos, 0.0)
        weight = 1.0 if (need.get(pos, 0) > 0 or need.get("FLEX", 0) > 0) else 0.35
        score = cost * weight
        if score > best_score:
            best, best_score = p, score
    return best or max(pool, key=lambda p: p.vorp)


def _my_pick(pool, roster_counts, round_no, rounds, strategy, league, rng, horizon=0):
    """Follow the strategy's positional preference, else best VORP available."""
    rounds_left = rounds - round_no + 1
    need_k = league["roster"].get("K", 0) - roster_counts["K"]
    need_d = league["roster"].get("DEF", 0) - roster_counts["DEF"]

    # Force K/DEF into the final rounds and never earlier.
    if rounds_left <= need_k + need_d:
        want = "K" if need_k else "DEF"
        cands = [p for p in pool if norm_pos(p.pos) == want]
        if cands:
            return min(cands, key=lambda p: p.adp)

    wanted = strategy[round_no - 1] if round_no - 1 < len(strategy) else "BPA"

    if wanted == "WAIT":
        return _wait_cost_pick(pool, roster_counts, round_no, league, rng, horizon)

    if wanted != "BPA":
        cands = [
            p
            for p in pool
            if norm_pos(p.pos) == wanted
            and roster_counts[norm_pos(p.pos)] < POS_CAP.get(wanted, 8)
        ]
        if cands:
            return max(cands, key=lambda p: p.vorp)

    cands = [
        p
        for p in pool
        if norm_pos(p.pos) not in ("K", "DEF")
        and roster_counts[norm_pos(p.pos)] < POS_CAP.get(norm_pos(p.pos), 8)
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


def opponent_keepers(pool, league, rng, count=None):
    """Take players off the board for opponents who keep somebody.

    Returns {overall_pick: player}. Each kept player consumes the keeping team's
    pick in the configured round, exactly like your Bijan pick does.

    Named keepers are used when you know them. `unknown_count` is the fallback:
    it samples that many players from the top of the board, which is where
    keepers actually come from — nobody protects their twelfth-round pick.
    """
    cfg = league.get("opponent_keepers", {})
    teams = league["teams"]
    my_slot = league["my_draft_slot"]
    by_name = {p.name: p for p in pool}

    slots = [s for s in range(1, teams + 1) if s != my_slot]
    rng.shuffle(slots)

    # A keeper costs the round that player went in last year, so the pick it
    # burns varies per player. Ranking candidates by surplus reproduces the
    # decision the other managers are actually making.
    from keepers import candidates as keeper_candidates

    ranked = [r for r in keeper_candidates(pool, league) if not r["mine"]]
    by_player = {r["player"].name: r for r in ranked}

    chosen: list = []
    for name in cfg.get("known", []):
        if isinstance(name, str) and name in by_name:
            chosen.append(by_name[name])

    n = cfg.get("unknown_count", 0) if count is None else count
    n = min(n, len(slots) - len(chosen))
    if n > 0:
        # Sample from the top of the surplus list rather than taking it exactly:
        # seven managers won't all identify the same seven best keepers, and one
        # team may hold two of them and keep only one.
        head = [r["player"] for r in ranked[: max(n * 2, cfg.get("pool_top_n", 14))]
                if r["player"] not in chosen]
        chosen += rng.sample(head, min(n, len(head)))

    out = {}
    for slot, player in zip(slots, chosen):
        rnd = by_player.get(player.name, {}).get("round", 1)
        rnd = min(max(1, rnd), league["rounds"])
        idx = slot - 1 if rnd % 2 == 1 else teams - slot
        out[(rnd - 1) * teams + idx + 1] = player
    return out


def run_draft(board, league, strategy, rng, track_availability=None, keeper_count=None):
    teams = league["teams"]
    rounds = league["rounds"]
    slot = league["my_draft_slot"]
    my_picks = set(snake_picks(slot, teams, rounds))

    # Keepers are off the board before anyone picks. In a keeper league this is
    # the single biggest reason published ADP lies to you.
    kept = {k["player"] for k in league.get("keepers", [])}
    mine = [p for p in board if p.name in kept and _is_mine(p, league)]
    pool = [p for p in board if p.name not in kept]

    opp_kept = opponent_keepers(pool, league, rng, keeper_count)
    for player in opp_kept.values():
        pool.remove(player)

    rosters = defaultdict(lambda: defaultdict(int))
    for p in mine:
        rosters["ME"][norm_pos(p.pos)] += 1

    runs = RunTracker()
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
                nxt = next((q for q in sorted(my_picks) if q > overall), None)
                horizon = (nxt - overall - 1) if nxt else 0
                pick = _my_pick(
                    pool, rosters["ME"], rnd, rounds, strategy, league, rng, horizon
                )
                mine.append(pick)
                rosters["ME"][norm_pos(pick.pos)] += 1
            else:
                team_id = f"T{overall % teams}"
                held = opp_kept.get(overall)
                if held is not None:
                    # That team spent this pick on its keeper before the draft.
                    rosters[team_id][norm_pos(held.pos)] += 1
                    runs.add(held.pos)
                    continue
                pick = choose(pool, rosters[team_id], rnd, league, rng, runs)
                rosters[team_id][norm_pos(pick.pos)] += 1
            runs.add(pick.pos)
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
    "Wait-cost (live tool)": ["WAIT"] * 14,
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


def keeper_sensitivity(board, league, n=300, seed=13):
    """How much does not knowing the other teams' keepers actually cost you?

    Re-runs the draft assuming 0..7 of them keep a top-of-the-board player. If
    the answer barely moves, stop worrying about it. If it moves a lot, that is
    the highest-value question you can ask your league chat.
    """
    teams = league["teams"]
    print(f"Effect of opponent keepers, {n} drafts each "
          f"(strategy: the live tool's wait-cost rule)\n")
    print(f"{'KEEPERS':>8} {'LINEUP PTS':>11} {'vs NONE':>9}   "
          f"{'YOUR FIRST TWO PICKS (most common)':<44}")
    print("-" * 76)

    baseline = None
    for count in range(0, teams):
        rng = random.Random(seed)
        totals, firsts = [], defaultdict(int)
        for _ in range(n):
            roster = run_draft(
                board, league, ["WAIT"] * league["rounds"], rng, keeper_count=count
            )
            totals.append(starting_lineup_points(roster, league))
            picked = [p for p in roster if p.name not in
                      {k["player"] for k in league.get("keepers", [])}]
            if len(picked) >= 2:
                firsts[f"{picked[0].name}, {picked[1].name}"] += 1
        mean = sum(totals) / len(totals)
        baseline = mean if baseline is None else baseline
        common = max(firsts.items(), key=lambda kv: kv[1])[0] if firsts else "-"
        print(f"{count:>8} {mean:>11.1f} {mean - baseline:>+9.1f}   {common[:44]:<44}")

    print("\nEach keeper removes a top-36 player and burns that team's round-"
          f"{league.get('opponent_keepers', {}).get('round', 1)} pick,")
    print("so the board gets thinner but the picks come back to you sooner.")


def draft_plan(board, league, n=400, seed=17):
    """What the winning rule actually does, pick by pick.

    Runs the wait-cost rule many times and reports what it took at each of your
    picks. Read it as a prior, not a script: the whole point of the rule is that
    it reacts to what falls. The position mix is the durable part.
    """
    rng = random.Random(seed)
    picks = snake_picks(league["my_draft_slot"], league["teams"], league["rounds"])
    keeper_picks = {
        k["pick_overall"] for k in league.get("keepers", []) if k.get("pick_overall")
    }
    real_picks = [p for p in picks if p not in keeper_picks]

    by_pick_pos = defaultdict(lambda: defaultdict(int))
    by_pick_player = defaultdict(lambda: defaultdict(int))

    for _ in range(n):
        roster = run_draft(board, league, ["WAIT"] * league["rounds"], rng)
        taken = [p for p in roster if p.name not in
                 {k["player"] for k in league.get("keepers", [])}]
        for pick_no, player in zip(real_picks, taken):
            by_pick_pos[pick_no][norm_pos(player.pos)] += 1
            by_pick_player[pick_no][player.name] += 1

    print(f"Round-by-round plan over {n} simulated drafts\n")
    print(f"{'PICK':>5} {'RD':>3}  {'POSITION MIX':<34} {'MOST LIKELY TARGETS':<44}")
    print("-" * 90)
    for pick_no in real_picks:
        rnd = (pick_no - 1) // league["teams"] + 1
        pos_counts = sorted(by_pick_pos[pick_no].items(), key=lambda kv: -kv[1])
        mix = "  ".join(f"{p} {c / n:.0%}" for p, c in pos_counts[:4])
        names = sorted(by_pick_player[pick_no].items(), key=lambda kv: -kv[1])[:3]
        targets = ", ".join(f"{nm.split(' ', 1)[-1][:14]} {c/n:.0%}" for nm, c in names)
        print(f"{pick_no:>5} {rnd:>3}  {mix:<34} {targets:<44}")


if __name__ == "__main__":
    league = load_league()
    board = build_board(league, load_players())
    mode = sys.argv[1] if len(sys.argv) > 1 else "strat"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if mode == "avail":
        availability(board, league, n=n or 1500)
    elif mode == "plan":
        draft_plan(board, league, n=n or 400)
    elif mode == "keepers":
        keeper_sensitivity(board, league, n=n or 300)
    else:
        compare_strategies(board, league, n=n or 800)
