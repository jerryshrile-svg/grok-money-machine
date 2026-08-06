"""How the other seven managers behave. One model, used everywhere.

Both the strategy simulator and the live assistant's survival estimates run on
this, so a fix to opponent behavior improves every number the toolkit prints.

A pure "follow the rankings with noise" model gets an 8-team league badly wrong in
two directions at once:

  - It hoards quarterbacks. Consensus rankings are built for 12-team leagues, so
    they price QBs for twelve starting jobs. Yours has eight.
  - It never drafts a kicker or defense, because their consensus rank is ~200 and
    some skill player always looks better. In your real draft those are sixteen
    guaranteed picks in the last two rounds.

Both come from the same omission: managers draft to fill a lineup, not to collect
the highest-ranked players. So this model tracks each team's roster and scores
candidates by rank *plus* how badly that team still needs the position — and once
a team has more holes than picks left, it can only take players who fill one.

It also models positional runs. Drafters herd: once three tight ends go, the room
panics about tight ends. Independent draws never reproduce that, which quietly
makes every "he'll still be there" estimate too optimistic.
"""

from __future__ import annotations

import random
from collections import defaultdict

# Spread of opponent deviation from consensus rank, in draft slots.
ADP_NOISE = 8.0

# How much a team prefers a player who fills an open starting slot.
NEED_BONUS = 22.0
FLEX_BONUS = 8.0

# Penalty per player already rostered beyond need at a capped position. Stops
# managers from stockpiling backup QBs and TEs they can never start.
BACKUP_PENALTY = 12.0

# Each recent pick at a position pulls that position forward for everyone else.
# Capped, and deliberately small: consensus ranks at the top of the board sit
# barely a slot apart, so an uncapped nudge compounds — one receiver goes, which
# makes receivers look better, which pulls another — until every first round is a
# runaway run at one position and elite backs fall to pick 11. Runs are real but
# they are a nudge, not a stampede.
RUN_WEIGHT = 1.5
RUN_WINDOW = 8
RUN_CAP = 3

# Nobody takes a kicker or defense before the endgame.
KDEF_LAST_ROUNDS = 3

POS_CAP = {"QB": 2, "TE": 2, "K": 1, "DEF": 1, "RB": 7, "WR": 8}

# Weighting for players you don't currently need.
#
# These are deliberately equal. The obvious-looking improvement is to discount a
# backup at a one-slot position — a second quarterback in a one-QB league looks
# worthless when the waiver wire holds hundreds of unowned players. That was
# tried at 0.08 and measured both ways across five seasons:
#
#     BACKUP_WEIGHT     draft-only    with waivers
#     0.08                    1591            1611
#     0.35                    1606            1622
#
# It lost under both, including the arm that allows streaming, and the full
# backtest fell from +44 points a season over the consensus list to +27. Backup
# value is real: byes and injuries have to be covered, and a high-value QB2 or
# TE2 can genuinely beat the marginal receiver. Don't re-apply the intuition
# without re-running that comparison.
DEPTH_WEIGHT = 0.35
BACKUP_WEIGHT = 0.35


def norm_pos(pos: str) -> str:
    return "DEF" if pos in ("DST", "D/ST") else pos


def starter_needs(counts: dict[str, int], league: dict) -> dict[str, int]:
    """Unfilled starting slots, with FLEX counted from positional surplus."""
    roster = league["roster"]
    flex_ok = set(league.get("flex_eligible", ["RB", "WR", "TE"]))

    need = {}
    for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
        need[pos] = max(0, roster.get(pos, 0) - counts.get(pos, 0))

    surplus = sum(max(0, counts.get(p, 0) - roster.get(p, 0)) for p in flex_ok)
    need["FLEX"] = max(0, roster.get("FLEX", 0) - surplus)
    return need


def _fills_need(pos: str, need: dict[str, int], league: dict) -> bool:
    if need.get(pos, 0) > 0:
        return True
    flex_ok = set(league.get("flex_eligible", ["RB", "WR", "TE"]))
    return pos in flex_ok and need.get("FLEX", 0) > 0


class RunTracker:
    """Rolling count of recent picks by position, for herding pressure."""

    def __init__(self, window: int = RUN_WINDOW):
        self.window = window
        self.recent: list[str] = []

    def add(self, pos: str) -> None:
        self.recent.append(norm_pos(pos))
        if len(self.recent) > self.window:
            self.recent.pop(0)

    def pressure(self, pos: str) -> int:
        return min(self.recent.count(norm_pos(pos)), RUN_CAP)

    def copy(self) -> "RunTracker":
        clone = RunTracker(self.window)
        clone.recent = list(self.recent)
        return clone


def value_weight(pos: str, need: dict, league: dict) -> float:
    """How much a player's raw value counts, given what your roster still needs.

    A player who fills an open starting slot counts fully. Everyone else is
    discounted, but only to the depth weight — see the note on the constants for
    why backups are not discounted further, which is not what intuition says.
    """
    flex_ok = set(league.get("flex_eligible", ["RB", "WR", "TE"]))
    if need.get(pos, 0) > 0:
        return 1.0
    if pos in flex_ok:
        return 1.0 if need.get("FLEX", 0) > 0 else DEPTH_WEIGHT
    return BACKUP_WEIGHT


def choose(
    pool: list,
    counts: dict[str, int],
    round_no: int,
    league: dict,
    rng: random.Random,
    runs: "RunTracker | None" = None,
    noise: float = ADP_NOISE,
):
    """Pick a player for one opponent team. Returns None only if the pool is empty."""
    if not pool:
        return None

    rounds = league["rounds"]
    rounds_left = rounds - round_no + 1
    need = starter_needs(counts, league)
    holes = sum(need.values())

    # Out of slack: every remaining pick has to fill a starting hole.
    forced = rounds_left <= holes

    best, best_score = None, float("inf")
    fallback, fallback_score = None, float("inf")

    for p in pool:
        pos = norm_pos(p.pos)
        if counts.get(pos, 0) >= POS_CAP.get(pos, 8):
            continue
        if pos in ("K", "DEF") and rounds_left > KDEF_LAST_ROUNDS:
            continue

        score = p.adp + rng.gauss(0, noise)
        fills = _fills_need(pos, need, league)

        if fills:
            score -= NEED_BONUS if need.get(pos, 0) > 0 else FLEX_BONUS
        elif pos in ("QB", "TE", "K", "DEF"):
            # A player at a capped position they cannot start.
            score += BACKUP_PENALTY * max(1, counts.get(pos, 0))

        if runs is not None:
            score -= RUN_WEIGHT * runs.pressure(pos)

        if score < fallback_score:
            fallback, fallback_score = p, score
        if forced and not fills:
            continue
        if score < best_score:
            best, best_score = p, score

    return best or fallback or pool[0]
