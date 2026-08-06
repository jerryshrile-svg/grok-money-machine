"""Pre-draft sanity check. Run this the morning of, before anything else.

The tests in `test_toolkit.py` prove the code is right. This proves the *data* is
right, which is a different and equally unrecoverable problem: a duplicated
player, a keeper whose name no longer matches the feed, or a scoring change that
never got rebuilt will all produce a board that looks completely normal and is
quietly wrong.

Every check here exists because getting it wrong would cost real picks.

    python3 audit.py

Exit code is non-zero if anything needs attention, so it can gate a script.
"""

from __future__ import annotations

import collections
import csv
import os
import sys

from engine import HERE, build_board, check_scoring, load_league, load_players
from last_season import norm

DATA = os.path.join(HERE, "data")
RAW = os.path.join(DATA, "raw")


def _rows():
    with open(os.path.join(DATA, "projections.csv"), newline="") as fh:
        return list(csv.DictReader(fh))


def check_scoring_is_current(league, problems, notes):
    warning = check_scoring(league)
    if warning:
        problems.append(warning.replace("\n", " "))
    else:
        notes.append("scoring in league.json matches the built projections")


def check_no_duplicates(rows, problems, notes):
    """A duplicated player is draftable twice and double-counts in every sim."""
    counts = collections.Counter(norm(r["name"]) for r in rows)
    dupes = [n for n, c in counts.items() if c > 1]
    if dupes:
        problems.append(f"duplicate players in the board: {dupes}")
    else:
        notes.append(f"{len(rows)} players, no duplicates")


def check_keepers_resolve(league, board, problems, notes):
    """A keeper whose name drifted silently stops being held out of the pool."""
    names = {p.name for p in board}
    for k in league.get("keepers", []):
        if k["player"] not in names:
            problems.append(
                f"keeper '{k['player']}' is not on the board — check the spelling "
                "against data/projections.csv"
            )
        else:
            notes.append(f"keeper {k['player']} resolves, holds pick "
                         f"{k.get('pick_overall')}")
    for name in league.get("opponent_keepers", {}).get("known", []):
        if name not in names:
            problems.append(f"known opponent keeper '{name}' is not on the board")


def check_teams_resolve(board, league, problems, notes):
    """Every draftable player must map to playoff-schedule data."""
    try:
        import playoffs
    except ImportError:
        return
    opponents = playoffs.playoff_opponents(league)
    if not opponents:
        notes.append("no schedule downloaded — playoff tiebreaker unavailable")
        return
    allowed = playoffs.points_allowed(league["scoring"])
    diff = playoffs.difficulty(allowed, playoffs.league_average(allowed), opponents)

    pool = league["teams"] * league["rounds"]
    missing = sorted(
        {p.team for p in board[:pool]
         if p.pos not in ("K", "DST", "DEF") and playoffs.team(p.team) not in diff}
    )
    if missing:
        problems.append(f"draftable players on teams with no schedule match: {missing}")
    else:
        notes.append(f"all {len(opponents)} teams resolve to playoff-week data")


def check_byes(rows, league, problems, notes):
    pool = league["teams"] * league["rounds"]
    missing = [r["name"] for r in rows[:pool]
               if not r.get("bye") or r["bye"] == "NA"]
    if missing:
        notes.append(f"{len(missing)} draftable players have no bye listed "
                     f"(e.g. {missing[0]}) — cosmetic only, byes miss the playoffs")


def check_freshness(rows, problems, notes):
    """A stale consensus misses two weeks of camp injuries and depth-chart moves."""
    meta = os.path.join(DATA, "projections.meta.json")
    if not os.path.exists(meta):
        return
    import json
    from datetime import date

    scraped = json.load(open(meta)).get("scrape_date", "")
    if not scraped:
        return
    try:
        y, m, d = (int(x) for x in scraped.split("-"))
        age = (date.today() - date(y, m, d)).days
    except ValueError:
        return
    if age > 7:
        problems.append(
            f"consensus rankings are {age} days old (scraped {scraped}) — run "
            "'python3 fetch_data.py rankings && python3 build_projections.py'"
        )
    else:
        notes.append(f"consensus is {age} days old (scraped {scraped})")


def check_draft_slot(league, problems, notes):
    slot, teams = league["my_draft_slot"], league["teams"]
    if not 1 <= slot <= teams:
        problems.append(f"draft slot {slot} is outside 1..{teams}")
        return
    from engine import snake_picks

    picks = snake_picks(slot, teams, league["rounds"])
    notes.append(f"slot {slot} of {teams} — picks {picks[0]}, {picks[1]}, "
                 f"{picks[2]} ... {picks[-1]}")


def check_live_state(league, problems, notes):
    """A stale live_draft.json from a practice run would poison a real draft."""
    path = os.path.join(DATA, "live_draft.json")
    if not os.path.exists(path):
        notes.append("no draft in progress")
        return
    import json

    picks = json.load(open(path)).get("picks", [])
    if picks:
        problems.append(
            f"data/live_draft.json already holds {len(picks)} picks. If that is a "
            "practice run, clear it: python3 advise.py reset"
        )


def main() -> int:
    league = load_league()
    board = build_board(league, load_players())
    rows = _rows()

    problems: list[str] = []
    notes: list[str] = []

    check_scoring_is_current(league, problems, notes)
    check_no_duplicates(rows, problems, notes)
    check_keepers_resolve(league, board, problems, notes)
    check_teams_resolve(board, league, problems, notes)
    check_byes(rows, league, problems, notes)
    check_freshness(rows, problems, notes)
    check_draft_slot(league, problems, notes)
    check_live_state(league, problems, notes)

    for n in notes:
        print(f"  ok    {n}")
    if problems:
        print()
        for p in problems:
            print(f"  FIX   {p}")
        print(f"\n{len(problems)} thing(s) to sort out before drafting.")
        return 1
    print("\nBoard is clean. Good to draft.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
