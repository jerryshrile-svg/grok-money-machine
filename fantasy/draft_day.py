"""Live draft assistant. Run this in a terminal next to your Yahoo draft window.

You type each pick as it happens; it keeps the board, tracks your roster needs,
and — the part that actually wins you picks — tells you how likely each target is
to survive until your next pick, and what you lose by waiting.

    python3 draft_day.py

Commands (fuzzy name matching, so "jeff" finds Justin Jefferson):

    <name>          someone else drafted this player
    me <name>       YOU drafted this player
    why <name>      last season's usage and luck for this player
    undo            take back the last pick
    board / b       best available by value
    rb / wr / te / qb / k / def    best available at that position
    go / t          recommendation for your pick, with survival odds
    roster / r      your roster and what you still need
    picks           your remaining pick numbers
    save / load     draft state persists to draft_state.json automatically
    quit
"""

from __future__ import annotations

import difflib
import json
import os
import random
import sys
from collections import defaultdict

from engine import (
    HERE,
    build_board,
    load_league,
    load_players,
    slot_for_pick,
    snake_picks,
)
from opponent import RunTracker, choose, value_weight

STATE_PATH = os.path.join(HERE, "draft_state.json")

SIM_TRIALS = 300

BOLD, DIM, RED, GRN, YEL, CYA, OFF = (
    "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m",
)


def _norm(pos: str) -> str:
    return "DEF" if pos in ("DST", "D/ST") else pos


# "James Cook III" has to answer to "cook", not to "iii".
SUFFIXES = frozenset(("jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"))


def _surname(name: str) -> str:
    parts = [w for w in name.lower().split() if w not in SUFFIXES]
    return parts[-1] if parts else ""


# Typed at a "which?" prompt these mean "get me out of here", not "find a player
# whose name contains this".
COMMAND_WORDS = frozenset((
    "go", "t", "targets", "rec", "board", "b", "roster", "r", "picks",
    "undo", "save", "quit", "q", "exit", "help", "h", "?",
    "rb", "wr", "te", "qb", "k", "def",
))


class Draft:
    def __init__(self, league, board):
        self.league = league
        self.board = board
        self.by_name = {p.name: p for p in board}
        self.teams = league["teams"]
        self.rounds = league["rounds"]
        self.my_picks = snake_picks(league["my_draft_slot"], self.teams, self.rounds)
        self.picks: list[dict] = []  # [{pick, name, mine}]
        self.rng = random.Random(1234)
        self._season = None  # 2025 context, loaded on first use (parses ~16 MB)
        self.keeper_names = {k["player"] for k in league.get("keepers", [])}
        self.keeper_picks = {
            k["pick_overall"] for k in league.get("keepers", []) if k.get("pick_overall")
        }

    # ---------- state ----------

    @property
    def on_the_clock(self) -> int:
        return len(self.picks) + 1

    @property
    def drafted(self) -> set[str]:
        return {p["name"] for p in self.picks}

    @property
    def available(self) -> list:
        # Keepers are unavailable to everyone from the first pick, not just once
        # their slot comes up — otherwise the sim lets opponents draft them.
        taken = self.drafted | self.keeper_names
        return [p for p in self.board if p.name not in taken]

    @property
    def my_roster(self) -> list:
        return [self.by_name[p["name"]] for p in self.picks if p["mine"]]

    def next_pick(self, after: int | None = None) -> int | None:
        """Your next pick where you actually choose — keeper slots don't count."""
        after = after if after is not None else self.on_the_clock - 1
        for p in self.my_picks:
            if p > after and p not in self.keeper_picks:
                return p
        return None

    def current_round(self) -> int:
        return (self.on_the_clock - 1) // self.teams + 1

    @property
    def runs(self) -> RunTracker:
        """Recent picks by position, rebuilt from the log.

        Derived rather than incrementally maintained so that undo, keeper
        auto-advance, and resuming a saved draft can't leave it out of step.
        """
        tracker = RunTracker()
        for entry in self.picks[-tracker.window:]:
            player = self.by_name.get(entry["name"])
            if player:
                tracker.add(player.pos)
        return tracker

    # ---------- mutation ----------

    def record(self, player, mine: bool):
        self.picks.append({"pick": self.on_the_clock, "name": player.name, "mine": mine})
        self.auto_advance()
        self.save()

    def auto_advance(self):
        """Drop in any keeper that occupies the pick now on the clock."""
        changed = True
        while changed:
            changed = False
            for k in self.league.get("keepers", []):
                if k.get("pick_overall") != self.on_the_clock:
                    continue
                if k["player"] in self.drafted:
                    continue
                if k["player"] not in self.by_name:
                    print(f"{YEL}! keeper '{k['player']}' not in projections{OFF}")
                    continue
                self.picks.append(
                    {"pick": self.on_the_clock, "name": k["player"], "mine": k.get("team") == "ME"}
                )
                who = "YOU keep" if k.get("team") == "ME" else f"{k.get('team','?')} keeps"
                print(f"{DIM}  [auto] pick {self.picks[-1]['pick']}: {who} {k['player']}{OFF}")
                changed = True

    def undo(self):
        if not self.picks:
            print("nothing to undo")
            return
        # Don't strand a keeper as the last entry — pop it too.
        gone = self.picks.pop()
        keeper_names = {k["player"] for k in self.league.get("keepers", [])}
        while self.picks and self.picks[-1]["name"] in keeper_names:
            self.picks.pop()
        print(f"undid pick {gone['pick']}: {gone['name']}")
        self.save()

    def save(self):
        with open(STATE_PATH, "w") as fh:
            json.dump({"picks": self.picks}, fh, indent=2)

    def load(self):
        if not os.path.exists(STATE_PATH):
            return False
        with open(STATE_PATH) as fh:
            self.picks = json.load(fh).get("picks", [])
        return True

    @property
    def season(self):
        """2025 context, or None if the raw data isn't downloaded.

        Deliberately fail-soft. This is a supporting column; the draft cannot
        stop because an optional file is missing while the clock is running.
        """
        if self._season is None:
            try:
                from last_season import Season

                print(f"{DIM}  (loading 2025 data...){OFF}")
                self._season = Season(self.league["scoring"])
            except (OSError, ImportError) as exc:
                print(f"{YEL}  2025 context unavailable ({exc.__class__.__name__}); "
                      f"run 'python3 fetch_data.py' for the LY column. "
                      f"Everything else works.{OFF}")
                self._season = False
        return self._season or None

    def poe_of(self, player) -> float | None:
        """Last season's points over expected per game, if the player has a 2025."""
        season = self.season
        if season is None:
            return None
        d = season.get(player.name)
        return d["poe_pg"] if d else None

    # ---------- analysis ----------

    def needs(self) -> dict[str, int]:
        """Remaining dedicated starter slots, flex counted separately."""
        slots = self.league["roster"]
        have = defaultdict(int)
        for p in self.my_roster:
            have[_norm(p.pos)] += 1
        need = {}
        for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
            need[pos] = max(0, slots.get(pos, 0) - have[pos])
        flex_ok = set(self.league.get("flex_eligible", ["RB", "WR", "TE"]))
        surplus = sum(
            max(0, have[p] - slots.get(p, 0)) for p in flex_ok
        )
        need["FLEX"] = max(0, slots.get("FLEX", 0) - surplus)
        return need

    def opponent_rosters(self) -> dict[int, dict[str, int]]:
        """Rebuild every other team's roster from the pick log.

        The snake tells us who owned each pick, so survival estimates can know
        that the team picking next already has a quarterback and won't take one.
        """
        rosters: dict[int, dict[str, int]] = {
            s: defaultdict(int) for s in range(1, self.teams + 1)
        }
        my_slot = self.league["my_draft_slot"]
        for entry in self.picks:
            slot = slot_for_pick(entry["pick"], self.teams)
            if slot == my_slot:
                continue
            player = self.by_name.get(entry["name"])
            if player:
                rosters[slot][_norm(player.pos)] += 1
        return rosters

    def survival(self, horizon: int, trials: int = SIM_TRIALS) -> dict[str, float]:
        """P(each player is still available after `horizon` opponent picks).

        Runs the same need-aware opponent model the strategy simulator uses,
        seeded with each team's actual roster so far.
        """
        pool_all = self.available
        if horizon <= 0:
            return {p.name: 1.0 for p in pool_all}

        # Only players near the top of the board realistically come off it.
        contenders = sorted(pool_all, key=lambda p: p.adp)[: horizon * 5 + 40]
        base_rosters = self.opponent_rosters()
        start = self.on_the_clock

        survived = defaultdict(int)
        for _ in range(trials):
            pool = list(contenders)
            rosters = {s: dict(c) for s, c in base_rosters.items()}
            runs = self.runs.copy()
            for step in range(horizon):
                overall = start + step
                slot = slot_for_pick(overall, self.teams)
                rnd = (overall - 1) // self.teams + 1
                pick = choose(pool, rosters[slot], rnd, self.league, self.rng, runs)
                if pick is None:
                    break
                rosters[slot][_norm(pick.pos)] = (
                    rosters[slot].get(_norm(pick.pos), 0) + 1
                )
                runs.add(pick.pos)
                pool.remove(pick)
            for p in pool:
                survived[p.name] += 1

        probs = {p.name: 1.0 for p in pool_all}
        for p in contenders:
            probs[p.name] = survived[p.name] / trials
        return probs

    def recommend(self, top: int = 12):
        self.season  # warm the cache before drawing, so the load notice can't
        # land in the middle of the table

        cur = self.on_the_clock
        # The pick after this one — passing `cur` stops it returning `cur` itself
        # when you're the one on the clock.
        nxt = self.next_pick(after=cur)
        if nxt is None:
            horizon = 0
            print(f"{BOLD}Pick {cur} — your last pick{OFF}\n")
        else:
            horizon = nxt - cur - 1
            print(
                f"{BOLD}Pick {cur} (round {self.current_round()}){OFF} — "
                f"next pick {nxt}, {horizon} picks away\n"
            )

        probs = self.survival(horizon)
        avail = self.available
        need = self.needs()

        # Expected best VORP still available at each position next time around.
        exp_next = {}
        for pos in ("QB", "RB", "WR", "TE"):
            pool = sorted(
                (p for p in avail if _norm(p.pos) == pos), key=lambda x: -x.vorp
            )
            ev, carry = 0.0, 1.0
            for p in pool[:25]:
                s = probs.get(p.name, 1.0)
                ev += carry * s * p.vorp
                carry *= 1 - s
                if carry < 0.001:
                    break
            exp_next[pos] = ev

        rows = []
        for p in avail:
            pos = _norm(p.pos)
            if pos in ("K", "DEF"):
                continue
            # What you give up by waiting on this position until your next pick.
            cost_to_wait = p.vorp - exp_next.get(pos, 0.0)
            weight = value_weight(pos, need, self.league)
            rows.append((cost_to_wait * weight, p, probs.get(p.name, 1.0), cost_to_wait))

        rows.sort(key=lambda r: -r[0])

        rounds_left = self.rounds - self.current_round() + 1
        must = need.get("K", 0) + need.get("DEF", 0)
        if rounds_left <= must:
            print(f"{RED}>> Take a {'K' if need.get('K') else 'DEF'} now — "
                  f"only {rounds_left} picks left and you still need {must}.{OFF}\n")

        print(f"{'PLAYER':<24} {'POS':<5} {'TIER':>4} {'VORP':>7} {'SURVIVE':>8} "
              f"{'WAIT COST':>10} {'LY':>6}")
        print("-" * 69)
        for _, p, surv, cost in rows[:top]:
            flag = ""
            if horizon > 0 and surv < 0.35:
                flag = f" {RED}<- gone if you wait{OFF}"
            elif horizon > 0 and surv > 0.80:
                flag = f" {GRN}<- safe to wait{OFF}"

            poe = self.poe_of(p)
            if poe is None:
                ly = f"{DIM}     -{OFF}" if self.season is None else f"{DIM}   new{OFF}"
            elif poe > 1.5:
                ly = f"{YEL}{poe:>+6.1f}{OFF}"   # rode 2025 luck, expect regression
            elif poe < -1.5:
                ly = f"{GRN}{poe:>+6.1f}{OFF}"   # unlucky 2025, positive regression
            else:
                ly = f"{poe:>+6.1f}"

            colour = CYA if need.get(_norm(p.pos), 0) > 0 else DIM
            print(
                f"{colour}{p.name:<24}{OFF} {_norm(p.pos) + str(p.pos_rank):<5} "
                f"{p.tier:>4} {p.vorp:>7.1f} {surv:>7.0%} {cost:>+10.1f} {ly}{flag}"
            )

        print(f"\n{DIM}WAIT COST = this player's value minus the value you'd expect "
              f"to still get\n             at this position at pick {nxt}. "
              f"Highest number is the pick.\n"
              f"LY        = 2025 points over expected per game. Positive outran "
              f"its usage\n             (fade it); negative underran it (expect a "
              f"partial bounce, not a full one).{OFF}")
        self.show_needs(inline=True)

    def show_board(self, pos: str | None = None, top: int = 20):
        avail = self.available
        if pos:
            avail = [p for p in avail if _norm(p.pos) == pos]
        avail = sorted(avail, key=lambda p: -p.vorp)[:top]
        print(f"{'PLAYER':<24} {'POS':<5} {'TIER':>4} {'PTS':>7} {'VORP':>7} {'ADP':>6}")
        print("-" * 56)
        for p in avail:
            print(
                f"{p.name:<24} {_norm(p.pos) + str(p.pos_rank):<5} {p.tier:>4} "
                f"{p.points:>7.1f} {p.vorp:>7.1f} {p.adp:>6.1f}"
            )

    def bye_load(self) -> dict[str, int]:
        """How many of your players share each bye week."""
        load: dict[str, int] = defaultdict(int)
        for p in self.my_roster:
            if p.bye and _norm(p.pos) not in ("K", "DEF"):
                load[p.bye] += 1
        return load

    def show_needs(self, inline: bool = False):
        need = self.needs()
        parts = [f"{k}×{v}" for k, v in need.items() if v > 0]
        label = "STILL NEED" if parts else "starters full — draft upside"
        print(f"\n{BOLD}{label}:{OFF} {' '.join(parts)}")

        # With five bench spots you can absorb one crowded bye, not two.
        heavy = sorted(
            ((wk, n) for wk, n in self.bye_load().items() if n >= 3),
            key=lambda kv: -kv[1],
        )
        if heavy:
            weeks = ", ".join(f"week {wk} ({n} players)" for wk, n in heavy)
            print(f"{YEL}BYE STACK:{OFF} {weeks}")

    def show_roster(self):
        roster = self.my_roster
        if not roster:
            print("(empty)")
        else:
            print(f"{'PLAYER':<24} {'POS':<5} {'PTS':>7} {'VORP':>7}")
            print("-" * 46)
            for p in sorted(roster, key=lambda x: (_norm(x.pos), -x.points)):
                print(f"{p.name:<24} {_norm(p.pos) + str(p.pos_rank):<5} {p.points:>7.1f} {p.vorp:>7.1f}")
        self.show_needs()

    # ---------- name matching ----------

    def find(self, query: str):
        q = query.strip().lower()
        if not q:
            return None
        avail = self.available
        exact = [p for p in avail if p.name.lower() == q]
        if exact:
            return exact[0]
        subs = [p for p in avail if q in p.name.lower()]
        if len(subs) == 1:
            return subs[0]
        if len(subs) > 1:
            # An exact surname beats a substring hit elsewhere in someone's name:
            # "henry" is Derrick Henry, not a three-way menu including Hunter
            # Henry and a receiver whose first name happens to contain it. The
            # chat front end already resolved this; the terminal is the one
            # running under a clock, so it needs it more.
            surname = [p for p in subs if _surname(p.name) == q]
            if len(surname) == 1:
                return surname[0]
            return self._disambiguate(subs, query)
        # Last-name / fuzzy fallback.
        names = {p.name.lower(): p for p in avail}
        close = difflib.get_close_matches(q, list(names), n=5, cutoff=0.6)
        if len(close) == 1:
            return names[close[0]]
        if close:
            return self._disambiguate([names[c] for c in close], query)

        taken = [p for p in self.board if p.name.lower().find(q) >= 0]
        if taken:
            print(f"{YEL}'{query}' is already off the board{OFF}")
        else:
            print(f"{YEL}no match for '{query}'{OFF}")
        return None

    def _disambiguate(self, cands, query, depth: int = 0):
        """Ask which player was meant, and never fall through silently.

        Two things a draft makes likely and the first version got wrong. You can
        answer with a fuller name instead of a number, because under a clock that
        is what fingers do. And backing out says so in yellow — a dropped pick
        shifts every pick number after it and quietly corrupts every survival
        estimate for the rest of the draft, which is not a thing to learn about
        four rounds later.
        """
        cands = sorted(cands, key=lambda p: p.adp)[:8]
        print(f"'{query}' matches several:")
        for i, p in enumerate(cands, 1):
            print(f"  {i}. {p.name} ({_norm(p.pos)}, {p.team}, ADP {p.adp:.0f})")
        try:
            choice = input("which? [number, or type more of the name] ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = ""
        if choice.isdigit() and 1 <= int(choice) <= len(cands):
            return cands[int(choice) - 1]
        if choice.lower() in COMMAND_WORDS:
            # You meant to be back at the main prompt. Searching the board for a
            # player called "go" would be a baffling thing to do about it.
            print(f"{YEL}cancelled — type the command again{OFF}")
            return None
        if choice and depth < 2:
            narrowed = [p for p in cands if choice.lower() in p.name.lower()]
            if len(narrowed) == 1:
                return narrowed[0]
            if narrowed:
                return self._disambiguate(narrowed, choice, depth + 1)
            # Not a narrowing of this list — treat it as a fresh name.
            return self.find(choice)
        print(f"{YEL}nothing recorded for '{query}' — pick {self.on_the_clock} "
              f"is still open{OFF}")
        return None


def main():
    league = load_league()
    board = build_board(league, load_players())
    d = Draft(league, board)

    if d.load() and d.picks:
        print(f"{DIM}resumed {len(d.picks)} picks from draft_state.json "
              f"(delete it to start fresh){OFF}")
    d.auto_advance()

    print(f"\n{BOLD}Draft assistant{OFF} — {d.teams} teams, slot "
          f"{league['my_draft_slot']}, {d.rounds} rounds")
    print(f"your picks: {', '.join(str(p) for p in d.my_picks)}")
    print(f"{DIM}type a name to mark it drafted, 'me <name>' for your pick, "
          f"'go' for advice, '?' for help{OFF}\n")

    pos_cmds = {"rb": "RB", "wr": "WR", "te": "TE", "qb": "QB", "k": "K", "def": "DEF"}

    while True:
        mine_next = d.on_the_clock in d.my_picks
        marker = f"{GRN}YOUR PICK{OFF}" if mine_next else "pick"
        try:
            raw = input(f"[{marker} {d.on_the_clock}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue

        cmd = raw.lower()
        if cmd in ("quit", "q", "exit"):
            break
        if cmd in ("?", "help", "h"):
            print(__doc__)
            continue
        if cmd == "undo":
            d.undo()
            continue
        if cmd in ("board", "b"):
            d.show_board()
            continue
        if cmd in pos_cmds:
            d.show_board(pos_cmds[cmd])
            continue
        if cmd in ("go", "t", "targets", "rec"):
            d.recommend()
            continue
        if cmd in ("roster", "r"):
            d.show_roster()
            continue
        if cmd.startswith("why "):
            if d.season is None:
                print(f"{YEL}needs 2025 data — run 'python3 fetch_data.py'{OFF}")
                continue
            from last_season import player_card

            player_card(d.season, d.board, raw[4:])
            continue
        if cmd == "picks":
            left = [
                f"{p}{' (keeper)' if p in d.keeper_picks else ''}"
                for p in d.my_picks
                if p >= d.on_the_clock
            ]
            print("remaining:", ", ".join(left) or "none")
            continue
        if cmd == "save":
            d.save()
            print(f"saved to {STATE_PATH}")
            continue

        mine = False
        if cmd.startswith("me ") or raw.startswith("+"):
            mine = True
            raw = raw[3:] if cmd.startswith("me ") else raw[1:]

        player = d.find(raw)
        if player is None:
            continue
        if mine and d.on_the_clock not in d.my_picks:
            print(f"{YEL}note: pick {d.on_the_clock} isn't one of yours{OFF}")
        elif not mine and d.on_the_clock in d.my_picks:
            # Forgetting "me" would drop the player from your roster tracking and
            # quietly corrupt every needs and wait-cost number after it.
            print(f"{YEL}note: pick {d.on_the_clock} IS yours — recording as "
                  f"your pick. Use 'undo' if that's wrong.{OFF}")
            mine = True
        d.record(player, mine)
        tag = f"{GRN}YOU{OFF}" if mine else "---"
        print(f"  {tag} pick {d.picks[-1]['pick']}: {player.name} "
              f"({_norm(player.pos)}, VORP {player.vorp:.1f})")

        if d.on_the_clock in d.my_picks:
            print(f"\n{BOLD}{GRN}>>> You're on the clock.{OFF}")
            d.recommend(top=10)


if __name__ == "__main__":
    sys.exit(main())
