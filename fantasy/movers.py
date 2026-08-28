"""What changed since the list your leaguemates are holding?

Your opponents are drafting off something printed. A magazine from July, a
cheat sheet exported last weekend, the rankings page as it looked whenever they
last opened it. You re-pull the consensus the morning of the draft, so for a
handful of players your board and theirs disagree — and every one of those
disagreements is a place where the room is wrong and you know it.

This is the only edge in the toolkit that comes from timing rather than method,
and it costs one command.

`build_projections.py` files a dated copy of every board it builds into
`data/snapshots/`. This diffs two of them and reports who moved, restricted to
players who are actually draftable, because a receiver going from ECR 340 to 300
is not information.

    python3 movers.py                  # newest snapshot vs the one before it
    python3 movers.py 2026-08-01       # newest vs a specific date
    python3 movers.py 2026-08-01 2026-08-14
"""

from __future__ import annotations

import csv
import os
import sys

from engine import HERE

SNAPS = os.path.join(HERE, "data", "snapshots")

POOL = 180      # overall consensus depth that anyone in an 8-team league drafts
MIN_MOVE = 6    # smaller than this is churn, not news
SHOW = 14


def available() -> list[str]:
    """Snapshot dates on disk, oldest first."""
    if not os.path.isdir(SNAPS):
        return []
    out = []
    for fn in os.listdir(SNAPS):
        if fn.startswith("board_") and fn.endswith(".csv"):
            out.append(fn[len("board_"):-len(".csv")])
    return sorted(out)


def load(stamp: str) -> dict[str, dict]:
    path = os.path.join(SNAPS, f"board_{stamp}.csv")
    rows = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                r["adp"] = float(r["adp"])
                r["points"] = float(r["points"])
            except (TypeError, ValueError):
                continue
            rows[r["name"]] = r
    return rows


def compare(old: dict, new: dict):
    """Movers, arrivals and departures between two boards."""
    moved, arrived, gone = [], [], []
    for name, n in new.items():
        if n["adp"] > POOL:
            continue
        o = old.get(name)
        if o is None:
            arrived.append(n)
            continue
        shift = o["adp"] - n["adp"]          # positive = moved up the board
        if abs(shift) >= MIN_MOVE:
            moved.append((shift, o, n))
    for name, o in old.items():
        if o["adp"] <= POOL and name not in new:
            gone.append(o)
    moved.sort(key=lambda t: -t[0])
    return moved, arrived, gone


def _line(shift, o, n):
    return (f"  {n['name']:<24} {n['pos']:<4} {n['team']:<4} "
            f"{o['adp']:>6.1f} -> {n['adp']:>6.1f}  {shift:>+6.1f}  "
            f"{n['points'] - o['points']:>+7.1f} pts")


def main() -> int:
    stamps = available()
    if len(stamps) < 2:
        print("Need two board snapshots to compare, and there "
              f"{'is 1' if stamps else 'are none'} on disk.")
        print("\nSnapshots are filed automatically every time you run")
        print("  python3 build_projections.py")
        print("so re-pull and rebuild now, then again on draft morning:")
        print("  python3 fetch_data.py rankings && python3 build_projections.py")
        return 1

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(args) >= 2:
        old_s, new_s = args[0], args[1]
    elif len(args) == 1:
        old_s, new_s = args[0], stamps[-1]
    else:
        old_s, new_s = stamps[-2], stamps[-1]

    for s in (old_s, new_s):
        if s not in stamps:
            print(f"no snapshot for {s}. Have: {', '.join(stamps)}")
            return 2

    old, new = load(old_s), load(new_s)
    moved, arrived, gone = compare(old, new)

    print(f"\nBoard movement, {old_s} -> {new_s}")
    print(f"Top {POOL} consensus only; moves of at least {MIN_MOVE} places.\n")

    if not moved and not arrived and not gone:
        print("  Nothing moved. Your board and a week-old one agree.")
        return 0

    head = (f"  {'PLAYER':<24} {'POS':<4} {'TM':<4} {'WAS':>6}    {'NOW':>6}  "
            f"{'MOVE':>6}  {'VALUE':>11}")

    if moved:
        ups = [m for m in moved if m[0] > 0][:SHOW]
        downs = [m for m in moved if m[0] < 0][-SHOW:][::-1]
        if ups:
            print("  RISING — the room is still pricing these too cheaply")
            print(head)
            for shift, o, n in ups:
                print(_line(shift, o, n))
            print()
        if downs:
            print("  FALLING — the room will still be paying yesterday's price")
            print(head)
            for shift, o, n in downs:
                print(_line(shift, o, n))
            print()

    if arrived:
        arrived.sort(key=lambda r: r["adp"])
        print("  NEW to the draftable range")
        for r in arrived[:SHOW]:
            print(f"  {r['name']:<24} {r['pos']:<4} {r['team']:<4} "
                  f"now {r['adp']:>6.1f}")
        print()

    if gone:
        gone.sort(key=lambda r: r["adp"])
        print("  DROPPED out of the draftable range")
        for r in gone[:SHOW]:
            print(f"  {r['name']:<24} {r['pos']:<4} {r['team']:<4} "
                  f"was {r['adp']:>6.1f}")
        print()

    print("A player who moved a long way in the last week usually moved for a")
    print("reason the market has priced and your leaguemates have not read.")
    print("Rising players are the ones to reach for; falling ones are the traps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
