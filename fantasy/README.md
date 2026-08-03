# Fantasy Draft Toolkit

Draft tooling calibrated to one specific league: 8 teams, 0.5 PPR, snake, pick 6,
Bijan Robinson kept in round 1. Pure Python stdlib — no install step.

See [PLAYBOOK.md](PLAYBOOK.md) for the strategy reasoning and the build roadmap.

> ⚠️ `data/projections.SAMPLE.csv` contains **made-up placeholder numbers** used to
> exercise the code. Replace it with real projections before trusting any output.

## Usage

```bash
cd fantasy

python3 engine.py          # value-based draft board + tiers + your pick numbers
python3 sim.py strat 2000  # compare draft strategies over 2000 simulated drafts
python3 sim.py avail 2000  # P(player available) at each of your picks
```

## Files

| File | Purpose |
|---|---|
| `league.json` | Scoring, roster slots, draft slot, keepers. Edit this first. |
| `engine.py` | Scoring conversion, flex-aware replacement levels, VORP, tiering. |
| `sim.py` | Monte Carlo draft sim: availability curves and strategy comparison. |
| `data/projections.SAMPLE.csv` | Placeholder input. Swap for real projections. |

## Getting real projections in

`engine.py` reads a CSV with columns:

```
name, pos, team, adp, [points], [pass_yd, pass_td, pass_int,
rush_yd, rush_td, rec, rec_yd, rec_td, fumble_lost, two_pt]
```

Supply raw stat columns and the scoring in `league.json` is applied to them — that's
the point, since it converts any source into *your* format. If your source only
publishes fantasy points, put them in a `points` column and they'll be used as-is
(but they'll be in that source's scoring, not yours).

FantasyPros allows a free CSV export of consensus projections and ADP, which is the
lowest-friction starting point.

## Before you draft

1. **Fill in the other teams' keepers** in `league.json`. In a keeper league this
   matters more than any projection tweak — kept players are off the board and every
   public ADP figure is wrong until you account for them.
2. Replace the sample projections with real ones.
3. Re-run `sim.py strat` to see which strategy your own numbers favor from pick 6.
4. Re-run `sim.py avail` and note, for each of your picks, who is unlikely to survive
   the gap to your next one. Those are your reach-justified targets.
