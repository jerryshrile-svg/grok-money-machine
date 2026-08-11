"""Which player should I keep?

The league rule: a keeper costs you the round you got him in last year. Keep a
player you took in round 11 and he simply becomes your round-11 pick this year.

That makes the decision a surplus question, not a "who is best" question. The
right keeper is not the best player on last year's roster — it is the player
whose current value most exceeds what that pick would otherwise buy. Bijan
Robinson is the best player here by a distance and is close to the worst keeper,
because a round-1 keeper costs a pick that was going to return a round-1 player
anyway.

Two measurements, because they answer slightly different questions:

  SURPLUS   the player's projected points minus the expected points of whoever
            you would otherwise have taken with that pick. Fast, and it is the
            number the reasoning above is really about.

  ROSTER    full drafts run with each candidate installed as the keeper, scored
            on the starting lineup at the end. Slower, and it accounts for what
            the rest of the draft does in response — a keeper that fills a
            scarce position changes every later pick.

Both run paired against the same seeds, so the comparison is between keepers and
not between lucky drafts.

    python3 keeper_choice.py           # surplus table, then 300 drafts each
    python3 keeper_choice.py 100       # fewer drafts, faster
"""

from __future__ import annotations

import math
import random
import sys
from collections import defaultdict

import sim
from engine import build_board, load_league, load_players, snake_picks
from last_season import norm

# Last year's draft: the round each player was taken in, which is the pick he
# costs this year. Taken from the league's own draft-results page.
LAST_YEAR = [
    (1, "Bijan Robinson"),
    (2, "Justin Jefferson"),
    (3, "De'Von Achane"),
    (4, "DeVonta Smith"),
    (5, "George Kittle"),
    (6, "Patrick Mahomes II"),
    (7, "George Pickens"),
    (8, "Jameson Williams"),
    (9, "Tyrone Tracy Jr."),
    (10, "Ricky Pearsall"),
    (11, "Emeka Egbuka"),
    (12, "Tank Bigsby"),
    (13, "Kyler Murray"),
    (14, "Roschon Johnson"),
    (15, "Pat Bryant"),
]


def candidates(board, league):
    """Resolve each rostered player to this year's board and the pick he costs."""
    by_name = {norm(p.name): p for p in board}
    picks = snake_picks(league["my_draft_slot"], league["teams"], league["rounds"])
    out = []
    for rnd, name in LAST_YEAR:
        player = by_name.get(norm(name))
        if player is None:
            out.append({"round": rnd, "name": name, "player": None,
                        "pick": None, "why": "not in this year's consensus"})
            continue
        if rnd > league["rounds"]:
            out.append({"round": rnd, "name": name, "player": player,
                        "pick": None,
                        "why": f"no round {rnd} this year — draft is "
                               f"{league['rounds']} rounds"})
            continue
        out.append({"round": rnd, "name": player.name, "player": player,
                    "pick": picks[rnd - 1], "why": ""})
    return out


def expected_at_pick(board, league, n=400, seed=5):
    """Mean VORP of the player actually taken at each of your picks.

    VORP, not raw points. Comparing a quarterback's 241 points against a
    receiver's 176 says the quarterback is worth more, which is false — eight
    quarterbacks start in this league and the ninth-best is nearly as good as
    the first. The first version of this table used raw points and ranked Kyler
    Murray the best keeper on the roster by a distance, which is an artefact of
    the units, not a finding.

    Run with no keeper installed, so it measures what a pick is worth when
    nothing is occupying it. That is what a keeper is traded against.
    """
    bare = dict(league, keepers=[])
    picks = snake_picks(league["my_draft_slot"], league["teams"], league["rounds"])
    got: dict[int, list[float]] = defaultdict(list)
    for i in range(n):
        rng = random.Random(seed * 7919 + i)
        roster = sim.run_draft(board, bare, ["WAIT"] * league["rounds"], rng)
        for pick, player in zip(picks, roster):
            got[pick].append(player.vorp)
    return {p: sum(v) / len(v) for p, v in got.items() if v}


# Rounds 13 and 14 are where the simulator is forced to take a kicker and a
# defence. A keeper parked there eats one of those slots, and the lineup score
# ignores K and DEF entirely — so a worthless late keeper scores as though it
# cost nothing at all. It costs a real roster spot; the number just can't see it.
KDEF_ROUNDS = 2


def roster_strength(board, league, cand, n, seed=99):
    """Starting-lineup points from full drafts with this keeper installed."""
    keeper = [] if cand is None else [
        {"team": "ME", "player": cand["name"], "round": cand["round"],
         "pick_overall": cand["pick"]}
    ]
    cfg = dict(league, keepers=keeper)
    out = []
    for i in range(n):
        rng = random.Random(seed * 100_003 + i)
        roster = sim.run_draft(board, cfg, ["WAIT"] * league["rounds"], rng)
        out.append(sim.starting_lineup_points(roster, league))
    return out


def paired(a, b):
    diffs = [x - y for x, y in zip(a, b)]
    mu = sum(diffs) / len(diffs)
    if len(diffs) < 2:
        return mu, 0.0
    var = sum((d - mu) ** 2 for d in diffs) / (len(diffs) - 1)
    return mu, math.sqrt(var / len(diffs))


def main() -> int:
    league = load_league()
    board = build_board(league, load_players())
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 300

    cands = candidates(board, league)
    baseline = expected_at_pick(board, league)

    print("\nKEEPER SURPLUS — value now, minus what that pick would otherwise buy")
    print("In VORP, so positions are comparable.\n")
    print(f"{'RD':>3} {'PICK':>5}  {'PLAYER':<22}{'POS':<6}{'VORP':>7}"
          f"{'PICK BUYS':>10}{'SURPLUS':>9}")
    print("-" * 66)
    scored = []
    for c in cands:
        if c["player"] is None or c["pick"] is None:
            print(f"{c['round']:>3} {'—':>5}  {c['name']:<22}{'':<6}{'':>7}{'':>10}"
                  f"   {c['why']}")
            continue
        p = c["player"]
        buys = baseline.get(c["pick"], 0.0)
        c["surplus"] = p.vorp - buys
        scored.append(c)
        print(f"{c['round']:>3} {c['pick']:>5}  {p.name:<22}"
              f"{p.pos + str(p.pos_rank):<6}{p.vorp:>7.0f}{buys:>10.0f}"
              f"{c['surplus']:>+9.0f}")

    # Every eligible candidate goes through the full simulation. Pre-filtering
    # on the surplus heuristic is how the quarterback artefact above nearly
    # decided which players got measured at all.
    scored.sort(key=lambda c: -c["surplus"])
    top = scored

    print(f"\n\nFULL DRAFTS — {n} paired drafts with each of the "
          f"{len(top)} eligible players installed as keeper")
    print("Scored on the starting lineup, so it counts what the rest of the "
          "draft does\nin response, not just the keeper himself.\n")

    # Keeping nobody is a real option and the only honest reference point: you
    # hand back the keeper and draft all fourteen picks yourself.
    none_arm = roster_strength(board, league, None, n)
    results = {c["name"]: roster_strength(board, league, c, n) for c in top}

    print(f"{'PLAYER':<22}{'RD':>3}{'PICK':>6}{'LINEUP PTS':>12}"
          f"{'vs KEEPING NOBODY':>20}")
    print("-" * 68)
    print(f"{'— keep nobody —':<22}{'':>3}{'':>6}"
          f"{sum(none_arm) / len(none_arm):>12.0f}{'baseline':>20}")
    last = league["rounds"] - KDEF_ROUNDS
    for c in sorted(top, key=lambda c: -sum(results[c["name"]]) / n):
        vals = results[c["name"]]
        gain, se = paired(vals, none_arm)
        note = "  (eats a K/DEF pick — overstated)" if c["round"] > last else ""
        print(f"{c['name']:<22}{c['round']:>3}{c['pick']:>6}"
              f"{sum(vals) / len(vals):>12.0f}{gain:>+14.0f} ± {se:<3.0f}{note}")

    print("\nTwo keepers within about two standard errors of each other are a coin")
    print("flip; take the one whose position you would rather lock in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
