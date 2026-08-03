# Fantasy Playbook — 8-Team, 0.5 PPR, Pick 6, Bijan Keeper

Where the edge actually comes from, and what to build to capture it.

---

## 1. The structural read on your league

Your league is unusual in ways your leaguemates almost certainly aren't accounting
for, because every ranking list, podcast, and draft guide they consume is built for
a **12-team full-PPR** league. Four consequences:

**Replacement level is very high.** 8 teams × 14 roster spots = 112 players rostered.
A 12-team league rosters 168+. The ~56 players who'd be owned elsewhere are sitting
in your free agent pool all season. Anyone you draft has to beat *that* bar, not the
bar in the magazine.

**Only 8 QBs and 8 TEs start.** Dedicated-starter demand at those positions is a
third of what public rankings assume. QB9 and TE9 are legitimately rosterable, which
compresses the value of an early QB or TE far more than most drafters realize.
Whether that compression is *enough* to make an elite QB a bad pick is an empirical
question — that's exactly what `sim.py` is for, rather than a vibe.

**Your bench is for upside, never for insurance.** Five bench spots and a deep
waiver wire means handcuffing your own RB is nearly free money thrown away — if your
starter goes down, the backup is very often still unowned. Bench spots should hold
lottery tickets (rookie WRs, ambiguous backfields, post-hype breakouts), and you
should churn them aggressively.

**K and DEF are the last two picks. Always.** In an 8-team league you can stream both
off waivers every single week. Every round you spend on them earlier is a round of
pure loss.

**It's a keeper league, which means published ADP is systematically wrong.** If the
other seven teams each keep a player, 7 first- and second-round-caliber players
vanish from the pool before pick 1. ADP data doesn't know that. Everyone else will
draft off a board that's silently misaligned; you can draft off one that isn't.
**Finding out the other teams' keepers before the draft is probably the single
highest-value hour of prep you can do**, and it costs nothing but asking.

**Your slot.** Pick 6 of 8, snake, 14 rounds:

```
R1   6    R2  11    R3  22    R4  27    R5  38    R6  43    R7  54
R8  59    R9  70    R10 75    R11 86    R12 91    R13 102   R14 107
```

Bijan takes pick 6, so your real first decision is **pick 11, and then you don't
pick again until 22**. That 10-pick gap is the pattern for your whole draft: short
gap, long gap, short gap, long gap. Every long gap is where tier cliffs hurt you, and
those are exactly the moments the availability simulator is built to inform.

---

## 2. What to build, ranked by edge per hour

### Tier S — do these before the draft

**1. A draft board calibrated to your exact league.** *(built — `engine.py`)*
Converts projections to your 0.5 PPR scoring, computes flex-aware replacement
baselines from *your* lineup requirements, ranks by value over replacement, and
tiers each position by where the expert panel's rank ranges stop overlapping. The
`EDGE` column — value rank minus consensus rank — is a direct list of who the field
is systematically mispricing in your format.

**2. A Monte Carlo draft simulator.** *(built — `sim.py`)*
Two outputs that change decisions:
- *Availability:* "P(this player survives to pick 22)". Stops you from spending pick
  11 on someone who'd have been there at 22, which is the most common way good
  drafters leak value.
- *Strategy comparison:* runs RB-heavy vs Zero-RB vs elite-QB-early vs BPA a few
  thousand times from *your* slot with *your* keeper, and reports mean/floor/ceiling
  of the resulting starting lineup. This settles format debates with your own
  numbers instead of someone else's league.

**3. Opponent modeling from league history.** *(highest unfair-advantage-per-hour, not yet built)*
If your league is on Sleeper, ESPN, or Yahoo, prior drafts are pullable via API. Two
or three years of an 8-team league is a small sample but individual tendencies are
loud and repeat: who reaches for a QB in round 3, who only drafts their favorite NFL
team, who panics on the first K run and starts one four rounds early. Feed those
tendencies into the simulator's opponent model instead of generic ADP noise and the
availability numbers get sharply better. Almost nobody in a casual league does this.

### Tier A — do these during the season

**4. A weekly waiver-wire agent.** *(the biggest season-long edge in a shallow league)*
Because your FA pool is so deep, waivers is where the season is won. The signal to
chase is **opportunity, not past points**: snap share, route participation, target
share, red-zone touches, and backfield-committee changes predict future fantasy
scoring far better than last week's box score, and they show up a week or two before
the points do. A scheduled job that ingests last week's usage, filters to players
actually free in your league, and ranks them by rest-of-season value with a
recommended drop is a durable weekly edge over managers reading a generic
"top 10 waiver adds" article written for 12-team leagues.

**5. Start/sit with Vegas inputs.** Implied team totals (from the game total and
spread) are the best free predictive input in fantasy and most managers ignore them
entirely. A player on a team implied for 27 points is in a different projection
regime than the same player implied for 17. Combine with opponent-defense-vs-position
and you have a start/sit tool that beats site-default projections.

**6. An injury and beat-reporter monitor.** In a league where waiver claims are
contested, being first to a backfield change matters more than being right about it
a day later. A cron that watches for practice reports, snap-count surprises, and
depth chart moves and pings you is cheap to build and occasionally decisive.

### Tier B — nice, lower leverage

**7. Trade finder.** Model each opponent's starting lineup, find trades that improve
your weakest starting slot more than they cost you. In an 8-team league trades matter
less than waivers, but "buy low on a stud whose owner is panicking" is real.

**8. Playoff-schedule weighting.** Use weeks 15–17 strength of schedule as a
tiebreaker between similarly-valued players late in the draft, and as a trade lever
in November.

**9. Make your local Claude Code a permanent GM.** A `CLAUDE.md` in this repo plus
custom slash commands (`/waivers`, `/startsit`, `/trade-check`) so in-season work is
one command instead of a re-explanation every week.

---

## 3. The data

Everything runs on free public data, pulled with one command and no accounts:
**nflverse** for actual NFL results, snap counts and injuries; **DynastyProcess**
for weekly FantasyPros expert consensus rankings plus a player ID map that includes
Yahoo IDs; **ffopportunity** for expected fantasy points. All three publish plain
files on GitHub. See the README for how projections are assembled from them.

## 4. Honest limits

**The projections are the consensus's opinion in your format, not an independent
one.** Player ordering comes from FantasyPros' expert panel; only the points scale
is derived from real NFL history under your scoring. The tools cannot tell you the
consensus is wrong about a player. What they can do — and what your leaguemates
can't — is convert that consensus into an 8-team 0.5 PPR board with correct
replacement levels, and tell you who survives your next 10-pick gap.

Rank-to-points mapping assumes the #N finisher in 2026 scores like the #N finisher
historically. That's a good assumption for the *shape* of the curve, which is all
VORP and tiers need. It is a bad assumption for any individual player's total, so
don't read the points column as a prediction.

The consensus board is FantasyPros' full-PPR redraft ranking. It is used only for
*ordering within position* and as the ADP proxy for opponent behavior, both of which
are fine. It does mean the simulator assumes your leaguemates draft roughly to
public consensus — true for most casual 8-team leagues, and improvable once you
model their actual tendencies (item 3 above).

More broadly: projections are a commodity, and you will not out-predict the market on
raw player talent with a weekend of code. The edge here is **format calibration,
keeper-adjusted boards, draft-day discipline under a 90-second clock, and speed on
waivers** — process advantages, which happen to be exactly the ones that compound
over a season.

## 5. Blind spots found and fixed

Worth recording, because each was invisible until measured:

**The opponent model hoarded quarterbacks and never drafted a kicker.** Simulated
drafts took 15 QBs in a league that starts 8, and zero K/DEF — their consensus rank
is ~200, so a skill player always looked better. In your real draft, sixteen picks
in the last two rounds go to K/DEF. Fixing it meant giving opponents a concept of
roster *needs* rather than just rankings, which also self-corrects the 12-team bias
baked into consensus rankings. The effect on advice is large and directional: Trey
McBride's odds of lasting from pick 11 to 22 went from 26% to 92%, turning a "reach
now" into a "wait".

**The live assistant had its own, worse copy of that model** — no roster needs at
all. Both now run the same code in `opponent.py`, and it reconstructs each
opponent's roster from the pick log, so it knows which teams already have a QB.

**Drafters herd and the model didn't.** Independent draws never produce a run on
tight ends. Recent picks at a position now pull that position forward for everyone.

**Nothing modelled the other teams' keepers**, despite this document twice calling
them the single biggest source of board error. `sim.py keepers` now shows the
sensitivity directly.

**There were no tests.** Every bug above was caught by squinting at output. There
are now 33, covering snake math, keeper handling, lineup optimisation, roster
legality and survival monotonicity.

## 6. Known limits that remain

**Consensus rank is standing in for ADP.** No free ADP source exists, and ECR is
what experts think rather than what drafters do. The need-aware opponent model
narrows the gap but cannot close it. If you run a mock draft on Yahoo, the pick
order it produces is worth more than any of this — send it over and it can be
fitted directly.

**Opponents are modelled as one archetype.** Real leaguemates have tendencies: the
one who always reaches for a quarterback, the homer who drafts his own team. Two or
three years of your league's Yahoo draft history would replace the generic model
with seven specific ones. That is still the highest-value unbuilt item.

**Rank-to-points assumes the #N finisher scores like the #N finisher historically.**
Fine for the shape of the curve, which is what VORP and tiers need. Not a
prediction for any individual player.

**In-season is untouched.** Waivers are where a shallow league is won, and none of
that is built yet.
