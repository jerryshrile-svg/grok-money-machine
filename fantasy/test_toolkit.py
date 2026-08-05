"""Tests for the parts that would silently ruin a draft.

Draft day is unrecoverable — a wrong pick number or a keeper the model thinks is
available costs a pick you never get back, under a 90-second clock. Every bug
found so far in this toolkit was caught by eyeballing output, which is not a
plan. These cover the invariants instead.

    python3 -m unittest test_toolkit -v
    python3 test_toolkit.py
"""

from __future__ import annotations

import os
import random
import unittest
from collections import defaultdict

import draft_day
import engine
from last_season import norm as norm_name
import opponent
import sim
from engine import Player

LEAGUE = {
    "teams": 8,
    "my_draft_slot": 6,
    "rounds": 14,
    "roster": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1, "BN": 5},
    "flex_eligible": ["RB", "WR", "TE"],
    "scoring": {
        "pass_yd": 0.04, "pass_td": 4.0, "pass_int": -2.0,
        "rush_yd": 0.1, "rush_td": 6.0,
        "rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0,
        "fumble_lost": -2.0, "two_pt": 2.0,
    },
    "keepers": [{"team": "ME", "player": "Keeper Back", "round": 1, "pick_overall": 6}],
    "opponent_keepers": {"known": [], "unknown_count": 0, "round": 1, "pool_top_n": 36},
}


def make_board(n_per_pos=40):
    """Synthetic board with a clean, monotonic value curve per position."""
    players = []
    adp = 1.0
    for i in range(n_per_pos):
        for pos, base in (("RB", 300), ("WR", 290), ("QB", 380), ("TE", 200)):
            players.append(
                Player(
                    name=f"{pos} Player {i + 1}",
                    pos=pos,
                    team="XX",
                    adp=adp,
                    points=base - i * 5.0,
                )
            )
            adp += 1
    for i in range(10):
        players.append(Player(name=f"K Player {i+1}", pos="K", team="XX",
                              adp=400 + i, points=130 - i))
        players.append(Player(name=f"DST Player {i+1}", pos="DST", team="XX",
                              adp=420 + i, points=120 - i))
    # The keeper the league config refers to.
    players.append(Player(name="Keeper Back", pos="RB", team="XX", adp=2.0, points=310.0))
    return engine.build_board(LEAGUE, players)


class SnakeMath(unittest.TestCase):
    def test_known_slot(self):
        self.assertEqual(
            engine.snake_picks(6, 8, 4), [6, 11, 22, 27]
        )

    def test_slot_for_pick_inverts_snake_picks(self):
        teams, rounds = 8, 14
        for slot in range(1, teams + 1):
            for pick in engine.snake_picks(slot, teams, rounds):
                self.assertEqual(engine.slot_for_pick(pick, teams), slot)

    def test_every_pick_belongs_to_exactly_one_slot(self):
        teams, rounds = 8, 14
        owned = defaultdict(list)
        for slot in range(1, teams + 1):
            for pick in engine.snake_picks(slot, teams, rounds):
                owned[pick].append(slot)
        self.assertEqual(sorted(owned), list(range(1, teams * rounds + 1)))
        for pick, slots in owned.items():
            self.assertEqual(len(slots), 1, f"pick {pick} owned by {slots}")


class ReplacementAndValue(unittest.TestCase):
    def setUp(self):
        self.board = make_board()

    def test_replacement_is_deeper_than_dedicated_starters(self):
        """Flex demand must push RB/WR baselines past the pure starter count."""
        levels = engine.replacement_levels(self.board, LEAGUE)
        rbs = sorted((p for p in self.board if p.pos == "RB"), key=lambda p: -p.points)
        # 2 RB x 8 teams = 16 dedicated; flex must consume at least one more.
        self.assertLess(levels["RB"], rbs[15].points)

    def test_qb_baseline_reflects_eight_starters(self):
        levels = engine.replacement_levels(self.board, LEAGUE)
        qbs = sorted((p for p in self.board if p.pos == "QB"), key=lambda p: -p.points)
        self.assertEqual(levels["QB"], qbs[8].points)

    def test_kickers_and_defenses_have_no_value(self):
        for p in self.board:
            if p.pos in ("K", "DST", "DEF"):
                self.assertEqual(p.vorp, 0.0)

    def test_tiers_never_improve_as_value_falls(self):
        by_pos = defaultdict(list)
        for p in self.board:
            by_pos[p.pos].append(p)
        for pos, pool in by_pos.items():
            pool.sort(key=lambda p: -p.vorp)
            for a, b in zip(pool, pool[1:]):
                self.assertLessEqual(a.tier, b.tier, f"{pos}: {a.name} -> {b.name}")

    def test_metadata_columns_are_not_scored(self):
        """A bye week or yahoo_id must never be treated as a scoring stat."""
        p = Player(name="X", pos="RB", team="XX", adp=1.0)
        p.stats = {"bye": 9.0, "yahoo_id": 12345.0}
        self.assertEqual(engine.score(p, LEAGUE["scoring"]), 0.0)


class Lineup(unittest.TestCase):
    def test_flex_takes_best_leftover(self):
        roster = [
            Player(name="qb", pos="QB", team="X", adp=1, points=300),
            Player(name="rb1", pos="RB", team="X", adp=2, points=200),
            Player(name="rb2", pos="RB", team="X", adp=3, points=190),
            Player(name="rb3", pos="RB", team="X", adp=4, points=180),
            Player(name="wr1", pos="WR", team="X", adp=5, points=150),
            Player(name="wr2", pos="WR", team="X", adp=6, points=140),
            Player(name="te1", pos="TE", team="X", adp=7, points=100),
        ]
        # 300 + (200+190) + (150+140) + 100 + flex 180
        self.assertAlmostEqual(sim.starting_lineup_points(roster, LEAGUE), 1260.0)

    def test_incomplete_roster_does_not_crash(self):
        roster = [Player(name="qb", pos="QB", team="X", adp=1, points=300)]
        self.assertAlmostEqual(sim.starting_lineup_points(roster, LEAGUE), 300.0)


class OpponentModel(unittest.TestCase):
    def setUp(self):
        self.board = make_board()

    def _full_draft(self, seed=0):
        rng = random.Random(seed)
        pool = [p for p in self.board if p.name != "Keeper Back"]
        counts = defaultdict(lambda: defaultdict(int))
        runs = opponent.RunTracker()
        picked = []
        for rnd in range(1, LEAGUE["rounds"] + 1):
            for slot in range(1, LEAGUE["teams"] + 1):
                pick = opponent.choose(pool, counts[slot], rnd, LEAGUE, rng, runs)
                self.assertIsNotNone(pick)
                pos = opponent.norm_pos(pick.pos)
                counts[slot][pos] += 1
                runs.add(pos)
                pool.remove(pick)
                picked.append((rnd, slot, pick))
        return counts, picked

    def test_never_exceeds_position_caps(self):
        counts, _ = self._full_draft()
        for slot, c in counts.items():
            for pos, cap in opponent.POS_CAP.items():
                self.assertLessEqual(c.get(pos, 0), cap, f"slot {slot} {pos}")

    def test_every_team_fills_its_starting_lineup(self):
        """The old model left all eight teams without a kicker or defense."""
        counts, _ = self._full_draft()
        for slot, c in counts.items():
            need = opponent.starter_needs(c, LEAGUE)
            self.assertEqual(
                sum(need.values()), 0, f"slot {slot} finished with holes: {need}"
            )

    def test_kickers_and_defenses_go_late(self):
        _, picked = self._full_draft()
        for rnd, _slot, p in picked:
            if opponent.norm_pos(p.pos) in ("K", "DEF"):
                self.assertGreaterEqual(
                    rnd, LEAGUE["rounds"] - opponent.KDEF_LAST_ROUNDS,
                    f"{p.name} went in round {rnd}",
                )

    def test_no_player_drafted_twice(self):
        _, picked = self._full_draft()
        names = [p.name for _, _, p in picked]
        self.assertEqual(len(names), len(set(names)))

    def test_run_tracker_respects_window(self):
        t = opponent.RunTracker(window=3)
        for pos in ("RB", "RB", "WR", "TE"):
            t.add(pos)
        self.assertEqual(t.pressure("RB"), 1)
        self.assertEqual(len(t.recent), 3)

    def test_run_pressure_is_capped(self):
        """Uncapped pressure compounds into a runaway run on one position."""
        t = opponent.RunTracker(window=12)
        for _ in range(12):
            t.add("WR")
        self.assertEqual(t.pressure("WR"), opponent.RUN_CAP)

    def test_elite_players_do_not_survive_the_first_round(self):
        """A top-three consensus player must not routinely last nine picks."""
        board = make_board()
        survived = 0
        trials = 60
        best = min(board, key=lambda p: p.adp)
        for t in range(trials):
            rng = random.Random(t)
            pool = [p for p in board if p.name != "Keeper Back"]
            counts = defaultdict(lambda: defaultdict(int))
            runs = opponent.RunTracker()
            for slot in range(1, 10):
                pick = opponent.choose(pool, counts[slot], 1, LEAGUE, rng, runs)
                counts[slot][opponent.norm_pos(pick.pos)] += 1
                runs.add(pick.pos)
                pool.remove(pick)
            if best in pool:
                survived += 1
        self.assertLess(survived / trials, 0.25, f"{best.name} survived too often")

    def test_flex_need_comes_from_surplus(self):
        need = opponent.starter_needs({"RB": 2, "WR": 2, "TE": 1, "QB": 1}, LEAGUE)
        self.assertEqual(need["FLEX"], 1)
        need = opponent.starter_needs({"RB": 3, "WR": 2, "TE": 1, "QB": 1}, LEAGUE)
        self.assertEqual(need["FLEX"], 0)


class FullDraftIntegrity(unittest.TestCase):
    def setUp(self):
        self.board = make_board()

    def test_my_roster_size_and_uniqueness(self):
        rng = random.Random(3)
        mine = sim.run_draft(self.board, LEAGUE, ["WAIT"] * 14, rng)
        self.assertEqual(len(mine), LEAGUE["rounds"])
        self.assertEqual(len({p.name for p in mine}), LEAGUE["rounds"])

    def test_keeper_is_on_my_roster_and_never_available(self):
        rng = random.Random(4)
        mine = sim.run_draft(self.board, LEAGUE, ["WAIT"] * 14, rng)
        self.assertIn("Keeper Back", {p.name for p in mine})

    def test_wait_strategy_fills_a_legal_lineup(self):
        rng = random.Random(5)
        mine = sim.run_draft(self.board, LEAGUE, ["WAIT"] * 14, rng)
        counts = defaultdict(int)
        for p in mine:
            counts[opponent.norm_pos(p.pos)] += 1
        need = opponent.starter_needs(counts, LEAGUE)
        self.assertEqual(sum(need.values()), 0, f"holes left: {need}")

    def test_opponent_keepers_consume_picks_and_players(self):
        rng = random.Random(6)
        pool = [p for p in self.board if p.name != "Keeper Back"]
        kept = sim.opponent_keepers(pool, LEAGUE, rng, count=7)
        self.assertEqual(len(kept), 7)
        # One per opposing team, never on my slot.
        slots = {engine.slot_for_pick(pick, LEAGUE["teams"]) for pick in kept}
        self.assertEqual(len(slots), 7)
        self.assertNotIn(LEAGUE["my_draft_slot"], slots)

    def test_more_keepers_never_crashes_the_draft(self):
        for count in range(0, LEAGUE["teams"]):
            rng = random.Random(7 + count)
            mine = sim.run_draft(
                self.board, LEAGUE, ["WAIT"] * 14, rng, keeper_count=count
            )
            self.assertEqual(len(mine), LEAGUE["rounds"], f"count={count}")


class LiveAssistant(unittest.TestCase):
    def setUp(self):
        self.board = make_board()
        self.d = draft_day.Draft(LEAGUE, self.board)
        draft_day.STATE_PATH = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".test_state.json"
        )

    def tearDown(self):
        if os.path.exists(draft_day.STATE_PATH):
            os.remove(draft_day.STATE_PATH)

    def test_keeper_never_appears_available(self):
        self.assertNotIn("Keeper Back", {p.name for p in self.d.available})

    def test_keeper_auto_advances_and_counts_as_mine(self):
        for i in range(5):
            self.d.record(self.d.available[i], mine=False)
        # Pick 6 is the keeper slot; it should fill itself.
        self.assertEqual(self.d.on_the_clock, 7)
        self.assertIn("Keeper Back", {p.name for p in self.d.my_roster})

    def test_next_pick_skips_the_keeper_slot(self):
        self.assertEqual(self.d.next_pick(after=1), 11)

    def test_next_pick_after_current_is_not_current(self):
        # Nine recorded picks plus the auto-filled keeper at 6 puts us on 11.
        for i in range(9):
            self.d.record(self.d.available[i], mine=False)
        self.assertEqual(self.d.on_the_clock, 11)
        self.assertEqual(self.d.next_pick(after=11), 22)

    def test_undo_restores_availability(self):
        target = self.d.available[0]
        self.d.record(target, mine=False)
        self.assertNotIn(target.name, {p.name for p in self.d.available})
        self.d.undo()
        self.assertIn(target.name, {p.name for p in self.d.available})

    def test_opponent_rosters_exclude_me_and_track_positions(self):
        for i in range(10):
            self.d.record(self.d.available[i], mine=False)
        rosters = self.d.opponent_rosters()
        total = sum(sum(c.values()) for c in rosters.values())
        # Ownership follows the snake, not the `mine` flag: both pick 6 (keeper)
        # and pick 11 fall on my slot, so both are excluded.
        mine_by_slot = sum(
            1 for e in self.d.picks
            if engine.slot_for_pick(e["pick"], LEAGUE["teams"])
            == LEAGUE["my_draft_slot"]
        )
        self.assertEqual(total, len(self.d.picks) - mine_by_slot)
        self.assertEqual(mine_by_slot, 2)

    def test_survival_probabilities_are_valid(self):
        for i in range(10):
            self.d.record(self.d.available[i], mine=False)
        probs = self.d.survival(horizon=10, trials=40)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in probs.values()))

    def test_survival_falls_as_the_wait_grows(self):
        for i in range(10):
            self.d.record(self.d.available[i], mine=False)
        best = max(self.d.available, key=lambda p: p.vorp).name
        short = self.d.survival(horizon=2, trials=60)[best]
        long = self.d.survival(horizon=12, trials=60)[best]
        self.assertGreaterEqual(short, long)

    def test_missing_season_data_does_not_break_recommendations(self):
        """The 2025 column is optional; a missing file must not stop the draft."""
        import last_season

        original = last_season.RAW
        last_season.RAW = "/nonexistent/path"
        try:
            d = draft_day.Draft(LEAGUE, self.board)
            d._season = None
            self.assertIsNone(d.season)
            self.assertIsNone(d.poe_of(self.board[0]))
            d.recommend(top=3)  # must not raise
        finally:
            last_season.RAW = original

    def test_needs_start_at_full_lineup_minus_keeper(self):
        need = self.d.needs()
        self.assertEqual(need["QB"], 1)
        self.assertEqual(need["RB"], 2)  # keeper not yet auto-advanced


class PlayoffSchedule(unittest.TestCase):
    """Only runs when the schedule has been fetched."""

    def setUp(self):
        import playoffs

        self.playoffs = playoffs
        if not os.path.exists(os.path.join(playoffs.RAW, "schedule_2026.csv")):
            self.skipTest("run: python3 fetch_data.py schedule")
        self.league = engine.load_league()
        self.opponents = playoffs.playoff_opponents(self.league)

    def test_every_team_has_three_playoff_week_opponents(self):
        self.assertEqual(len(self.opponents), 32)
        for tm, opps in self.opponents.items():
            self.assertEqual(len(opps), 3, f"{tm}: {opps}")

    def test_playoff_weeks_match_the_league_calendar(self):
        """Week 17 must be the week that ends on the stated playoff end date."""
        weeks = self.playoffs.playoff_weeks(self.league)
        self.assertEqual(weeks, (15, 16, 17))
        path = os.path.join(self.playoffs.RAW, "schedule_2026.csv")
        import csv as _csv

        last = max(
            r["gameday"]
            for r in _csv.DictReader(open(path))
            if r["season"] == "2026" and int(r["week"]) == weeks[-1]
        )
        self.assertEqual(last, "2027-01-04")

    def test_no_byes_during_the_playoffs(self):
        """A bye in the championship week would be a silent disaster."""
        import collections as _c
        import csv as _csv

        path = os.path.join(self.playoffs.RAW, "schedule_2026.csv")
        playing = _c.defaultdict(set)
        for r in _csv.DictReader(open(path)):
            if r["season"] != "2026":
                continue
            playing[int(r["week"])].update([r["home_team"], r["away_team"]])
        teams = set().union(*playing.values())
        for wk in self.playoffs.playoff_weeks(self.league):
            self.assertEqual(teams - playing[wk], set(), f"byes in week {wk}")

    def test_nobody_plays_themselves(self):
        for tm, opps in self.opponents.items():
            self.assertNotIn(tm, opps)

    def test_difficulty_is_centred_on_the_league_average(self):
        allowed = self.playoffs.points_allowed(self.league["scoring"])
        avg = self.playoffs.league_average(allowed)
        diff = self.playoffs.difficulty(allowed, avg, self.opponents)
        for pos in self.playoffs.SKILL:
            vals = [d[pos] for d in diff.values()]
            self.assertAlmostEqual(sum(vals) / len(vals), 0.0, delta=0.6)


class Backtest(unittest.TestCase):
    """Only runs when the historical inputs are present."""

    def setUp(self):
        import backtest

        self.bt = backtest
        if not os.path.exists(os.path.join(backtest.HIST, "ecr_2024.csv")):
            self.skipTest("historical rankings not extracted")
        if not os.path.exists(os.path.join(backtest.RAW, "stats_2021.csv")):
            self.skipTest("historical stats not fetched")
        self.league = engine.load_league()

    def test_points_curve_honours_its_season_window(self):
        """If the window were ignored, the backtest would be scoring itself."""
        from build_projections import points_curve

        early = points_curve(self.league["scoring"], range(2018, 2021))
        late = points_curve(self.league["scoring"], range(2022, 2025))
        self.assertNotEqual(early["RB"][:10], late["RB"][:10])

    def test_board_for_a_season_uses_only_prior_results(self):
        """Rebuilding with a deliberately wrong window must change the board."""
        from build_projections import points_curve

        real = points_curve(self.league["scoring"], range(2021, 2024))
        shifted = points_curve(self.league["scoring"], range(2022, 2025))
        self.assertNotEqual(real["WR"][:5], shifted["WR"][:5])

    def test_unplayed_roster_scores_zero(self):
        roster = [Player(name="Nobody At All", pos="RB", team="XX", adp=1, points=200)]
        self.assertEqual(self.bt.score_roster(roster, {1: {}}, LEAGUE), 0.0)

    def test_lineup_cannot_start_more_than_the_slots_allow(self):
        roster = [
            Player(name=f"RB {i}", pos="RB", team="X", adp=i, points=300 - i)
            for i in range(1, 11)
        ]
        week = {norm_name(p.name): 10.0 for p in roster}
        # 2 RB + 1 FLEX = 3 startable, at 10 points each, for one week.
        self.assertEqual(self.bt.score_roster(roster, {1: week}, LEAGUE), 30.0)


class RealDataSmoke(unittest.TestCase):
    """Only runs when projections have been built."""

    def setUp(self):
        path = os.path.join(engine.HERE, "data", "projections.csv")
        if not os.path.exists(path):
            self.skipTest("run fetch_data.py && build_projections.py first")
        self.league = engine.load_league()
        self.board = engine.build_board(self.league, engine.load_players())

    def test_board_is_populated_and_sorted(self):
        self.assertGreater(len(self.board), 300)
        vorps = [p.vorp for p in self.board]
        self.assertEqual(vorps, sorted(vorps, reverse=True))

    def test_configured_keeper_exists_on_the_board(self):
        """A typo here would silently un-keep your first-round pick."""
        names = {p.name for p in self.board}
        for k in self.league.get("keepers", []):
            self.assertIn(k["player"], names)

    def test_scoring_matches_the_projections_on_disk(self):
        """Editing scoring without rebuilding silently changes nothing."""
        warning = engine.check_scoring(self.league)
        self.assertIsNone(warning, warning)

    def test_scoring_mismatch_is_detected(self):
        import copy

        bad = copy.deepcopy(self.league)
        bad["scoring"]["pass_td"] = bad["scoring"]["pass_td"] + 2
        self.assertIsNotNone(engine.check_scoring(bad))

    def test_every_position_has_a_replacement_level(self):
        levels = engine.replacement_levels(self.board, self.league)
        for pos in ("QB", "RB", "WR", "TE"):
            self.assertIn(pos, levels)
            self.assertGreater(levels[pos], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
