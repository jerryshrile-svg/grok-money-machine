"""Draft advice from pasted picks — the chat-friendly front end.

`draft_day.py` is the fast path: you type picks into a terminal and it answers
instantly. This is for when you'd rather paste names into a chat and be told what
to do. Same board, same rule, same code — only the interface differs.

You paste picks **in draft order** and it works out who owns each one from the
snake, so there is nothing to mark as yours and no way to forget. Your keeper
fills its own slot. When the next pick is yours, it prints the recommendation.

    python3 advise.py add "Chase, Gibbs, Nacua"   # record picks, in order
    python3 advise.py status                       # board state, no changes
    python3 advise.py undo                         # take back the last pick
    python3 advise.py reset                        # start over

State lives in data/live_draft.json, which is committed rather than ignored, so
the draft survives this machine going away mid-round.
"""

from __future__ import annotations

import difflib
import os
import re
import sys

import draft_day
from engine import HERE, build_board, load_league, load_players
from opponent import value_weight

STATE = os.path.join(HERE, "data", "live_draft.json")

# Chat has no terminal colours; strip them so nothing renders as escape codes.
for _name in ("BOLD", "DIM", "RED", "GRN", "YEL", "CYA", "OFF"):
    setattr(draft_day, _name, "")


def resolve(draft, query: str):
    """Match a typed name against players still on the board.

    Returns (player, candidates). Ambiguity is reported rather than prompted for,
    because there is nobody at a keyboard to answer.
    """
    q = " ".join(query.strip().lower().split())
    if not q:
        return None, []
    avail = draft.available

    exact = [p for p in avail if p.name.lower() == q]
    if exact:
        return exact[0], []

    subs = [p for p in avail if q in p.name.lower()]
    if len(subs) == 1:
        return subs[0], []
    if len(subs) > 1:
        # Prefer an exact surname hit before declaring it ambiguous.
        surname = [p for p in subs if draft_day._surname(p.name) == q]
        if len(surname) == 1:
            return surname[0], []
        return None, sorted(subs, key=lambda p: p.adp)[:6]

    names = {p.name.lower(): p for p in avail}
    close = difflib.get_close_matches(q, list(names), n=6, cutoff=0.6)
    if len(close) == 1:
        return names[close[0]], []
    if close:
        return None, [names[c] for c in close]
    return None, []


def split_names(blob: str) -> list[str]:
    """Accept commas, newlines, semicolons or numbered lists."""
    parts = re.split(r"[,\n;]+", blob)
    out = []
    for part in parts:
        part = re.sub(r"^\s*\d+[.):]\s*", "", part).strip()
        if part:
            out.append(part)
    return out


def show_status(draft) -> None:
    league = draft.league
    nxt = draft.next_pick(after=draft.on_the_clock - 1)
    taken = len(draft.picks)
    print(f"{taken} picks recorded. On the clock: pick {draft.on_the_clock} "
          f"(round {draft.current_round()}).")
    if nxt and nxt != draft.on_the_clock:
        print(f"Your next pick is {nxt} — {nxt - draft.on_the_clock} picks away.")
    mine = draft.my_roster
    if mine:
        print("\nYour roster:")
        for p in sorted(mine, key=lambda x: (draft_day._norm(x.pos), -x.points)):
            print(f"  {draft_day._norm(p.pos) + str(p.pos_rank):<5} {p.name}")
    draft.show_needs()
    _ = league


def main() -> int:
    draft_day.STATE_PATH = STATE
    league = load_league()
    board = build_board(league, load_players())
    d = draft_day.Draft(league, board)
    d.load()
    d.auto_advance()
    # Warm the 2025 data before any table draws, so its load notice cannot land
    # in the middle of the recommendation.
    _ = d.season

    args = sys.argv[1:]
    cmd = args[0] if args else "status"

    if cmd == "reset":
        if os.path.exists(STATE):
            os.remove(STATE)
        print("draft state cleared.")
        return 0

    if cmd == "undo":
        d.undo()
        show_status(d)
        return 0

    if cmd == "add":
        blob = " ".join(args[1:])
        names = split_names(blob)
        if not names:
            print("nothing to add — pass names separated by commas")
            return 2

        for raw in names:
            if d.on_the_clock > league["teams"] * league["rounds"]:
                print("draft is complete.")
                break
            player, options = resolve(d, raw)
            if player is None:
                if options:
                    print(f"\n'{raw}' is ambiguous. Which one?")
                    for p in options:
                        print(f"  - {p.name} ({draft_day._norm(p.pos)}, "
                              f"{p.team}, consensus #{p.adp:.0f})")
                else:
                    print(f"\n'{raw}' matched nobody still on the board "
                          "(already drafted, or a spelling I don't have).")
                print("Nothing after that name was recorded. Re-send from there.")
                return 1
            pick_no = d.on_the_clock
            mine = pick_no in d.my_picks
            who = "YOU" if mine else " · "
            # Print before recording: recording may auto-fill a keeper slot and
            # announce it, which would otherwise appear above the pick that
            # caused it.
            print(f"{pick_no:>4} {who}  {player.name} "
                  f"({draft_day._norm(player.pos)}{player.pos_rank})")
            d.record(player, mine)

    print()
    if d.on_the_clock in d.my_picks and d.on_the_clock not in d.keeper_picks:
        print("=" * 62)
        print(f"YOU ARE ON THE CLOCK — pick {d.on_the_clock}")
        print("=" * 62)
        d.recommend(top=8)
        best = _top_choice(d)
        if best:
            print(f"\n>>> TAKE: {best.name} "
                  f"({draft_day._norm(best.pos)}{best.pos_rank}, "
                  f"consensus #{best.adp:.0f})")
    else:
        show_status(d)
    return 0


def _top_choice(draft):
    """Re-derive the single highest wait-cost pick for a one-line verdict."""
    nxt = draft.next_pick(after=draft.on_the_clock)
    horizon = (nxt - draft.on_the_clock - 1) if nxt else 0
    probs = draft.survival(horizon)
    need = draft.needs()

    exp_next = {}
    for pos in ("QB", "RB", "WR", "TE"):
        pool = sorted((p for p in draft.available if draft_day._norm(p.pos) == pos),
                      key=lambda x: -x.vorp)
        ev, carry = 0.0, 1.0
        for p in pool[:25]:
            s = probs.get(p.name, 1.0)
            ev += carry * s * p.vorp
            carry *= 1 - s
            if carry < 0.001:
                break
        exp_next[pos] = ev

    best, best_score = None, float("-inf")
    rounds_left = draft.rounds - draft.current_round() + 1
    must = need.get("K", 0) + need.get("DEF", 0)
    for p in draft.available:
        pos = draft_day._norm(p.pos)
        if pos in ("K", "DEF"):
            # Only forced at the very end, and then it is the whole answer.
            if rounds_left <= must:
                return min(
                    (q for q in draft.available
                     if draft_day._norm(q.pos) == ("K" if need.get("K") else "DEF")),
                    key=lambda q: q.adp, default=None,
                )
            continue
        weight = value_weight(pos, need, draft.league)
        score = (p.vorp - exp_next.get(pos, 0.0)) * weight
        if score > best_score:
            best, best_score = p, score
    return best


if __name__ == "__main__":
    raise SystemExit(main())
