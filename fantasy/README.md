# Fantasy Draft Toolkit

Draft tooling calibrated to one specific league: 8 teams, 0.5 PPR, snake, pick 6,
Bijan Robinson kept in round 1. Pure Python stdlib — no install step, no API keys.

See [PLAYBOOK.md](PLAYBOOK.md) for the strategy reasoning and the build roadmap.

## Quick start

```bash
cd fantasy

python3 fetch_data.py          # download free public data (~37 MB, one command)
python3 build_projections.py   # -> data/projections.csv in your scoring

python3 engine.py              # value-based draft board + tiers + your picks
python3 sim.py strat 2000      # compare draft strategies over 2000 drafts
python3 sim.py avail 2000      # P(player available) at each of your picks
python3 sim.py keepers         # how much the other teams' keepers move your board
python3 keepers.py             # who the other teams are most likely to keep
python3 playoffs.py            # weeks 15-17 schedule difficulty by team
python3 playoffs.py board      # easiest and hardest playoff schedules, draftables only

python3 last_season.py             # 2025 usage + luck for the top of the board
python3 last_season.py regression  # rode 2025 touchdown luck — fade list
python3 last_season.py values      # unlucky in 2025 with real usage — buy list
python3 last_season.py player bijan

python3 cheatsheet.py          # -> cheatsheet.html, printable draft-day sheet
python3 draft_day.py           # live assistant — run this during the draft
python3 advise.py add "..."    # same advice from pasted picks, for chat

python3 backtest.py            # replay five real seasons; validates the rule
python3 validate.py            # does the regression signal actually predict?
python3 season_value.py        # draft vs waiver wire: where the value actually is
python3 waiver_signal.py       # does opportunity beat points on the wire? (yes)
python3 audit.py               # data sanity check — run this the morning of
python3 -m unittest test_toolkit   # 55 tests; run before draft day
```

Re-run `fetch_data.py rankings && python3 build_projections.py` the morning of the
draft. The rankings source updates weekly, so a fresh pull costs 5 seconds and
catches every camp injury and depth-chart move the consensus has priced in.

## Draft day setup (do this the morning of)

On your own machine, not in a chat session. Needs Python 3 and nothing else.

```bash
git clone -b claude/fantasy-football-draft-co0mnh <this repo> ff && cd ff/fantasy

python3 fetch_data.py            # ~37 MB, one minute
python3 build_projections.py     # rebuilds the board on today's consensus
python3 -m unittest test_toolkit  # 55 tests, ~6 seconds — confirms nothing rotted
python3 audit.py                 # checks the data, not the code

python3 draft_day.py             # leave this open beside the Yahoo draft window
```

Verified working from a clean clone. If `fetch_data.py` can't reach GitHub, the
committed `data/projections.csv` still drives the board — you lose only the LY
column, and the assistant says so rather than failing.

Then `python3 cheatsheet.py` and print `cheatsheet.html` — tiered boards, your
pick numbers, the round plan and the endgame rules on one page. It is generated
from the same board the assistant uses, so it can never disagree with what `go`
tells you; regenerate it any time you re-pull the rankings.

Do one practice run before the real thing: start it, type ten names, hit `go`,
then delete `draft_state.json`. Two minutes, and the commands stop being
something you think about while the clock runs.

## Where the data comes from

All free, all public, no accounts and no scraping — both projects publish plain
files on GitHub:

| Source | What it gives |
|---|---|
| [nflverse](https://github.com/nflverse/nflverse-data) | Weekly player stats (2023–25), snap counts, injuries, rosters |
| [DynastyProcess](https://github.com/dynastyprocess/data) | FantasyPros expert consensus rankings, refreshed weekly, with a cross-platform ID map including **Yahoo IDs** |
| [ffopportunity](https://github.com/ffverse/ffopportunity) | Expected fantasy points — for in-season waiver work |

## How the projections are built

`build_projections.py` does four things:

1. Scores three seasons of **actual** NFL results under your exact rules — 0.5 PPR,
   your TD and turnover values.
2. Builds the historical curve of what the #N finisher at each position really
   scored, averaged across those seasons and lightly smoothed.
3. Reads the current **FantasyPros expert consensus** for who finishes where in 2026.
4. Maps each player's consensus positional rank onto the historical curve.

Player ordering is the consensus's; the points scale is real NFL history in your
scoring. That's what a value-based board needs — VORP and tiers depend on the
*shape* of the curve, not on nailing any one player's total.

**What it is not:** an independent opinion on players. It takes the market's read
and converts it into your format — which is most of the edge, because your
leaguemates are using that same consensus in a format it was never built for.

For the part that *does* disagree with the consensus, see `last_season.py` below.

Ceiling and floor come from the experts' own disagreement: each player's best- and
worst-case rank run through the same curve. Tiers come from the same signal — while
players' rank ranges overlap, the panel can't separate them and neither should you.

## Last season, and where it disagrees with the consensus

`last_season.py` is the one place the toolkit forms its own opinion.

For every 2025 play, ffopportunity models what an average player would have gained
given the situation — down, distance, air yards, field position — and converts that
into expected receptions, yards and touchdowns. Compare it to what actually
happened and you get **points over expected (POE)**:

- **POE strongly positive** — output ran ahead of the opportunity behind it. Almost
  always touchdown luck, and touchdown rate regresses hard year to year. If the
  consensus is still paying for that season, you're buying noise.
- **POE strongly negative** — real usage, unlucky finish. If the consensus faded
  them for it, that's the cheapest edge on the board.

Snap share and target share sit next to it, because POE only matters when the
opportunity behind it is real. Justin Jefferson in 2025 is the clean example: 94%
of snaps, a 30.7% target share, and **2 touchdowns against 8.6 expected** — a WR25
finish built on a WR6 workload.

Rookies and players who missed 2025 show as `new`; there is no usage history to
read and the consensus rank is the only signal.

**This is validated, not assumed** — `python3 validate.py` tests it against four
seasons. Points-over-expected repeats only ~4% year to year, so it is
overwhelmingly noise. Hot players gave back **91%** of the gap between what they
scored and what their usage earned; cold players recovered only **31%** of
theirs. So the fade list is about three times more trustworthy than the buy list:
treat a hot player as coming back to his expected line, and a cold one as a
partial bounce, not a full one.

## Draft day

Run `draft_day.py` in a terminal beside your Yahoo draft window. Type each pick as
it happens (`me <name>` when it's yours); it keeps the board, tracks your roster
needs, and when you're on the clock ranks your options by **wait cost** — each
player's value minus what you'd expect to still get at that position at your *next*
pick, from a live Monte Carlo of the intervening picks. That number, not raw
ranking, is the pick:

```
Pick 11 (round 2) — next pick 22, 10 picks away

PLAYER                   POS   TIER    VORP  SURVIVE  WAIT COST     LY
---------------------------------------------------------------------
Justin Jefferson         WR6      2    51.1      0%      +26.0   -2.6 <- gone if you wait
Drake London             WR7      2    42.8      1%      +17.7   +0.2 <- gone if you wait
James Cook III           RB6      1    86.6     30%      +15.7   +3.4 <- gone if you wait
...
Josh Allen               QB1      1    78.8     84%       +1.1   +3.0 <- safe to wait
```

Josh Allen has the highest raw value on that board and is still the wrong pick — an
8-team league won't take a QB in the next ten selections, so he keeps.

The `LY` column is last season's POE per game, coloured yellow for regression risk
and green for bounce-back. `why <name>` pulls a player's full 2025 card without
leaving the draft.

Names match fuzzily (`ja'marr`, `bijan`). State auto-saves to `draft_state.json`
after every pick, so a closed terminal doesn't lose your draft; delete it to start
over. `undo` fixes a mistyped pick. Worth one dry run so the commands are muscle
memory under the clock.

### Driving it from chat instead

`advise.py` is the same board and the same rule behind a paste-friendly
interface, for when you'd rather send picks to an assistant than run a terminal.

```bash
python3 advise.py add "Chase, Gibbs, Nacua, Smith-Njigba"
```

Picks go in **draft order** and ownership is worked out from the snake, so there
is nothing to mark as yours and no way to forget. Your keeper fills its own slot.
When the next pick is yours it prints the full table plus a one-line verdict.

An ambiguous name (`McCaffrey` matches two players) stops the batch and asks
rather than guessing, and nothing after it is recorded — a wrong name silently
recorded would corrupt every later survival number. `undo` and `reset` do what
they say.

State lives in `data/live_draft.json`, which is committed rather than ignored, so
the draft survives the machine going away between picks.

### On Yahoo

Yahoo's API doesn't expose live draft state reliably mid-draft, so the assistant is
built around manual entry — it can't break on you on draft night. Where Yahoo's API
*is* useful is pre-draft and in-season: league settings, keeper lists, rosters, and
the live free agent pool. That needs a Yahoo developer app and OAuth2 and isn't
built yet. The `yahoo_id` column in `data/projections.csv` is already there to join
against when it is.

## Files

| File | Purpose |
|---|---|
| `league.json` | Scoring, roster slots, draft slot, keepers. **Edit this first.** |
| `fetch_data.py` | Downloads all free public data to `data/raw/`. |
| `build_projections.py` | Builds `data/projections.csv` in your scoring. |
| `engine.py` | Replacement levels, VORP, tiering. |
| `opponent.py` | How the other managers draft. Shared by the sim and the live tool. |
| `sim.py` | Monte Carlo: availability, strategy comparison, keeper sensitivity. |
| `last_season.py` | 2025 usage, luck, and regression flags vs the 2026 consensus. |
| `keepers.py` | Ranks who the other teams are likeliest to keep, by surplus. |
| `playoffs.py` | Weeks 15-17 schedule difficulty — a tiebreaker between close players. |
| `cheatsheet.py` | Builds the printable one-page cheat sheet from the live board. |
| `draft_day.py` | Live draft assistant. |
| `advise.py` | Chat front end: paste picks in order, get the recommendation. |
| `audit.py` | Pre-draft data checks: duplicates, keepers, staleness, stale state. |
| `backtest.py` | Replays 2021-2025 with no lookahead and scores on real results. |
| `validate.py` | Tests the points-over-expected claim against four seasons. |
| `season_value.py` | Measures the waiver wire against the draft across five seasons. |
| `waiver_signal.py` | Tests opportunity vs points as the in-season waiver signal. |
| `test_toolkit.py` | Invariants that would otherwise break silently mid-draft. |

## Before you draft

1. **Put the other seven teams' keepers in `opponent_keepers.known` in
   `league.json`.** In a keeper league this matters more than any projection tweak —
   kept players are off the board and every consensus ranking is wrong until you
   account for them. Until you know, set `unknown_count` and run
   `python3 sim.py keepers` to see how far the board moves.
2. Re-pull rankings the morning of the draft.
3. Run `sim.py strat` to see which strategy your own numbers favor from pick 6.
4. Run `sim.py avail` and note who is unlikely to survive each 10-pick gap.
