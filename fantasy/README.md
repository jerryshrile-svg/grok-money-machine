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
python3 draft_day.py           # live assistant — run this during the draft
```

Re-run `fetch_data.py rankings && python3 build_projections.py` the morning of the
draft. The rankings source updates weekly, so a fresh pull costs 5 seconds and
catches every camp injury and depth-chart move the consensus has priced in.

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

**What it is not:** an independent opinion on players. It can't tell you the
consensus is wrong about someone. It takes the market's read and converts it into
your format — which is the whole edge, because your leaguemates are using that same
consensus in a format it was never built for.

Ceiling and floor come from the experts' own disagreement: each player's best- and
worst-case rank run through the same curve. Tiers come from the same signal — while
players' rank ranges overlap, the panel can't separate them and neither should you.

## Draft day

Run `draft_day.py` in a terminal beside your Yahoo draft window. Type each pick as
it happens (`me <name>` when it's yours); it keeps the board, tracks your roster
needs, and when you're on the clock ranks your options by **wait cost** — each
player's value minus what you'd expect to still get at that position at your *next*
pick, from a live Monte Carlo of the intervening picks. That number, not raw
ranking, is the pick:

```
Pick 11 (round 2) — next pick 22, 10 picks away

PLAYER                   POS   TIER    VORP  SURVIVE  WAIT COST
--------------------------------------------------------------
Justin Jefferson         WR6      2    51.1      0%      +26.0 <- gone if you wait
Drake London             WR7      2    42.8      1%      +17.7 <- gone if you wait
James Cook III           RB6      1    86.6     30%      +15.7 <- gone if you wait
...
Josh Allen               QB1      1    78.8     84%       +1.1 <- safe to wait
```

Josh Allen has the highest raw value on that board and is still the wrong pick — an
8-team league won't take a QB in the next ten selections, so he keeps.

Names match fuzzily (`ja'marr`, `bijan`). State auto-saves to `draft_state.json`
after every pick, so a closed terminal doesn't lose your draft; delete it to start
over. `undo` fixes a mistyped pick. Worth one dry run so the commands are muscle
memory under the clock.

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
| `sim.py` | Monte Carlo: availability curves and strategy comparison. |
| `draft_day.py` | Live draft assistant. |

## Before you draft

1. **Put the other seven teams' keepers in `league.json`.** In a keeper league this
   matters more than any projection tweak — kept players are off the board and every
   consensus ranking is wrong until you account for them. The tools hold keepers out
   of the pool for all teams, so availability and wait-cost math stay correct.
2. Re-pull rankings the morning of the draft.
3. Run `sim.py strat` to see which strategy your own numbers favor from pick 6.
4. Run `sim.py avail` and note who is unlikely to survive each 10-pick gap.
