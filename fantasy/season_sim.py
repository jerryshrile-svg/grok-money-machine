"""Simulate the season 10,000 times and see who actually wins.

Projections rank teams. They do not tell you who wins a league, because a
14-week head-to-head season plus a 6-team bracket is mostly variance. The
best roster on paper wins the title far less often than people assume, and
the only way to know how much less is to play the season out repeatedly.

Everything here is bootstrapped from real weekly data rather than assumed:

  WEEKLY SPREAD   For each position, the distribution of (a player's week
                  score / his own per-game average), taken from every 2024
                  and 2025 player-week with real volume. That distribution
                  is stable across both seasons and strongly right-skewed --
                  a receiver's median week is 0.90x his average while his
                  90th percentile is 1.9x. Sampling from the real shape
                  matters, because a normal distribution would badly
                  understate how often a starter posts a dud.

  ABSENCE         How often a rostered starter simply isn't there that week,
                  measured the same way: 13% for backs, 14-16% for receivers,
                  18% for quarterbacks. This is what makes bench depth worth
                  anything, so it can't be left out.

Kickers and defenses are excluded for every team equally -- I never captured
kickers from the rosters, and both positions are near-constant across teams.

    python3 season_sim.py            # 10,000 seasons
    python3 season_sim.py 2000       # faster
"""
from __future__ import annotations

import json, os, random, statistics, sys
from collections import defaultdict

import backtest
from engine import HERE, load_league, load_players, build_board
from last_season import norm

ME = "Bijan MUSTAAAAAAAADD (you)"
SAMPLE_SEASONS = (2024, 2025)
POOL_DRAWS = 20000     # per-team weekly-score distributions, precomputed once
PLAYOFF_TEAMS = 6
BYES = 2


def norm_pos(p):
    return "DEF" if p in ("DST", "D/ST") else p


def empirical(league):
    """Per-position weekly multiplier pools and absence rates, from real data."""
    import csv
    pos_of = {}
    for r in csv.DictReader(open(os.path.join(HERE, "data", "raw", "stats_2025.csv"),
                                 newline="")):
        if r.get("season_type") != "REG":
            continue
        pos_of[norm(r.get("player_display_name") or "")] = (r.get("position") or "").upper()

    mult = defaultdict(list)
    absent = defaultdict(lambda: [0, 0])
    for season in SAMPLE_SEASONS:
        actuals = backtest.weekly_actuals(season, league["scoring"])
        tot, games = defaultdict(float), defaultdict(int)
        for wk, week in actuals.items():
            for n, p in week.items():
                tot[n] += p; games[n] += 1
        ppg = {n: tot[n] / games[n] for n in tot
               if games[n] >= 10 and tot[n] / games[n] >= 6}
        for n, avg in ppg.items():
            pos = pos_of.get(n)
            if pos not in ("QB", "RB", "WR", "TE"):
                continue
            for wk in range(1, 18):
                got = actuals.get(wk, {}).get(n)
                absent[pos][1] += 1
                if got is None:
                    absent[pos][0] += 1
                else:
                    mult[pos].append(got / avg)
    rates = {p: absent[p][0] / absent[p][1] for p in absent}
    return dict(mult), rates


def load_teams(league, board):
    by = {norm(p.name): p for p in board}
    rosters = json.load(open(os.path.join(HERE, "data", "league_rosters.json")))
    out = {}
    for name, r in rosters.items():
        players = []
        for n in r["starters"] + r.get("bench", []):
            p = by.get(norm(n))
            if p and norm_pos(p.pos) in ("QB", "RB", "WR", "TE"):
                players.append((norm_pos(p.pos), p.points / 17.0))
        out[name] = players
    return out


def week_score(players, mult, rates, repl, rng):
    """One team's score for one week: who plays, then best legal lineup.

    An unfilled slot is streamed off waivers at replacement level rather than
    scored as zero. Without that the model punishes a one-quarterback roster
    for all eighteen percent of weeks his starter is out, when in reality you
    pick somebody up -- and in this league the best free quarterback is
    comfortably above replacement. Leaving it out made thin rosters look far
    worse than they are.
    """
    live = defaultdict(list)
    for pos, ppg in players:
        if rng.random() < rates.get(pos, 0.15):
            continue                      # out this week
        pool = mult[pos]
        live[pos].append(ppg * pool[rng.randrange(len(pool))])
    total, used = 0.0, []
    for pos, cnt in (("QB", 1), ("RB", 2), ("WR", 2), ("TE", 1)):
        s = sorted(live[pos], reverse=True)
        total += sum(s[:cnt])
        for _ in range(cnt - len(s[:cnt])):          # slot left empty
            pool = mult[pos]
            total += repl[pos] * pool[rng.randrange(len(pool))]
        used.extend(s[cnt:])
    flex = sorted(used, reverse=True)     # RB/WR/TE leftovers
    if flex:
        total += flex[0]
    else:
        pool = mult["WR"]
        total += repl["WR"] * pool[rng.randrange(len(pool))]
    return total


def replacement_per_game(league, board):
    """Waiver-wire quality per position, per game."""
    from engine import replacement_levels
    lv = replacement_levels(board, league)
    return {p: lv.get(p, 120.0) / 17.0 for p in ("QB", "RB", "WR", "TE")}


def build_pools(teams, mult, rates, repl, rng, draws):
    """Precompute each team's weekly-score distribution once, then resample.

    Team-weeks are independent in this model, so drawing from a precomputed
    distribution is equivalent to re-simulating every lineup and roughly a
    hundred times faster.
    """
    return {name: sorted(week_score(pl, mult, rates, repl, rng) for _ in range(draws))
            for name, pl in teams.items()}


def load_schedule(league):
    sched = json.load(open(os.path.join(HERE, "data", "league_schedule.json")))
    last = int(league.get("regular_season_last_week", 14))
    return [sched[str(w)] for w in range(1, last + 1) if str(w) in sched]


def simulate(pools, schedule, names, rng):
    """One season: 14 weeks head-to-head, then a 6-team bracket."""
    wins = dict.fromkeys(names, 0)
    pts = dict.fromkeys(names, 0.0)
    for games in schedule:
        drawn = {}
        for a, b in games:
            for t in (a, b):
                if t not in drawn:
                    pool = pools[t]
                    drawn[t] = pool[rng.randrange(len(pool))]
            pts[a] += drawn[a]; pts[b] += drawn[b]
            if drawn[a] > drawn[b]:
                wins[a] += 1
            elif drawn[b] > drawn[a]:
                wins[b] += 1
            else:
                wins[a] += 0.5; wins[b] += 0.5
    seeds = sorted(names, key=lambda t: (-wins[t], -pts[t]))
    field = seeds[:PLAYOFF_TEAMS]

    def play(x, y):
        px = pools[x][rng.randrange(len(pools[x]))]
        py = pools[y][rng.randrange(len(pools[y]))]
        return x if px >= py else y

    # Week 15: seeds 3v6 and 4v5. Seeds 1-2 have byes.
    qf = [play(field[2], field[5]), play(field[3], field[4])]
    # Week 16 semis: 1 v lowest surviving seed, 2 v the other.
    qf.sort(key=lambda t: field.index(t))
    sf = [play(field[0], qf[1]), play(field[1], qf[0])]
    champ = play(sf[0], sf[1])
    return wins, pts, seeds, field, champ


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10000
    league = load_league()
    board = build_board(league, load_players())
    mult, rates = empirical(league)
    teams = load_teams(league, board)
    schedule = load_schedule(league)
    names = list(teams)

    rng = random.Random(20260815)
    print(f"Bootstrapping weekly distributions from {len(SAMPLE_SEASONS)} real "
          f"seasons ({sum(len(v) for v in mult.values()):,} player-weeks)...")
    repl = replacement_per_game(league, board)
    pools = build_pools(teams, mult, rates, repl, rng, POOL_DRAWS)

    print(f"Simulating {n:,} seasons over {len(schedule)} weeks + playoffs...\n")
    titles = dict.fromkeys(names, 0)
    made = dict.fromkeys(names, 0)
    byes = dict.fromkeys(names, 0)
    finals = dict.fromkeys(names, 0)
    top = dict.fromkeys(names, 0)
    winsum = defaultdict(float)
    ptsum = defaultdict(float)

    for _ in range(n):
        wins, pts, seeds, field, champ = simulate(pools, schedule, names, rng)
        titles[champ] += 1
        for t in field:
            made[t] += 1
        for t in seeds[:BYES]:
            byes[t] += 1
        top[seeds[0]] += 1
        for t in names:
            winsum[t] += wins[t]; ptsum[t] += pts[t]

    print(f"{'TEAM':<34}{'TITLE':>7}{'PLAYOFF':>9}{'BYE':>7}{'1 SEED':>8}"
          f"{'AVG W':>7}{'AVG PTS':>9}")
    print("-" * 82)
    for t in sorted(names, key=lambda t: -titles[t]):
        star = " *" if t == ME else ""
        print(f"{t:<34}{titles[t]/n:>6.1%}{made[t]/n:>9.1%}{byes[t]/n:>7.1%}"
              f"{top[t]/n:>8.1%}{winsum[t]/n:>7.1f}{ptsum[t]/n:>9.0f}{star}")

    print(f"\nMost likely champion wins {max(titles.values())/n:.1%} of the time.")
    print("A perfectly balanced 8-team league would be 12.5% each.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
