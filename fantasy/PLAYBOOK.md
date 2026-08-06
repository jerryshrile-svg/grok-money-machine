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

## 7. The answer: what to actually do

Measured, not asserted. 400 simulated drafts from pick 6 with Bijan kept,
scored on best legal starting lineup:

```
STRATEGY                   MEAN    FLOOR     CEIL   vs BEST
Wait-cost (live tool)    1741.3   1706.5   1779.2      +0.0
RB heavy                 1732.1   1700.7   1766.0      -9.2
Zero RB                  1670.4   1642.6   1702.3     -70.8
Elite QB early           1638.1   1619.5   1660.8    -103.2
Hero RB -> WR wall       1637.4   1604.2   1674.7    -103.8
Elite TE early           1622.0   1601.4   1644.6    -119.3
BPA (pure value)         1547.4   1481.5   1673.8    -193.9
```

Two things to read out of that. The adaptive rule wins, but only by ~9 points
over plain RB-heavy — a real edge, replicated across independent runs, and a
small one. And **best-player-available finishes last**, with by far the widest
spread: chasing raw value with no regard for lineup holes sometimes builds a
great team and sometimes strands you starting a replacement-level tight end.

### Why: tier depth

| Position | Tier-1 players | Last tier-1 at consensus # |
|---|---|---|
| WR | 4 | #6 |
| RB | 6 | #19 |
| TE | 4 | #54 |
| QB | 7 | #69 |

All four elite receivers go inside the top six, so they are gone before pick 11
every time. Tier-1 running back runs to #19, so one falls to you. Tier-1 tight
end runs to #54 and tier-1 quarterback to #69 — those wait rounds, not picks.

Replacement level is RB 179 and WR 177, nearly identical, but you start two
backs plus a flex, and the consensus board is full-PPR while you play 0.5.

### The shape it produces

Bijan plus two more backs through pick 22, receivers from 27 to 54, quarterback
in the 27-43 window, tight end around 70-75, kicker and defense with the last
two picks. `python3 sim.py plan` regenerates the detail.

On quarterbacks specifically: forcing one at pick 11 is among the worst things
you can do, but the winning rule still takes Josh Allen at pick 27 about a third
of the time, because by then the tier-1 backs are gone and his wait cost peaks.
If he is gone, do not chase — tier-1 QB extends to #69.

**None of this is a script.** Pick 11 goes receiver 29% of the time. If an elite
one slides, take him; that is the rule working, not the plan failing.

---

## 8. What the confirmed settings change

**Six of eight teams make the playoffs.** Qualifying is close to automatic — you
only have to avoid finishing in the bottom two. So the regular season's real job
is **seeding**, not survival. If the top two seeds get byes, they win the title
by taking two games instead of three, which roughly doubles their odds. Chasing
the highest possible seed is worth more than any single draft pick.

The second consequence is that the title is decided in three weeks, so **ceiling
beats consistency**. A boom-bust roster that wins a shootout in week 16 is worth
more than a steady one. Worth noting the wait-cost rule already wins on ceiling
as well as on mean, so the recommendation does not change — but between two close
players, take the one with the higher ceiling, not the safer floor.

Third: **bye weeks matter much less than the tools imply.** Byes fall in the
regular season, where you can absorb losses. The bye-stack warning in the live
assistant is worth glancing at, not worth a pick.

**Weeks 15-17 schedule is now a real tiebreaker** rather than trivia, because
those are the only weeks that decide anything. `playoffs.py` ranks it. Use it to
break ties between players you rate closely — never as a reason to reach.

Confirmed against the 2026 calendar: NFL week 17 ends Monday 4 January 2027,
which matches the league's playoff end date, so the bracket is weeks 15-16-17
and the fantasy regular season is weeks 1-14. Two things follow. **No team has a
bye in weeks 15-17**, so bye weeks can only ever cost you seeding, never the
title — one more reason not to spend a pick avoiding them. And week 18 is not
used, which is the normal and correct choice: that is the week starters rest.

The residual risk is that week 17 is now your championship, and a team that has
already locked its seed can rest starters a week early. It is a smaller risk than
week 18 would be, but it is not zero, and it slightly favours players on teams
still fighting for position in late December.

**Waivers are a continual rolling list, not FAAB.** That makes priority a
depleting resource: every claim you win drops you to the bottom of the queue.
Two rules follow.

1. **Hoard priority.** Only burn a claim on a player who plausibly changes your
   season — a back who just inherited a starting job, a receiver whose target
   share just doubled. Everything else can wait until the player clears waivers
   and becomes a free agent, which costs nothing.
2. **The waiver-wire edge is about being right early, not being fast.** In a FAAB
   league you outbid; here you cannot. What you can do is identify the player
   whose usage moved *before* the points show up, and spend your one good claim
   on him rather than on last week's box-score hero.

Initial priority usually runs in reverse draft order, so drafting sixth of eight
starts you around third — good position. Do not spend it in week 2.

**A keeper costs the round the player was drafted in last year.** This is the
single biggest structural fact about the league, because it means keepers are a
surplus calculation and the most likely keepers are last year's late-round
breakouts, not this year's best players. `keepers.py` ranks them. Seven opponent
keepers cost you roughly 45 lineup points, because the talent leaves the board
and the picks burned are middle-round, so nothing comes back to you.

**There is an IR slot.** That reverses part of the advice above: a player who
opens the season on IR or PUP is a free stash, since he does not occupy a bench
spot. One of your last two or three picks should be exactly that.

---

## 9. The backtest: what actually held up

Five real seasons replayed with only what was knowable each August, scored on
what those players actually did week by week. `backtest.py`. Numbers are points
above simply drafting the consensus list, which is what the rest of your league
does.

```
STRATEGY                     MEAN     BEST    WORST   WINS
Wait-cost (live tool)         +44     +144      -44    4/5
Zero RB                       +10     +104     -118    4/5
Consensus list                 +0       +0       +0    0/5
RB heavy                      -26      +28     -101    1/5
BPA (my board)               -133      -15     -191    0/5
```

**The live tool's rule survives contact with reality.** That is the one claim in
this repository that has been tested rather than asserted.

**Two things did not survive.**

*Rigid RB-heavy is worse than drafting the list* — minus 26 a season, one winning
season in five. Earlier drafts of this playbook claimed following an RB-heavy
shape would capture most of the edge. It does not. The adaptation is the edge.

*Chasing raw value on this board is much worse than drafting the list* — minus
133, losing all five seasons. The diagnosis is positional: best-available on this
board spends 64% of its first six picks on tight ends and quarterbacks and takes
a quarterback in round 2.8, because last-starter baselines make QB9 and TE9 look
like an enormous drop from the top. The wait-cost rule escapes this only because
survival odds tell it quarterbacks last. So the board is a fair input to that
rule and a poor ranking on its own — do not draft off the VORP column directly.

**The obvious fix made things worse, which is why it was tested.** Re-baselining
against the best player available on waivers all season (QB10, RB32, WR48, TE10)
did rescue naive value-chasing, lifting it from -133 to -99 and RB-heavy from
-26 to +15. But it cut the wait-cost rule from +44 to +24 and from four winning
seasons to three, by inflating running back and receiver value so far that the
rule could no longer take an elite quarterback or tight end when one fell. The
capability is still in `engine.py` behind `replacement_depth`; it is deliberately
not enabled.

**The caution.** In 2025 — the most recent season and the one that most resembles
the conditions you are drafting into — every strategy lost to the consensus list,
the wait-cost rule by 44 points. A plus-44 average carries real variance, and
five seasons is a small sample. Treat the rule as an edge, not a guarantee.

---

## 9. Where the value actually is

Measured, not assumed. Same drafted roster, replayed across five real seasons
with and without in-season adds:

```
SEASON    DRAFT ONLY  WITH WAIVERS    GAIN   PERFECT  CEILING
2021            1581          1595     +14      1890     +309
2022            1630          1624      -6      1821     +191
2023            1478          1512     +34      1855     +377
2024            1601          1646     +44      1928     +327
2025            1640          1640      -0      1870     +230
mean                                   +17               +287
```

Three numbers matter.

**The draft lever is +44 a season** — the gap between the wait-cost rule and
drafting straight off the consensus list. That is real, it is validated, and the
tooling to capture it is built.

**Naive waiver management is worth +17** — less than the draft, and negative in
two of five seasons. Chasing last month's points actively hurt in 2022 and did
nothing in 2025. So "just churn the wire" is not a strategy.

**The ceiling on the wire is +287** — six and a half times the entire draft
lever. That is with hindsight and nobody achieves it, but the shape of the answer
is unambiguous: the free agent pool in an 8-team league holds enormous value, and
a manager reacting to trailing points captures about 6% of it.

The gap between those last two numbers, roughly 270 points a season, is the
addressable opportunity. It dwarfs everything left on draft day. And the reason
naive churn fails is exactly the thing flagged at the very start of this
playbook: **trailing points are the wrong signal**. Snap share, route
participation, target share and expected points move first, and the data for all
of them is already downloaded.

So the priority after 15 August is not a better board. It is the waiver tool —
and it has to be built on opportunity metrics, because the version built on
points has now been measured and is barely worth running.

---

## 10. A change that was measured and rejected

Worth recording, because the reasoning was persuasive and wrong.

A full 14-round rehearsal showed the tool taking two quarterbacks in a one-QB
league. That looks like an obvious waste: with 5 bench spots and hundreds of
unowned players, you can stream the position, so a backup should be discounted
heavily. The discount was applied and then measured across five seasons, scored
both without waivers and with them:

```
BACKUP_WEIGHT     draft-only    with waivers
0.08                    1591            1611
0.35                    1606            1622
```

It lost under both, and the full backtest fell from +44 points a season over the
consensus list to +27, from four winning seasons to three. So the change was
reverted.

Two things to take from it. Backup value is real — byes and injuries have to be
covered every week, and a high-value QB2 or TE2 can genuinely beat the marginal
receiver you would otherwise take. And more usefully: **the intuition sounded
right, was specific, and was still wrong.** Anything that "obviously" improves
the board should be run through `backtest.py` before it is kept, including
changes that come from me.

---

## 11. On the number I kept quoting

The wait-cost rule's edge was reported as "+44 points a season" for several days,
including on the printed cheat sheet. That was one backtest run at forty drafts
per strategy, treated as if it were precise. It is not.

Re-running after unrelated changes produced +27. Chasing that gap turned up a
genuine logic bug — the weighting condition read `need[pos] > 0 or need[FLEX] > 0`
and so gave backup quarterbacks full weight whenever any flex slot was open, even
though a quarterback cannot fill one — but a head-to-head on identical seeds
showed the fixed version is *better*, not worse:

```
RULE           draft-only   with waivers   QBs drafted
legacy               1585           1608          2.00
flex-aware           1596           1612          2.00
```

So the bug was real and worth fixing, and it was not the cause of the difference.
The +44 and the +27 are the same measurement taken twice.

**What is stable across every run is the direction and the win rate: the rule
beats drafting straight off the consensus list, in four seasons out of five.**
The magnitude moves between roughly +25 and +45 depending on the sample. Quote
the range, not a point estimate — and treat any single backtest run at these
sample sizes as a rough number, including when it says something flattering.

---

## 12. The settled numbers

20,000 drafts — 800 per strategy per season, five seasons — with every strategy
facing identical opponents on each draft so the comparison is paired. This
supersedes every earlier figure in this document.

```
STRATEGY                     MEAN   ± SE    WINS  VERDICT
Wait-cost (live tool)         +30      2    5/5  real
Consensus list                 +0      0    0/5  baseline
Zero RB                        -2      3    2/5  inside the noise
RB heavy                      -21      3    1/5  real, and bad
BPA (my board)               -144      3    0/5  real, and bad
```

**The wait-cost rule is +30 points a season and won all five.** At a standard
error of 2 that is fifteen standard errors from zero — not a close call. Earlier
runs had it at 4 of 5 with a loss in 2025; at proper sample size, 2025 is +9 and
the record is perfect.

**Zero-RB is not an edge.** Earlier noisy runs put it at +10 winning 4 of 5. It
is -2 ± 3, which is nothing.

The per-season detail explains why a fixed plan cannot work:

```
            2021    2022    2023    2024    2025
RB heavy     +45      -8     -34     -44     -65
Zero RB      +42     -37      -1    +104    -118
Wait-cost    +23     +22      +2     +93      +9
```

RB-heavy was the best plan available in 2021 and among the worst in 2025.
Zero-RB swung from +104 to -118 in consecutive years. **The wait-cost rule is
never the single best plan in a given season — it was beaten in 2021 and 2024 —
and it is the only one that is positive in every season.** It wins on robustness,
not on peak, which is exactly what you want when you cannot know in advance which
kind of year you are drafting into.

---

## 13. The in-season signal, finally tested

The claim in section 2 — that waiver decisions should follow **opportunity, not
points** — was made before any of this existed and repeated for weeks without
evidence. It is now measured, over 320 paired seasons. Same drafted rosters, same
one-add-a-week budget, same real scoring; only what the manager looks at changes.

```
MANAGER READS     SEASON PTS   vs NO WAIVERS   % OF CEILING
no waivers              1599        +0                  0%
points                  1616       +17 ± 3              6%
opportunity             1627       +28 ± 4             10%
blended                 1629       +30 ± 4             11%
perfect                 1874      +275 ± 6            100%

opportunity vs points:  +11 ± 3  -> real
blended vs opportunity:  +2 ± 2  -> inside the noise
```

**The claim holds.** Watching expected points instead of the scoreboard is worth
+11 a season at nearly four standard errors — about a third of the entire draft
edge, from one change in what you look at. And blending the two signals adds
nothing measurable, so the in-season tool should read expected points only. That
is a simpler tool than the one this playbook originally described.

### Two corrections to earlier sections

**Section 9 oversold the opportunity.** It called the gap to the hindsight
ceiling "roughly 270 points a season" of addressable value. That was wrong. The
ceiling arm knows in week 3 what a player will average through week 17; no signal
available in real time can approach it. The best rule reaches 11% of it. Most of
that gap is unreachable, not merely unclaimed.

**Section 9 also implied waivers dwarf the draft.** On the corrected numbers the
two levers are close to equal: the draft is worth +30 a season, and the best
waiver rule is worth +28. They are comparable, and you want both. What is true is
that the draft's edge is already captured and the waiver edge is not.

---

## 14. The loop, and the step that was missing

The working method here has been: establish the current state, establish the
desired state, identify the gaps, point at a gap, and repeat. That part was never
the problem.

**The missing step was a verifier**, and every failure in this project traces to
its absence rather than to carelessness:

| What went wrong | What was missing |
|---|---|
| A headline figure quoted for days | error bars — noise read as signal |
| Backup quarterbacks "obviously" discounted | a measurement taken before shipping |
| The board's own value ordering losing to the consensus | a backtest, which did not exist yet |
| A keeper still draftable by opponents | a test on the invariant |
| The waiver model dropping its only quarterback | a legality check |
| Stale draft state holding 112 practice picks | a data audit |

Each was caught the moment a verifier existed, and none were caught by attention.
That is the lesson worth keeping: verification has to be an artefact that runs,
not a habit that is remembered.

`verify.py` is that artefact. It re-measures every claim this document makes and
fails if any of them has stopped being true, and it prints the open gaps every
time it runs so they cannot quietly fall off the list. **A claim that cannot be
re-measured does not belong in this playbook.**

Its own first version proved the point immediately. It parsed the wrong two
columns out of the backtest — reading the raw season-points total as the edge —
and reported `+1590 ± 41` as a pass. The check was effectively asserting that
points exceed twice the difference, which is true regardless of whether the rule
works at all. **A verifier that cannot fail is worse than no verifier, because it
manufactures confidence.** There are now four tests on the parser itself,
including one that feeds it a dead edge and requires a failure.

The rule that follows: any change to the board, the weighting or the opponent
model gets run through `verify.py --full` before it is believed — including
changes that seem obviously correct, and especially those.
