# WPBL dice baseball — design spec

A two-player tabletop baseball game with cards and dice, using the 2026 WPBL.
One roll resolves a plate appearance. Both players set lineups and make the
pitching decisions; computer agents will be needed to test the game. It may
precede or replace the bullpen simulator (`bullpen_spec.md`). **DECISION
(user, 17 Sep).**

Status: design; cards and the d100 table built (`pixi run dice`, sections 3 and
4), v0.4.0. Numbers are from this repo's training scope: **39 games** -- the
30-game regular season, both semifinal series, and all five championship games,
the last on 22 Sep. **The season is complete; there is no more data coming.**
Semifinal G3 (14 Sep) is the only exclusion, because both bullpens were
exhausted (`tables.TRAINING_EXCLUDED`). It stays in the "all" scope, and the
fatigue work reads it there deliberately -- it is the league's one look at
pitchers working past the point a manager would normally allow.
**DECISION (user, 17 Sep; scope closed 23 Sep).** Items marked
**ASSUMPTION** are choices, not findings; items marked **OPEN** are undecided.

Policy: the probability distribution must reflect the data first; game
mechanics are then designed to reproduce it. Which card carries which line is
a finding, not a rule. **DECISION (user, 17 Sep).**

## 1. The chain

A play is a transition between base-out states, as in `markov.py`. The engine
needs nothing else: state is inning, half, outs, which bases are occupied,
score, and each pitcher's fatigue.

Design rule: **fidelity stops where the data stops.** 2,798 plate appearances
cannot support runner-by-runner advancement rules, so runner movement is fixed
per outcome line, with one variant line where the data shows a real coin flip.

## 2. Outcome lines

Two different jobs, kept apart:

1. **Card lines** come from the feed's play labels, consolidated from 15 to 8
   by `batters.contact()`. Counts are the 39 training games:

| Card line | Feed labels |
|---|---|
| K | strikeout 324; generic "out" 3 (batter's interference: an out with no ball in play) |
| BB | walk 348 |
| HBP | hit by pitch 98 |
| HR | home run 70 |
| 1B | single 587; fielder's choice 1 (the ball got through to the outfield) |
| 2B | double 126; **triple 1** -- Skylar Kaplan, 20 Sep, the only one of the season |
| ROE | reached on error 65 |
| Out | groundout 385, flyout 297, popup 122, fielder's choice 102, lineout 98, generic "out" 76, foul out 57, sacrifice 33 |

   Six of the eight are printed on a card. **2B and ROE are fixed league bands**
   on neither card, read straight off the d100 (section 4).

2. **What an outcome does to the runners** (the out flavors and Single+ below)
   comes from base-out transitions. It is league-wide, not on the cards.
   **DECISION (user, 17 Sep).**

The 15 Sep line table mixed the two: it counted outcomes by where the batter
ended up, not by label. That filed 53 fielder's choices and 6 singles with a
runner thrown out as singles, losing 59 outs (roughly one run per team per game
too many), and counted the 14 errors that put the batter on 2nd as doubles too.

**Outs** come in three flavors, each with an optional + modifier:

| Flavor | With a force at 1st | Without one |
|---|---|---|
| B | batter out | batter out |
| F | runner from 1st out at 2nd, batter to 1st, forced runners advance one | as B |
| FB | batter and runner from 1st out, other forced runners advance one | as B |
| + | unforced runners also advance one (B+: every runner advances one) | |

Evidence (39 training games): of the 419 plays the flavor table governs -- a
plate appearance with runners on, <2 outs, and a label that is an out -- these
lines reproduce 391 (93.3%). `out_flavors.py` counts 417 under a marginally
narrower filter; the two-play difference is the filter, not the data.

`proposals.py` reports the same coverage on a wider set of 537 (502, 93.5%): it
counts any plate appearance where an out was *recorded*, whatever the label,
which adds strikeouts, singles with a runner thrown out and unlabelled plays.
Strikeouts are not governed by the flavor table at all -- a strikeout cannot be
a fielder's choice -- so 419 is the denominator that means something.

- F uses the force at 2nd: of 30 fielder's choices with 2+ forced runners, 20
  took the runner from 1st, 9 the lead runner and 1 a middle runner. A
  lead-runner fielder's choice leaves the same base-out state as B, so both
  kinds are covered.
- FB: 10 of 11 nobody-out double plays retired the batter and the runner from
  1st; in all 9 ground-ball double plays from 1st and 2nd, the runner from 2nd
  reached 3rd.
- Sacrifice flies are B+ (the runner from 2nd also advances). **DECISION (user).**
- The other unreproduced plays (hits with a runner thrown out, non-force double
  plays) map to the line nearest in run value. **DECISION (user).**

**League flavor rates** (`out_flavors.py`; 399 out plays with runners on and <2
outs). The family is read off the feed's own label and never inferred from the
base-out change: inferring it leaves two thirds of plays ambiguous, because with
a runner on 1st "batter out, runner holds" and "runner forced, batter safe" are
the same state, and a tie-break would then be doing the measuring. Only the + is
read off the transition.

| Family | Share of outs with runners on | + rate | + measured on |
|---|---|---|---|
| B | 72.7% | 37.1% | 264 plays |
| F | 14.4% | 78.6% | 14 plays, pooled with FB |
| FB | 13.7% | 78.6% | 14 plays, pooled with F |

**F and FB share one + rate, because they are the same play with a different
number of outs recorded.** 45 of the 56 F plays read "reached on a fielder's
choice; [runner] out at second", and not one of the 56 mentions a throw to 1st.
The 49 ground-ball double plays are the identical fielding sequence with "to 1b"
on the end -- "ss to 2b" against "ss to 2b to 1b". An F is a double-play attempt
whose relay did not retire the batter, so whatever the other runners do on one
they do on the other. Measured apart the two read 1 of 2 and 9 of 11, which is
no evidence of a difference; pooled they are 11 of 14 = 78.6%, and the rate rests
on 14 plays instead of 2. The full season added one F/FB plate appearance with a
visible `+`, which is the whole of what more data bought here.
**DECISION (user, 21 Sep).**
The other 11 F plays are lead-runner force outs (6 at third, 5 at home), which
leave the same base-out state as B.

So the six flavors, as shares of all outs with runners on:

| | no + | with + |
|---|---|---|
| B | 45.7% | 27.0% |
| F | 3.2% | 10.8% |
| FB | 3.1% | 10.2% |

**The + rate splits hard by whether a force is on**, and that matters more than
anything else here: a B advances an unforced runner 55.6% of the time with
nobody on 1st and 26.1% with a force on (the 37.1% above is the two blended).
The reason is situational rather than mysterious -- with a runner on 2nd only, an
out to the right side moves her along, while with a force on the out often
removes the runner instead. The dice table is built per force state
(`out_quantize.py`), not off the blended number.

The family share is solid; the pooled F/FB + rate still rests on 13 plays.
Dropped from it are plays whose inning ended (28 of 305), because the feed never
shows the bases after the third out, and plays where the + changes nothing
visible -- most of them, since with a runner forced out the batter takes the base
the runner left. The force matters far more than anything a card could carry: with a
runner on 1st the mix is B 63.5% / F 19.1% / FB 17.4%, without one B 96.4%.
**OPEN:** the 13 visible plays are selected by which base states make the +
visible, and F and FB are selected differently (2 against 11), so pooling also
assumes the + does not vary by base state -- untestable at this size. **OPEN:**
there is no measurement at 2 outs at all.

**Singles** have three levels, read off the same d12 as the out flavors.
**DECISION (user, 21-22 Sep.)** `+` means on a single what it means on B / F /
FB -- *every* runner takes the extra base -- so the middle level needs its own
mark rather than borrowing the plus:

| | runner from 2nd | runner from 1st | d12, 0-1 out | d12, 2 outs |
|---|---|---|---|---|
| Single | to 3rd | to 2nd | 1-7 | 1-4 |
| Single . | **scores** | to 2nd | 8-10 | 5-9 |
| Single + | **scores** | **to 3rd** | 11-12 | 10-12 |

The batter takes 1st and the runner from 3rd scores on all three. The levels are
one event, not two independent ones: in 103 singles with runners on 1st and 2nd,
the runner from 1st reached 3rd in **0** of the 47 where the runner from 2nd
held, and in 21 of the 56 where she scored. The die matches the measurement
closely -- any advance 5/12 = 41.7% against 42% at 0-1 out and 8/12 = 66.7%
against 67% at 2 outs; the full `+` 2/12 = 16.7% against 14.5% and 3/12 = 25%
against 23.2%.

This replaces the 17 Sep "two outs, run on anything" rule, which was chosen when
the two-out figure read 76% on 36 games. At 67% it was rounding too far: playing
it out, "always" cost 0.013 on the mean run-expectancy error and pushed every
two-out multi-runner state high.

**Doubles and errors** move the runners by a fixed rule, taken from the modal
transition in every state (`pixi run advance`):

- **2B:** batter to 2nd; runners from 2nd and 3rd score; runner from 1st to 3rd.
  (Fits the modal transition in all seven states: `___`->`_2_` 47 of 47,
  `1__`->`_23` 18 of 23, `123`->`_23` with 2 runs 9 of 11.)
- **ROE:** batter to 1st; every runner advances one. (`___`->`1__` 22 of 30,
  `1__`->`12_` 10 of 13, `12_`->`123` 3 of 4.)

**Errors:** ROE is its own line, by label, excluded from Single and Double, and
is now a fixed league band rather than a card entry (section 4).

**Which outcomes share a line** is tested, not assumed: two outcomes stay apart
only if that predicts held-out games better (runs error, log5 matchup, 20 game
splits; `analysis/dice/merge_log5.py`).
- 1B and ROE stay apart: merging them is worse by 2.4 SE (+58, SE 24). ROE
  mostly reflects the fielders behind the pitcher, singles the batter. Making
  ROE a league band keeps them apart for the same reason.
- **BB and HBP stay apart**, reversing the 19 Sep free-pass merge. They were
  merged because keeping them apart scored no better (merged -81, SE 71) -- but
  that test was blind by construction: a walk is worth 0.45 runs and an HBP
  0.49, so a runs score cannot see the difference at all (section 9.0). Asked
  the question that actually decides the table -- whose card should the line be
  read from -- they are opposites: walks want the pitcher's card (weight 0.70),
  hit-by-pitches the batter's (0.20). Each is its own card line and the d10
  free-pass split is gone. **DECISION (user, 21 Sep).** (`mixture_per_line.py`)
- All outs share one line: their differences are the league-wide out flavors
  above, and a batter's ground-ball tendency moved her double-play odds by
  about one dice cell. Nor is any batter measurably better or worse at the +
  (section 3.6), so the flavor and its + come off an extra die at league rates.

**Doubles** include triples (none in the training games). **Running plays**
(wild pitch, passed ball, balk) remain a league line: every runner advances one,
then roll again; with the bases empty it is a reroll.

**OPEN:** how the out flavors are rolled -- fixed bands on the extra die (as in
the 15 Sep table) or fractions of each matchup's outs. Since no batter shows
real spread in either the family or the +, the rates are league-wide either way,
so this is a question about dice, not about probability.

## 3. Player cards

Every pitcher and batter has a full card. Six lines are printed -- OUT, K, HBP
BB, 1B, HR -- and together they fill that player's block of the d100 (section
4). 2B and ROE are fixed league bands on neither card. Smoothing decides how
far each player differs from her cohort; no printed line is left off a card by
rule. This replaces the 15 Sep rule that an entry exists only if its league
spread exceeds one dice cell, and the batter ground-ball entry is dropped.
**DECISION (17 Sep).**

`pixi run dice` (`src/wpbl/dice.py`) builds every card and writes
`data/dice/cards_batters.csv` and `data/dice/cards_pitchers.csv`, each carrying
both the probabilities and the printed d100 cells. The tuning runs behind the
constants below are analysis, not part of the module.

**The 1% floor is not applied to a card.** A card is half of a matchup; the
distribution a d100 has to represent is the one left after a batter and a
pitcher have been combined, and that is where `floor()` belongs. Flooring the
cards as well would floor twice, and a line can only be rounded up once.
**DECISION (user, 21 Sep).**

**League average.** `data/dice/cards_league.csv` holds an average batter and an
average pitcher, for a player with no card and as the baseline a real card is
read against. Both are the league's own line over every training PA, so the two
rows are identical: each PA has a batter and a pitcher, so the season is one
distribution. It is deliberately not the mean of the player cards, which differs
by side and is not what "average" should mean here. **DECISION (20 Sep).** The
original argument for this definition was a log5 identity -- the league card is
the L a matchup divides by, so a player facing it keeps her own card exactly
(verified for all 104 players to 1e-6 of a point, against up to 1.9 points of
drift for the mean of the cards). That identity no longer applies now that the
combination rule is a mixture, under which facing the league card shrinks a
player toward league by the mixing weight. The definition stands on the
one-distribution argument alone.

### 3.1 Smoothing in steps

Outcomes are split step by step. Each step divides a group of outcomes and is
smoothed toward the player's cohort with its own constant k:

    step share = (her count + k * cohort share) / (her count at the step + k)

A card line is the product of the shares along its path, so the six printed
lines sum to what the bands leave over, and outs are an explicit outcome, not a
remainder. A hole in one outcome can be filled only from within its own step:
smoothing cannot give a player hits she did not make. **DECISION (user,
18 Sep).** 2B and ROE sit outside both trees, so every step answers "given it
was not a double or an error, what happened?", and the tree's shares are scaled
by 1 minus the bands.

**Batters:**

| Step | Split | k |
|---|---|---|
| 1 | true outcomes (K+BB+HBP+HR) \| in play (1B+Out) | 16 |
| 2 | HR \| K+BB+HBP | 2 |
| 3 | K \| BB+HBP | 16 |
| 4 | BB \| HBP | 2.83 |
| 5 | 1B \| Out | 45 |

**Pitchers:**

| Step | Split | k |
|---|---|---|
| 1 | K \| not K | 1 |
| 2 | BB+HBP \| in play | 64 |
| 3 | BB \| HBP | 2.83 |
| 4 | Out \| hit | inf (the cohort's mix) |
| 5 | HR \| 1B | inf (the cohort's mix) |

Inside each branch, two-way splits run in order of increasing k (the most
individual outcome first).

**These k are smaller than they used to be, and that is the mixing.** Reading
one card or the other (section 4) is itself a form of shrinkage: a batter's card
is only read 58% of the time, so a card built to be mixed can afford to keep
more of the player's own record than a card read alone. k and the mixing weight
therefore cannot be fitted separately, and were fitted together by coordinate
descent on runs from six starting points, all converging to the same place
(`joint_runs.py`). Against the v0.3.0 values: batter step 1 fell 64 to 16, the
HR step 4 to 2, the BB \| HBP step 8 to 2.83 and the 1B step 64 to 45 (the K
step held at 16); the pitcher's K step fell 32 to 1, his free-pass step 1024 to
64 and his BB \| HBP step 16 to 2.83. The cards are sharper and the mixture puts
the smoothing back.

**The BB \| HBP step is fitted on log loss, not runs** (the exception in section
9.0): a walk is worth 0.45 runs and an HBP 0.49, so runs cannot see the split
and a runs search returns whatever the grid order gives. There is also no reason
the two sides should share a value -- a batter's walk/HBP mix and a pitcher's
are different quantities with different amounts of signal behind them -- so the
whole 18x18 grid was searched with both sides free. It returned 2.83 on both
independently; the best shared value costs +0.000, so the shared number here is
a result, not a simplification. (`split_k_final.py`)

**Where the k column comes from:** each step's k is the best held-out score
(section 9.0) on a grid of powers of sqrt(2) from 1 to 2048, plus inf, scored at
the mixing weight the cards are actually read at. The best score is used; there
is no tie rule. **DECISION (user, 18 Sep).**

### 3.2 Cohorts

- Ranked by usage, never by performance (a performance ranking is circular):
  batters by share of team games started, pitchers by share of team batters
  faced. **DECISION (user, 17 Sep).**
- Share is measured over the player's tenure with each team; a traded player's
  tenure splits at her first game for the new team. **ASSUMPTION.**
- Cohort = nearest players by share, excluding her, until they total 250 PA
  (batters) or 250 BF (pitchers). Tied players enter together, so the 8
  everyday starters form one group, and the cohort a player actually gets is
  usually larger than the target (median 360 PA for batters at a 250 target).
  **DECISION (user, 20 Sep).** Tested (nested) on 150 / 200 / 250 / 300 / 350 /
  400 / 500 / 600: batters dip to a minimum at 250 (-344, SE 204, against 300)
  and rise on both sides; pitchers are flat from 250 up and worse below it. One
  size serves both, since 250 costs pitchers nothing (+77, SE 162). The 250 edge
  is 1.7 SE and is the best of seven comparisons, so it locates the optimum at
  roughly 250-400 rather than proving 250.
- Absences (jobs, exams, injury) count as non-use: box-score rosters list
  everyone, so availability cannot be measured.

### 3.3 Sluggers

Benites and Whitmore (12 HR each; next best 5; both homer on 20.7% of balls in
play against 3.0% for other everyday starters) are a named exception. At the
step that splits off home runs, each is smoothed toward the other plus Lansdell
and Mackay, and neither is in anyone else's cohort for that step. Without them
the rest of the league shows no measurable HR spread. **DECISION (user,
17-18 Sep).**

### 3.4 How k and the structures were chosen

- **k:** section 3.1. Each step's k is the best held-out score (section 9.0) on
  a grid of powers of sqrt(2), fitted jointly with the mixing weight.

  **Refitted on all 39 games (23 Sep, `joint_runs.py`), and the shipped values
  stand.** Coordinate descent on runs from six starts moves four of the five
  batter constants and four of the five pitcher constants to a common point that
  differs from what ships -- batter step 1 from 16 to 128, step 2 from 2 to 11.3,
  step 5 from 45 to 90.5, pitcher step 2 from 64 to 32. But **runs cannot see the
  difference**: all six endpoints span 1.3 units out of 396,407, a relative spread
  of 3e-6, across constants differing by eight to sixteen times. Swept against the
  weight at a fixed 0.375, the refit is about 250 runs-units better (0.35 SE) and
  2.2 log-loss units worse (0.6 SE) -- two non-significant edges pointing opposite
  ways. There is no case for changing them.

  **The BB | HBP k is not identified by runs at all.** It is the only constant the
  descent leaves wherever it started -- 2, 16, 256 or 2.83 depending on the start
  -- because a walk and a hit-by-pitch are worth almost the same in runs. Log loss
  ranks those leftovers 2.83 (1629.56) then 16 (1629.91) then 2 (1630.57) then 256
  (1633.54), so the shipped 2.83 is the best of them. That reproduces
  `split_k_final.py` from a completely different direction, and it is why that
  step was settled on log loss in the first place.
- **Structures:** compared by nested cross-validation, where k is tuned only
  inside each build half. Results are held-out runs error, x1e-6 per PA:

| Comparison (batters) | Difference (SE) |
|---|---|
| per-line smoothing (8 k, renormalized) minus 4-step tree | +159 (316): tie |
| chain (HBP, K, BB, HR \| contact, hit \| fielded, 2B \| 1B, ROE \| out) minus tree | -169 (413): tie |
| true outcomes first, then increasing-k chains (8 lines) minus chain | **-360 (193)** |
| true outcomes first, other branch orders minus chain | +129 to +290: chain better |
| free pass, HR \| K+FP then K \| FP (above) minus the 8-line version | -78 (79): tie |
| free pass, FP \| K+HR or K \| FP+HR minus the 8-line version | -19 (163), +49 (163): tie |
| HR grouped with hits minus chain | +272 (357): chain better |

  For pitchers, every chain tried ties or trails the tree (pitcher-ordered
  chain -66 (111), then +137 (142) with fresh splits). Only strikeouts are a
  stable pitcher skill, so the extra splits have nothing to work with.

- **Where the batter structure came from:** a correlation analysis of players'
  true rates (sampling noise removed, relative to cohort) put HR, K and HBP on
  the opposite side from Out and 1B (HR-Out -0.64, 90% interval -1.38 to -0.28;
  K-Out -0.58; HBP-Out -0.48; HR-1B +0.22, not negative). That suggested
  splitting true outcomes from fielded outcomes first. **(user, 18 Sep).** The
  order inside each branch follows increasing k (most individual first).
  Grouping HR with hits instead, the other reading of the same correlations,
  lost to the chain.
- **Why it works:** the true-outcome rate is among the most stable batter
  traits (tuned k about 16, middle half 6-45). Once that total is smoothed,
  the mix inside it needs little smoothing (HR \| K+FP about 7, middle half
  3-11; K \| FP 11, middle half 8-45). With walks and HBP as one free pass,
  testing all three places for it confirmed the increasing-k order.
- **Caveats:** the correlations and the in-branch order used all training games,
  including those later scored. A rule that picks the most reliable split
  automatically, fully inside each build half, ties it (+180, SE 252) but picks
  a different structure in every half. So this structure is among the best and
  interpretable, not proven best.
- **Correlations are only readable between lines with real spread:** where a
  line's true spread is small beside its sampling noise (batter BB, 2B, ROE;
  every pitcher line but K and BB), the estimate divides noise by noise and can
  exceed +/-1.
- **Only the hits-on-balls-in-play decision is sharp:** it is the most
  luck-driven rate and the one that moves the top hitters. Pitchers get their
  cohort's hit mix and little individual in-play hit rate, matching the
  standard defense-independent pitching finding.
- **The structure tests in this section predate two changes** and have not been
  rerun: 2B and ROE left both trees to become league bands, and walks and
  hit-by-pitches split back apart. Both changes remove or subdivide steps rather
  than reorder branches, and branch order is what these tests compared, so the
  conclusions are carried forward rather than re-established. **ASSUMPTION.**

### 3.5 What the cards look like

Runs above an average PA, x1000:

| | Raw | Card |
|---|---|---|
| Benites | 356 | 285 |
| Whitmore | 172 | 194 |
| Lansdell | 187 | 123 |
| Jorge | 128 | 93 |

- Spread among the 46 batters with 25+ PA: 125 raw, 80 on cards.
- Home runs the batter cards produce: 69.3 against 69 actual. The printed cell
  table gives 71.3 (section 4.1). **OPEN:** whether cards must preserve league
  totals.
- **OPEN:** optional fan-facing "replay" cards with k shifted toward raw.

### 3.6 What was tested (don't retest without new data)

Every alternative tried, with its result. Scripts are in `analysis/dice/` (see
its README). "Nested" results are held-out runs error, x1e-6 per PA, SE in
parentheses, against the comparison named; rows scored on log loss instead say so.

| Area | Tested | Result | Script |
|---|---|---|---|
| Target | one league average | flattened regulars; overrated bench (low-PA batters strike out 16.5%, homer 0.4%) | `recon.py` |
| | halves of PA, straight line between (quartile anchors) | rates not linear in PA (K steps down after the bench; HR jumps at the sluggers) | `followups.py`, `deciles.py` |
| | sliding cohort ranked by PA share | sorts everyday players by lineup spot | `cohort_cards.py` |
| | ranked by quality (context-neutral runs, FIP) | not run: circular | |
| | cohort 150 / 300 / 600 | batters: 150 worse by 2.3 SE, 600 no better; pitchers insensitive. Too coarse: it steps over the minimum | `cohort_cv.py` |
| | cohort 150 / 200 / 250 / 300 / 350 / 400 / 500 / 600 | batters bottom out at 250 (-344, SE 204 against 300); 200 -232, 350 -144, 500 +252, 600 +238. Pitchers flat from 250 up (250 +77, SE 162), worse below (200 +350, 150 +747). **250 chosen for both** | `cohort_grid.py` |
| | k re-tuned at the 250 cohort | 4 of 10 step k values moved: batter true outcomes 45 to 64, K-vs-FP 11 to 23, Out-vs-2B+ROE 181 to inf; pitcher FP-vs-in-play 256 to 1024, Out/ROE/hit 256 to 512. The d10 split k is unchanged (batters 8, pitchers 16) | `retune_k.py`, `split_k.py` |
| k | method of moments (15 Sep spec) | k = inf replaced whole lines (batter BB, 2B, ROE) though real spread is plausible | `k_uncertainty.py` |
| | smallest k within 2 SE of best (never a user rule) | near-raw cards for tiny samples | `k_cv.py`, `k_best.py` |
| | smallest k within 1 SE | little gain; only flat steps can move | `k_cv2.py`, `k_best2.py` |
| | best k on a sqrt(2) grid | **chosen** | `trees_cv.py`, `tto_c.py` |
| Batter structure | per line, outs as the remainder | filled holes (Whitmore 160 -> 204); erased Lansdell's walks and doubles | `k_best2.py` |
| | per line, outs a line, renormalized | tie with 4-step tree: nested +159 (316) | `lines_cv.py`, `nested2.py` |
| | 3-step and 4-step trees | tie; hit-mix k unstable (median 3.4, middle half 1-4096) | `tree4_cv.py`, `trees_cv.py` |
| | hybrid (own k per outcome within tree steps) | worse than tree: +104 (112); unstable k | `hybrid_cv.py` |
| | K/BB/HBP/in play, then Out/ROE/HR/1B/2B (with or without K split first) | tie with 4-step tree | `trees_cv.py` |
| | chain: HBP, K, BB, HR \| in-park, hit \| fielded, 2B \| 1B, ROE \| out | tie with tree: -169 (413); stabler k | `chain_cv.py` |
| | chain with HR grouped with hits | worse than chain: +272 (357) | `cchain_cv.py` |
| | true outcomes first; K \| rest orders (A1, A2) | worse than chain: +246 (291), +129 (292) | `tto_cv.py` |
| | true outcomes first; HBP, K, then HR \| BB (B) | worse than chain by 1.6 SE: +290 (184) | `tto_cv.py` |
| | true outcomes first; increasing-k branches | **better than chain by 1.9 SE: -360 (193); chosen** | `tto_c.py` |
| | automatic most-reliable-split-first | tie with chosen structure: +180 (252); a different structure in each of 40 halves | `greedy_cv.py` |
| Sluggers | protected vs treated like everyone | protected leans better (0.9 SE) and keeps league HR near actual | `tree_compare.py` |
| Lines | 1B and ROE merged | worse by 2.4 SE: +58 (24) | `merge_log5.py` |
| | BB and HBP merged into a free pass | no worse on runs: -81 (71); chosen 19 Sep, **reversed 21 Sep** -- runs cannot see this split at all, and the two lines want opposite cards (section 2) | `merge_log5.py`, `freepass_cv.py` |
| | free pass split by a league-wide d10 instead | loses batters' walk / HBP mixes (Jorge's HBP 16.2% -> 5.7%); moot now that each is its own line | `replayness.py` |
| Out flavors | rating batters on the + (does her out advance a runner) | no real spread either way: measured directly, SD 0 (90% 0 to 0.105, 19 batters, 187 chances); from her out-type mix, 0.028 (0 to 0.046, 19 batters, 562 outs). A + is worth 0.331 runs and a batter gets about 13 chances a season, so even the top of the range is 0.2 runs. **Stays league-wide** | `out_plus.py` |
| Pitcher structure | 4-step tree (free pass at step 2 since 19 Sep: tie, -8 (11)) | **chosen** | `trees_cv.py`, `freepass_cv.py` |
| | chain ordered HBP first | worse than tree by 1.5 SE: +252 (169) | `chain_cv.py` |
| | chain ordered K first | tie: -66 (111), +137 (142) | `pchain_cv.py`, `cchain_cv.py` |
| | K first, HR grouped with hits | tie with K-first chain: +16 (52) | `cchain_cv.py` |
| Combination | additive, flat log5, two-level log5, averaging | three tie within 0.7 SE; averaging halves player differences. Superseded by the mixture | `combine_fullpos.py` |
| | **mixture: the d100 picks which card to read** | better than no mixing by 4.5 SE (17.9), and beat flat log5, the additive shortcut and every zero-sum shift. **Chosen** | `mixture.py` |
| | compensated cards (print B' so the mixture reproduces B exactly) | rejected: B' is not a printable distribution for ordinary players | `mixture.py` |
| | one mixing weight per line, ignoring sum-to-100 | walks want the pitcher (0.70), HBP the batter (0.20) -- the diagnostic that split the free pass back apart | `mixture_per_line.py`, `mixture_eight.py` |
| | ten bins of 10%, a weight each (a superset of one weight) | never beat a single weight, across three layouts | `bins.py`, `bin_alpha.py`, `bin_nested.py` |
| | k re-fitted given mixing, then k and the weight jointly | six starts converge to one point; k falls sharply (section 3.1) | `k_given_mixing.py`, `joint_runs.py` |
| | the weight swept under both metrics | runs bottom near 0.15-0.20, log loss near 0.375-0.43; both curves flat enough that neither excludes the other | `alpha_sweep.py`, `alpha_cost.py` |
| | 35 / 5 / 2 / 58 cells (weight 0.3763) | **chosen**: the round-number point inside that range | `layout_cells.py`, `layout_round.py` |
| Bands | 2B and ROE on a card vs a flat league rate | no real spread on either side; flat beats the batter's own 2B record by 3.9 SE and the pitcher is worse still | `line_owner.py` |
| | flat 5% and 2% vs the measured 4.54% and 2.32% | round levels no worse and nominally better (log loss x1000 -0.151, SE 0.348; -0.236, SE 0.308). **Chosen: 5 and 2 cells** | `band_two_level.py` |
| | a flat band plus a marked bonus group, chosen inside each build half | worse at every bonus size (+0.017 to +1.088): it sorts noise | `band_two_level.py` |
| Rounding | largest remainder | lets Out absorb every rounding error | `layout_round.py` |
| | nearest, then spend the difference where \|run error\| is smallest | **chosen** | `layout_round.py` |
| | one-cell floor on both sides | league HR inflated 16%: 42 of 67 batters are owed under a tenth of a cell | `hr_floor_options.py` |
| | one-cell floor on pitchers only | costs 2% on league HR and closes every hole by itself. **Chosen** | `hr_floor_options.py` |
| | sub-cell lines sharing one cell in twelfths | more work at the table than the error it saves | `hr_floor_options.py` |
| | no floor at all | 47 batter entries and 5 pitcher entries at zero; some matchups cannot produce a home run | `hr_floor_options.py` |
| Handedness | RE24, situational and state-demeaned, against the context-neutral outcome mix | outcome mix identical (-0.002, 0.07 SE); only situational timing differs (+0.035, 1.08 SE). Detectable effect is 0.7 SD of the batter population, so: no evidence, not no effect | `handedness_re24.py` |
| Handedness | a platoon adjustment, fitted on held-out games at five strengths | worse than none on runs at every strength: +75.8 (SE 25.5) at quarter, +405.8 (SE 101.9) at full. The walk/HBP split, the one axis with a story, is 1.0 SE better at best. **No platoon mechanic** (section 5) | `handedness.py` |
| BB \| HBP k | one shared value for both sides | the full 18x18 grid returns 2.83 on each side independently; the shared value costs +0.000, so it is a result, not a simplification | `split_k_final.py` |

## 4. Combining pitcher and batter: the d100 table

**DECISION (user, 21 Sep).** One d100 resolves a plate appearance. Its hundred
cells are split into fixed blocks:

| Cells | Read | Size |
|---|---|---|
| 00-32 | the **pitcher's** card | 33 cells |
| 33-38 | **running play** | 6 cells |
| 39-40 | **reached on error** | 2 cells |
| 41-44 | **double** | 4 cells |
| 45-99 | the **batter's** card | 55 cells |

**The order inside those middle twelve cells follows the rulebook, not the other
way round (23 Sep).** The rulebook's Matchup Table and its own quick reference had
disagreed about which rolls were doubles, and the code agreed with the quick
reference; the user's call was to align the code to the Matchup Table. Only WHICH
roll produces which band changed -- the counts, and so every probability, are
untouched. `rules_check.py` now checks all 100 rolls so it cannot recur.

Each card spreads its own block over its six printed lines, so a roll lands in
exactly one cell of exactly one card and the player reads the line off it. No
arithmetic, no lookup table, no second roll to decide whose card to use.

**The running-play block is the odd one out.** A wild pitch, passed ball or balk
advances every runner and the roll is then *taken again*, so those six cells do
not resolve a plate appearance at all (section 6). A card is therefore a
distribution over the **94 cells that do end a plate appearance**, not over all
100, and the bands divide by 94: doubles at 4/94 = 4.26% and errors at 2/94 =
2.13%, against measured rates of 4.54% and 2.32%. With the bases empty the block
is a plain reroll, about once every 43 plate appearances.

**Reading one card or the other is the combination rule.** The mechanic is a
mixture:

    p = a * (pitcher's card) + (1 - a) * (batter's card)

with a = 33 / (33 + 55) = 0.375 exactly, the pitcher's share of the cells that
are neither a band nor a running play. It sums to 100% because exactly one card is read, and it gives every
line its trade-off for free: each card is already a distribution, so a batter
with more singles has less of something else.

On held-out games the mixture beat no mixing by 17.9 in runs error, 4.5 SE, and
also beat flat log5, the additive shortcut (league plus both deviations) and
every zero-sum shift (`mixture.py`). That closes the 19-20 Sep open question,
where additive, flat log5 and two-level log5 tied within 0.7 SE and nothing
could be chosen between them.

**What it costs.** A mixture can never be more extreme than either card, while a
real matchup of two extremes compounds. That is why the cards are built sharper
than they used to be (section 3.1): the mixing supplies the smoothing, so k does
not have to. Printing compensated cards instead -- B' = (B - aP) / (1 - a), so
that the mixture reproduces the batter's true card exactly -- was tried and
rejected: B' is not a printable distribution for ordinary players.

**Why one weight and not several.** Asked line by line, the lines disagree:
walks want 0.70 and hit-by-pitches 0.20 (`mixture_per_line.py`). That diagnostic
is what split the free pass back apart, but it ignores the sum-to-100
constraint, which the block layout restores. Giving the d100 ten bins of 10%
with a weight each -- a strict superset of one weight -- never beat one weight,
across three layouts (`bins.py`, `bin_alpha.py`, `bin_nested.py`). A bin whose
two cards hold lines of the same run value has an unidentified weight, and the
fit returns whatever the grid order gives (section 9.0).

**Where 0.3763 came from.** The two metrics put the weight in different places:
runs bottom near 0.15-0.20, log loss near 0.375-0.43, and both curves are flat
enough that neither excludes the other (`alpha_sweep.py`, `joint_runs.py`).

**That sentence was measured on a k set that was never shipped** (found 23 Sep).
`alpha_sweep.py` copied its constants instead of importing them, and the copy had
drifted: it swept `[11.3, 1, 8, 8, 32]` under a label reading "in dice.py now"
while dice.py shipped `[16, 2, 16, 2.83, 45.25]`. The script now reads them from
`wpbl.dice` at import, so it cannot drift again.

**Re-swept at the SHIPPED constants on all 39 games**, and the shape is the one
the choice was made on: **runs barely cares and log loss does.**

| metric | best weight | depth of the bowl | SE | verdict |
|---|---|---|---|---|
| held-out runs | 0.30 | 703 | 725 | under 1 SE: cannot choose |
| log loss | 0.40 | 18.06 | 3.62 | 5 SE: genuinely discriminates |

So the weight is set by log loss, and log loss has a flat bottom between about
0.35 and 0.45 -- 1617.02, 1616.76, 1616.86 at 0.35 / 0.40 / 0.45 -- rising away on
both sides. **0.375 sits in that bottom**, which is why it was a reasonable
compromise and still is. Runs is along for the ride: its own minimum is 0.30 and
its 1-SE band runs 0.00 to 0.55, so it excludes nothing.
Within that range the user chose the value that makes the cells round. The
running-play block later forced the split to be redrawn (section 6), and 33 / 4 /
2 / 6 / 55 lands the weight on 33/88 = 0.375 exactly -- a move of 0.003, far
inside the flat region, so the k were not refitted. **DECISION (user, 21 Sep).** A parameter this flat is a choice inside a range, not a
measurement (section 9.0).

**The bands.** 2B and ROE sit on neither card because neither shows real spread
on either side: a flat league rate predicts held-out doubles better than the
batter's own record by 3.9 SE, and the pitcher's record is worse still
(`line_owner.py`). Printed at 5 and 2 cells against measured rates of 4.54% and
2.32%, the round levels score no worse and nominally better (log loss x1000:
-0.151, SE 0.348 for doubles; -0.236, SE 0.308 for errors). A two-level version
-- a flat band plus a marked group of doublers getting one extra cell, the group
chosen inside each build half -- is worse at every bonus size, which is what a
flat band should do to a sort of pure noise (`band_two_level.py`).

### 4.1 Turning a card into cells

For each side, over that side's six printed lines:

1. scale the card to the block size (55 or 33);
2. round each line to the nearest whole cell;
3. **pitchers only:** raise any line to at least one cell;
4. if the cells do not sum to the block, add or remove them one at a time, each
   time wherever the card's **run value** ends up closest to the unrounded card.

Step 4 is the point of the rule. Giving the leftover cells to the largest line
lets Out absorb every rounding error, which is the same mistake as letting Out
give back the mixing offset. Largest remainder, the classic rule, has the same
flavour of problem (`layout_round.py`).

**Why the floor is one-sided.** A line at zero cells on *both* cards cannot
happen at all in that matchup, which no amount of smoothing intended. Flooring
both sides is ruinous: 42 of 67 batters are owed less than a tenth of a cell of
home runs, so giving each of them a whole one inflates the league by 16%.
Pitcher cards take the cohort's mix on two of their five steps, so they sit near
league rates and only five entries in the whole pitcher set round to zero;
flooring those costs 2% on league home runs and closes every hole on its own,
because pitcher plus batter is then always at least one cell. The pairwise
alternative -- fix a line only where both sides are zero -- is unnecessary once
the pitcher side can never be zero. **DECISION (user, 21 Sep).**
(`hr_floor_options.py`)

**As built** (39 games, `pixi run dice`): every pitcher card fills its 33 cells
and every batter card its 55; no pitcher entry is at zero and 47 of 402 batter
entries are; **0 of 2,479 matchups have a line that cannot happen**; the table
gives 71.3 league home runs against 69 actual.

**The 1% floor** applies once, to the combined distribution, after the two cards
are put together -- never to a card (section 3).

## 5. Handedness

Handedness rides on every batting and pitching row (`parse.py`, modal per
person; the feed contradicts itself for 10 of 80 players). The league is 54
right / 17 left / 2 switch at the plate, 61 right / 12 left on the mound. Of
2,798 plate appearances, 1,762 are same-handed and 1,036 opposite (switch hitters
counted as opposite).

**DECISION (22 Sep): the game has no platoon mechanic.** Handedness is recorded
and carried in the data, and nothing on the table or the cards reads differently
for it.

That reverses the earlier design, which put platoon cells on the K/out and
out/single boundaries. It was never tested the way every card choice is tested;
when it was, it failed.

**The gaps did not survive the data growing.** On 36 games the spec quoted K
2.5 points, hits 2.1 and BB+HBP 0.9. On 37:

| line | opposite - same | SE | gap / SE |
|---|---|---|---|
| HBP | -1.62 | 0.70 | -2.31 |
| BB | +2.64 | 1.36 | 1.94 |
| K | -1.35 | 1.28 | -1.05 |
| 1B | +0.91 | 1.64 | 0.55 |
| OUT | +0.72 | 1.97 | 0.37 |
| HR, 2B, ROE | under 0.5 | | under 0.9 |

The K gap halved, the hits gap vanished (+0.10 across 1B, 2B and HR) and BB+HBP
flipped sign. The two lines the mechanic was built on are now the weakest, and
with eight lines tested a largest |z| of 2.31 is not significant.

**And an adjustment predicts held-out games worse, at every strength**
(`handedness.py`). The baseline is the mixture of the two cards, which already
knows each player's own rates; a platoon shift has to earn its keep on top of
that by predicting the part that depends on the matchup. Fitted on the build
half, shrunk toward zero by a factor, and scored on the other half, with cards
rebuilt per fold so neither side sees the test games:

| strength | runs error, vs none | log loss, vs none |
|---|---|---|
| 0.25 | +75.8 (SE 25.5) | -0.004 (SE 0.265) |
| 0.50 | +168.8 (SE 51.0) | +0.510 (SE 0.544) |
| 1.00 | +405.8 (SE 101.9) | +4.919 (SE 1.467) |

Worse on runs at 3.0 SE even at quarter strength, and 4.0 SE at full.

**The one axis with a physical story is the one runs cannot see.** BB and HBP
move in opposite directions, so the free-pass total barely shifts (+1.01) while
the split inside it shifts a lot: hit-by-pitches are 26.2% of free passes in
same-handed matchups and 15.0% in opposite, which is what a breaking ball
running in on the batter would do. Scored on log loss, as section 9.0 requires
for a choice between outcomes of near-equal run value, it is 1.0 SE better at
best (-2.40, SE 2.44, on 430 free passes). Not enough to print.

**RE24 agrees, and sharpens it** (`handedness_re24.py`). The line-by-line test
asks eight noisy questions; RE24 asks one, so it has far more power per plate
appearance. Same minus opposite: situational RE24 +0.0349 (SE 0.0322), the same
with each base-out state's mean removed +0.0350 (SE 0.0325), and the
context-neutral run value -0.0021 (SE 0.0293). The last is the informative one --
**the outcome mix is identical**, and what little RE24 difference exists is in
when those outcomes happened, not what they were. A card produces outcomes and
the game supplies the situation, so there is nothing there for a card to carry.
(The situations do differ slightly: same-handed matchups sit in states worth
+0.042 runs before the play, 1.30 SE, which is what bringing a same-handed
reliever into a tight spot would look like.)

**What these tests can and cannot say.** Two SE on the RE24 test is 0.059 runs
per plate appearance, and section 3.5 puts the spread across batters with 25+ PA
at 0.080 on cards -- so the smallest platoon effect detectable here is about 0.7
SD of the entire batter population. That rules out a split the size of the gap
between an average and a good hitter; it does not rule out an ordinary one. So
the finding is **no evidence**, not **no effect**.

The decision rests on the stronger half of the evidence rather than on the
absence: a mechanic has to earn its complexity, and acting on the measured gaps
made held-out predictions worse at every strength. **ASSUMPTION.**

**OPEN:** revisit when the league has more games. The HBP split is where to look
first, and it needs free passes rather than plate appearances, so it will be
slow to resolve.

## 6. Running plays and steals

- **The running-play line** covers wild pitches, passed balls and balks: 83 / 11
  / 18 = **112** in the 39 training games, 115 across all 40. Every runner
  advances one base, then roll again for the plate appearance. It owns **6 cells**
  of the d100 (section 4). With the bases empty it is a plain reroll, about once
  every 43 plate appearances. **DECISION (user, 21 Sep).**

  *Correction (23 Sep).* This line read "87 / 12 / 18 in the training games, 117
  in all". Those were the ALL-scope counts wearing a training label, and the rest
  of the paragraph then compared them against a training-scope denominator.
  Semifinal G3 is the difference: three wild pitches now, four plus a passed ball
  before its box score was re-parsed. **The training counts did not move when the
  last two games arrived** -- neither game had a running play in it.
- **Six cells, not the four "4.2% of rolls" implied.** Every play on record
  happened with a runner on, so the block is dead 39% of the time and has to be
  bigger to land the same rate. A running play also consumes its roll and you roll
  again, so a band of c cells yields c / (100 - c) plays per opportunity. Against
  the 1,696 plate appearances that began with a runner on:

  | cells | plays a season | against 112 actual |
  |---|---|---|
  | 4 | 70.7 | -41.3 |
  | 5 | 89.3 | -22.7 |
  | **6** | **108.3** | **-3.7** |
  | 7 | 127.7 | +15.7 |

  **Six is now the best fit on the raw count with nothing else assumed.** On the
  mixed-scope numbers seven fitted best and six needed the balk changepoint to
  justify it. On consistent ones six wins by a factor of four. Same decision,
  better footing.
- **It is on neither card.** Sweeping the smoothing constant, where k = inf *is*
  the flat band, the best k against the league is 1024 and beats the flat band by
  0.48 SE -- a tie. Smoothing toward the player's usage cohort instead is worse
  than ignoring pitcher identity altogether (log loss 99.5-99.9 against 98.27),
  because a cohort's own running-play count is too small to be a better target
  than the league rate. So the line joins doubles and errors as a fixed band.
  (`running_plays.py`, `running_k.py`)
- **What that result cannot say.** The feed records one of these plays only when
  it has a visible consequence -- all 115 describe a runner advancing or scoring,
  and the one wild pitch on record with the bases empty appears only because the
  batter reached on a dropped third strike. A pitch the catcher blocks never
  enters the data. So each pitcher's observed rate is her wildness times one
  minus her catcher's block rate, the two cannot be separated, and the part that
  was prevented is invisible. The spread is **censored, not absent**: what the
  test establishes is that at this sample size, on the quantity the game needs,
  no pitcher differentiation earns its place. **ASSUMPTION.**
- **The knuckleballer.** Liz Gilder threw 8 wild pitches in 287 pitches with a
  runner on, 2.79% against a league 1.34% -- twice the field, on eight events.
  Named here so it is revisited rather than lost in a null result, as the slugger
  exception was (section 3.3). Keira Izumi and London Studer sit higher still,
  but they are position players pressed into pitching by a league-wide shortage
  of arms, which is inexperience rather than a repeatable trait.
- **Balks and the umpire.** 18 balks, and the rate falls 4.1x after game 22
  (4.39 per 1000 pitches with a runner on, against 1.08), which is consistent with
  the mid-season replacement of an umpire who called them freely. Still not
  established, but the full season strengthened it rather than washing it out: the
  changepoint test that prices the search over all split points now gives
  **p = 0.094**, against 0.17 on 37 games.

  **No balk is discarded anywhere, and none ever was.** The band is a flat 6 cells
  (`dice.RUN_CELLS`) and all 18 are inside the 112 running plays it is fitted to.
  Nothing in the model filters by date, and because the line sits on neither card
  no pitcher carries a balk rate an umpire could distort. (The per-pitcher balk
  test is unaffected for the same reason it was always safe: a trigger-happy
  umpire would ADD spurious spread between pitchers, and none was found -- real
  SD 0.18, 90% interval 0.00 to 0.44.)

  **DECISION (user): estimate the balk rate from AFTER the changeover**, not from
  the season as a whole -- the early games, the ones carrying two balks apiece,
  are the umpire and not the league. Applied across the season that gives 1.08 per
  1000 pitches with a runner on, or about 6.6 balks, for 100.7 running plays.

  | treatment | plays a season | best band |
  |---|---|---|
  | **post-change rate applied all season (chosen)** | **100.7** | **6** (+7.6) |
  | keep every balk | 112 | 6 (-3.7) |
  | drop balks entirely | 94 | 5 (-4.7) |

  **Six cells either way**, which is what makes the decision safe rather than
  load-bearing: the chosen estimate and the do-nothing one agree, and only
  pretending balks never happen -- when three were called after the changeover --
  would give five. On the old mixed-scope numbers the chosen estimate was the only
  thing getting to 6, because keeping all 117 gave 7; now it is the choice and the
  robustness check both. **Re-checked 23 Sep.**

  The separate question of whether balks BUNCH into particular games -- the same
  umpire theory read a different way -- is still nothing: 18 balks over 39 games
  have variance 0.47 against a mean of 0.46, and a Poisson process is this
  clustered or more 42% of the time.
- **Steals are a decision, not a line.** The offense declares before the roll;
  only the resolution is random. 133 attempts, 112 successful.
- **A league-rate stand-in exists for the validation only** (`engine.steal`),
  because a check that never steals reproduces only the half-innings nobody stole
  in. Attempts per plate appearance by state: `1__` 0.145, `1_3` 0.370, `_2_`
  0.047, `12_` 0.035; success 83% stealing 2nd, 88% stealing 3rd. Re-measured on
  the full season (23 Sep) those come to 0.142, 0.375, 0.046, 0.036 and 84% / 86%
  -- inside rounding of what is shipped, so the constants were left alone. It
  resolves
  **after** the plate appearance, not before: a steal happens during the next
  batter's turn and the feed files it between the two, so rolling it first puts
  it in the wrong transition and leaves the batter who singled and stole standing
  on 1st. That was a real bug and it cost two thirds of the engine's transition
  error (section 9.1).
- **The catcher is the variable worth modeling:** runners went 60% against
  Benites and 90% against everyone else; NYH threw out 35% against 4-15%
  elsewhere. **OPEN**: catcher rating scale, and whether runner speed is
  modeled at all (probably not; it needs more data than exists).

## 7. Fatigue

The game's central mechanic, and the least supported by data.

- **Pitch counting comes free from the outcome line.** Measured pitches per
  result: walk 5.4, strikeout 4.9, out 3.3, hit 3.2, hit by pitch 3.1. A track
  advances by the line's cost, so a strikeout-and-walk pitcher tires faster.
  Walks and hit-by-pitches are separate lines now (section 2), so each carries
  its own cost directly.
- **Usage targets to reproduce:** starts average about 70 pitches, relief about
  35; the median 7-day load is 45 pitches for relief-only weeks and 85 for weeks
  with a start.
- **Fading columns.** **ASSUMPTION**: a pitcher card carries fresh / fading /
  gassed columns; the pitch track selects one; fading columns shrink K and widen
  BB and contact. This keeps fatigue to one dial with no extra roll.
- **What the data cannot say — measured, 22 Sep (`fatigue.py`,
  `fatigue_from_end.py`).** A within-appearance decline *is* detectable, but only
  when the appearance is aligned on the REMOVAL rather than on the first batter,
  and only when a pitcher is compared with herself. Aligning on the start and
  bucketing by pitches finds nothing (below); the paired end-aligned test finds
  **+0.078 runs per batter faced (SE 0.035, 2.2 SE)** in the inning before she was
  pulled against her own first inning -- with the inning the removal happened in
  excluded, so it is not the collapse that triggered the decision. That inning,
  for reference, is +0.192 (4.8 SE).

  **Why the alignment matters.** Aligning on the start puts only survivors in the
  late buckets. Aligning on the end and pooling inverts the bias -- "four innings
  before removal" exists only inside long outings, which are the good ones -- so
  the test has to be *paired*: her first inning against her penultimate one,
  inside one appearance, which holds the outing's length and the pitcher both
  fixed.

  **Fatigue, or a manager reacting to bad luck?** Not resolved. The inning before
  removal is selected on having just pitched badly, which is what makes a manager
  act, so luck plus a quick hook produces the same result. They separate on one
  prediction -- fatigue should bite harder when more pitches have been thrown --
  and it is directionally supported but thin: outings of 45 pitches or fewer show
  -0.004 (SE 0.136, 14 outings), 46-70 show +0.116 (SE 0.050), 71+ show +0.054
  (SE 0.055). The short bucket is the decisive one and cannot tell -0.004 from
  +0.12. **OPEN.**

  The start-aligned cuts find nothing. Conditioning on survivors -- comparing a
  pitcher's early and late batters only within appearances that reached a given
  depth, so the manager's decision no longer picks who is in the late bucket --
  the two available cuts **disagree in sign**, each at about 1 SE:

  | cut | early | late | difference |
  |---|---|---|---|
  | pitches, among appearances reaching 50+ | -0.0274 | -0.0619 | -0.034 (SE 0.034) |
  | times through the order, among those reaching 2x | -0.0425 | -0.0125 | +0.030 (SE 0.032) |

  **The pitch cut needs a control the obvious version omits.** A pitcher's first
  25 pitches face the top of the order and her next 25 the bottom, so without
  removing the batter's own expected value every pitcher appears to improve. The
  numbers above already subtract it; doing so shrank the times-through effect
  from +0.036 to +0.030 and did not flip the pitch cut, so lineup order is not
  the whole of the disagreement.

- **The fatigue that is visible is between games, not within one.** Semifinal G3
  (14 Sep), excluded from training precisely because both bullpens were spent, is
  the only clean observation: 86 plate appearances at +0.0878 run value allowed
  per batter faced against a league -0.0433, a gap four times the standard error
  of anything measurable within an appearance. Its shape is section 7's predicted
  tired signature -- **K 7.0% against 11.8%, HR 5.8% against 2.6%, 2B 8.1%
  against 4.5%** -- strikeouts collapsing and extra-base contact doubling.

  But within that game more pitches did *not* mean worse: the 83-pitch outing was
  comparatively fine (+0.068) and the worst were 42 and 54 pitches (+0.287,
  +0.229). What it shows is a bullpen tired across days. The same axis measured
  league-wide is the largest signal anywhere in this work and still not
  significant: pitchers who threw 25+ pitches in the prior three days allow
  +0.049 against -0.026 for the rested, a 0.075 gap at about 1.65 SE. Prior-seven-
  day load and days of rest show no monotone pattern at all.

- **A usable magnitude, at last.** The paired result gives roughly **0.08 runs
  per batter faced by the inning before a manager acts**, which is something to
  tune against rather than a blind setting. It is an upper bound on fatigue
  proper, since some of it is the manager reacting to luck.

- **So the mechanic takes its shape from G3 and its size from tuning.** The track
  should carry workload **across days**, not reset each outing, which is what the
  usage targets above already describe; the fading column should shrink K and
  widen extra-base contact rather than walks alone. **OPEN**: the size, the daily
  recovery, and whether a within-appearance component is worth having at all.
  Recovery cannot be fitted: the prior-three-day load carries the signal and the
  prior-seven-day load shows no monotone pattern, which hints most recovery
  happens inside three days, but 18 appearances in the loaded bucket cannot
  support a curve.

- **The published in-game rules are not supported here** (`pitcher_state.py`).
  Deadball and History Maker Baseball both carry state rules alongside workload
  ones; scored as a residual against the matchup -- both cards, so neither who
  batted nor who pitched can be credited -- none of them appears:

  | rule | test | result |
  |---|---|---|
  | STRUGGLER (HMB) | after n consecutive batters reach base, is the next worse? | 0 on -0.013, 1 -0.019, 2 **-0.072**, 3+ -0.025. Non-monotone; the two-consecutive bucket is the best of the four |
  | ACE (HMB) | a reliever entering mid-inning, on her first batter | -0.037 on 34 BF against -0.029 for her later batters |
  | FRESH / SEMI-FRESH (HMB) | a starter's innings 1-3 against 4-6 | -0.011 against -0.033: later looks *better* |

  So a pitcher who cannot get anyone out in a third of an inning is not in a
  persistent state the next batter inherits -- on this data that is bad luck plus
  a manager reacting quickly. The manager pulling her biases the test toward
  zero, so the effect would have to be large to hide there. **ASSUMPTION.**

  HMB's tiers also do not map onto this league at all: a starter's seventh inning
  of work has **zero** plate appearances, because WPBL plays seven-inning games.

- **Pitch cost per line, and why it already does the work** a struggling rule
  would. Measured pitches: BB 5.40, K 4.92, HR 3.26, Out 3.23, 2B 3.18, 1B 3.08,
  HBP 3.05. Outs recorded cost 3.58 and reaching base 3.76, a gap of 0.17 --
  essentially nothing, and a single is *cheaper* than an out. Weighting outs
  lower would distort a measured quantity rather than refine it. It is also
  unnecessary: at 5.40 pitches a walk against 3.2 for contact, **the walk-prone
  pitcher already tires fastest**, and she is the pitcher who is not making
  progress. **DECISION (22 Sep): the track uses the measured costs.**

### 7.1 Starters and relievers

**A reliever throws nearer her ceiling.** Measured within the pitcher -- a card
pools her starts and her relief, so any comparison across pitchers is muted by
construction -- 13 of the 19 who did enough of both are better in relief, mean
**-0.058 runs per batter faced** (about 1.7 SE). Jaida Lee, who has described
the move from starting to relief herself, is among the largest: -0.177 in relief
against -0.024 starting. (`roles.py`)

**Whether she burns through it faster cannot be tested here.** By pitches thrown
relievers appear to *improve* -- -0.005 early, -0.068 at 25-49, -0.118 at 50+ --
which is survivorship, and worse for relievers than anyone, since a reliever
still in at 50 pitches is one who is dominating. The paired end-aligned fix needs
three innings, which relievers almost never reach: median 8 batters faced and 31
pitches, against 19 and 68 for a start. **The burn half is unfalsifiable on this
data.** Other games price it at about 3x. **ASSUMPTION.**

### 7.2 The system to build

**What the fatigue system is for.** Not to predict a pitcher's decline -- it is
to give the player a reason to take her out on roughly the schedule a real
manager would. That distinction decides everything below, because **managers
always pull, so what would have happened past the hook is never observed.** Any
curve out there is extrapolation and cannot be verified from play-by-play, now or
with ten more seasons. **DECISION (user, 22 Sep).**

Two ways to make a player act: a mechanism that deteriorates past the hook, or
one that forces the change on a trigger. **Deterioration**, as Deadball and
History Maker Baseball both chose -- a forced trigger removes the decision, and
the pitching change is the most interesting choice a manager makes.

**The curve is anchored across the whole working range** (`fatigue_curve.py`),
not just at its ends. Every figure is paired -- a pitcher against herself earlier
in the same outing, with her removal inning excluded -- so neither her quality nor
the outing's length can masquerade as fatigue:

| against her own first inning | runs per batter faced | |
|---|---|---|
| her 2nd inning | **+0.067** | 1.9 SE |
| her 3rd | **+0.095** | 2.4 SE |
| her 4th or later | +0.084 | 1.2 SE |
| the inning before a manager acts | +0.078 | 2.2 SE |
| the inning he acts in | +0.192 | 4.8 SE |

**The decline arrives early and then flattens.** It is a step of roughly +0.08
after the first inning, level thereafter, and then a spike when the manager acts
-- which is largely him reacting to a bad inning rather than the inning being bad
because she is tired. A mechanic that accumulates linearly with pitches would get
this shape wrong.

**An independent check with no cards in it at all** (`times_seen.py`). Comparing
the i'th time a batter has faced this pitcher in this game with her first holds
the matchup *exactly* fixed -- same batter, same pitcher -- so raw run values can
be differenced with nothing modelled away. Second meeting minus first: **+0.028
(SE 0.033)** over 831 pairs, and +0.031 restricted to outings of 3+ innings where
surviving to a second meeting was never in doubt.

That looks like a third of the innings figure and is not: **the times-seen clock
is compressed.** Only 59% of first meetings fall in the pitcher's first inning
(36% in her second, mean inning 1.47), while second meetings average inning 3.02.
A step of +0.09 taken after her first inning therefore predicts a penalty of
0.037 on first meetings and 0.089 on seconds -- a contrast of **+0.052**, not
+0.09. The measured +0.028 sits 0.7 SE below that. Inverted, this design alone
implies a step of +0.048 (SE 0.057). Consistent with the innings curve, and a
weaker instrument for it, since it can generate only about half the contrast.
Its value is that it corroborates the direction with no card, no residual and no
statistical control.

**Bucket by innings, never by pitches.** The same paired test bucketed by pitches
thrown says the opposite -- -0.085 at 25-49 pitches, -0.132 at 50-74, both about
2 SE -- and it is wrong. Pitches consumed depend on how badly she pitched: a
struggling inning is a long inning, so "her first 24 pitches" disproportionately
covers innings where she was struggling, and the next bucket regresses upward
from a baseline selected on bad performance. An inning is normalised by outs and
does not do that. This is why the start-aligned cuts in section 7 found nothing.

**Past the hook there is one observation and it is on a different baseline.**
Semifinal G3 ran +0.131 runs per batter faced *against the league*, not against
those pitchers' own earlier innings, and the pitchers in it were whoever was
left. It fixes the SHAPE of exhaustion -- K collapsing, extra-base contact
doubling -- and says the level out there is worse than anything inside the
working range, but it is not a point on the same curve and should not be read as
one.

**Every parameter, and where it stands:**

| parameter | status |
|---|---|
| base pitch cost per line | **measured**: BB 5.40, K 4.92, contact 3.05-3.26 |
| reach-base surcharge | **not needed** -- the compounding is already automatic (below) |
| capacity | **per pitcher**, not per role (section 7.4). Her own number, 44-100 over 38 arms, median 69.5 |
| daily recovery | **20 pitches a day** (user, 23 Sep, section 7.9). Superseded a 14 chosen on 22 Sep, which was set before the entry cost existed |
| degradation shape | **from G3**: shrink K, widen extra-base contact |
| degradation size | **+0.032 at gassed** (section 7.3). The innings step of +0.09 is an upper bound a card-only mechanic cannot reach without an absurd card |
| relief ceiling bonus | **about 0.06 runs per batter faced** (section 7.1) |
| relief burn multiplier | **none** (section 7.4): capacity carries it, and a 3x rate contradicts the observed rest rhythm |

**The feedback loop is already in a plain pitch count** (`pitch_tempo.py`). The
proposal was an *effective* count -- outs costing less, other results more -- so
that a struggling pitcher tires faster. Measured, **pitches per plate appearance
do not drift at all** over an outing: -0.13, -0.11, +0.00 against her own first
inning, every one inside a standard error, and the walk and contact rates are
flat with them. Each plate appearance costs the same whatever is happening.

What varies is BATTERS FACED. A PITCHER-inning averages 4.80 batters (SD 1.85)
and 17.6 pitches (SD 7.8), and a pitcher who cannot get outs faces more of them.
So a plain pitch count already burns faster for her, by the batter rather than by the
pitch -- the compounding arrives on its own, without a surcharge and without
distorting a measured quantity. **DECISION (22 Sep): the track counts measured
pitches, unweighted.**

**Measure in innings, implement in pitches.** The decline is measured per inning
because pitches are endogenous; the track counts pitches because that is the work.
The conversion is noisy -- a coefficient of variation of 0.44 -- so the step
should be applied on the track's own scale rather than by pretending an inning is
a fixed quantity of work. Batting around is rare
enough not to matter: 1.7% of innings face ten or more batters and 1.9% see a
batter twice.

### 7.3 What a fading column looks like

**One cell is 1/94 of a plate appearance, not 1/33.** Her block is only 35.1% of
the cells that resolve one; the rest is the batter's block and the bands. So
moving a cell from K to 1B -- a run-value gap of 1.214 -- is worth **+0.013 runs
per batter faced**, and K to HR is +0.023. (`tired_card.py`)

**That puts a hard ceiling on a card-only mechanic.** To move the *matchup* by
the +0.09 step, her *card* has to move by 0.09 / 0.351 = 0.26 runs a read,
against a league pitcher card worth -0.077. Scaling G3's own line mix far enough
to do it means multiplying that shift by 2.82 and moving 8 of her 33 cells, which
prints a card of K 1, BB 6, HBP 4, HR 4, 1B 5, OUT 13. Hit-by-pitches at 12% of
her card is not a tired pitcher.

**So +0.09 is the wrong target, and the other two estimates say so.** It is an
upper bound that includes the manager reacting to luck. The two that do not:

| estimate | runs per batter faced |
|---|---|
| innings step (upper bound, includes the manager's reaction) | +0.09 |
| times-seen design, inverted (section 7.2) | +0.048 (SE 0.057) |
| **G3's own line mix applied to her card** | **+0.032** |

**The columns.** Shifting the league pitcher card toward the G3 mix, rounded
with the same rule the cards use:

| column | G3 shift | runs/BF | cells moved | K | BB | HBP | HR | 1B | Out |
|---|---|---|---|---|---|---|---|---|---|
| fresh | 0 | 0 | 0 | 4 | 4 | 1 | 1 | 8 | 15 |
| fading | 0.5x | +0.020 | 3 | 3 | 5 | 2 | 2 | 6 | 15 |
| gassed | 1.0x | +0.032 | 3 | 3 | 5 | 2 | 2 | 7 | 14 |

Three cells of 33 between fresh and gassed -- small enough to print on one card as
three columns, and large enough for a player to feel. **DECISION (22 Sep): size
anchored at G3's own shift, not at the +0.09 step.** The rounding is why fading and
gassed differ by only one cell despite differing by half the shift; at 33 cells
the mechanic has about that much resolution, which is an argument for two fading
states rather than four.

### 7.4 The track: thresholds, and what it is for

**There is no burn multiplier** (`burn_or_capacity.py`). Other games give a
reliever one fresh inning against a starter's three, which is where a 3x burn
rate comes from. Within an outing a rate and a capacity are algebraically the
same thing -- a threshold of 31 at rate 1 behaves exactly like 93 at rate 3 --
so nothing could distinguish them there. Across days they differ, and the data
decides -- re-run at E = 30, R = 20 (23 Sep), because the original arithmetic was
done at R = 14 with no entry cost in the model. At rate 3 a reliever's 31-pitch
outing puts 3 x (30 + 31) = 183 on her track and needs 9.2 days to clear, while
she actually rests 5. She would arrive tired every time. At rate 1 she carries 61
and clears in 3.1 days, which is the observed rhythm. **DECISION (22 Sep,
re-checked 23 Sep): capacity carries the difference; there is no burn parameter.**

**The re-check exposed a dependence worth naming.** It now matters whether the
entry cost is multiplied by the burn rate. If it is not, a rate-3 reliever carries
3 x 31 + 30 = 123 and clears in 6.2 days, still past her 5 -- but strip the entry
cost out altogether and she carries 93, clears in 4.65, inside her rest, and rate
3 would no longer be excluded. The original rejection was made at R = 14 without
ever confronting this. It survives at R = 20 only because the entry cost exists.
**ASSUMPTION.**

Observed rhythm, for the record: relievers 31 pitches every 5 days, starters 68
every 6. Seven-day loads reproduce section 7's targets -- 45 relief-only, 85 for a
week with a start. League-wide a team-game is 133.1 pitches (median 132.5) over
6.83 innings of a SEVEN-inning game: 19.5 pitches an inning, 3.67 a plate
appearance, 2.90 pitchers a side.

**The cross-day track rarely binds, and that is the point.** At 14 pitches a day
-- and more so at the 20 finally chosen -- four outings in five start from zero,
and the mean carried in is 2.5 pitches in
the regular season and 2.6 in the postseason -- the playoffs are not tighter
(median rest 5 days against 6). So the track is not reproducing something real
managers hit. **It exists to stop the PLAYER doing what a real manager would
not** -- running one arm out every game -- and the fact that real usage almost
never engages it is evidence the limit is set in the right place, not that it is
useless. **ASSUMPTION.** (The figure looks only at the previous outing; a track
that sums will bite harder on back-to-back appearances.)

**Thresholds.** The two boundaries are not the same KIND of thing, and what
follows replaces a role-keyed table that treated them as if they were.

| column | every pitcher |
|---|---|
| fresh | 0-20 pitches |
| fading | 21 to her capacity |
| gassed | past her capacity |

**Fresh ends at 20, and that is MEASURED -- but the measurement moved.** The
decline is a step after her first inning and flat after (section 7.2). On the full
season a starter's first inning is **19.3 pitches mean, 18.0 median, over 79
starts**; it was 19.5 and 19.0 over 75. Complete team-innings run 19.4 (SD 8.8,
5.31 batters). The previous 17 came from an inning being "17.5 pitches" -- which
is the PITCHER-inning average, partial relief innings included, and a first inning
is a complete one. That unit error is fixed for good.

**Twenty is now slightly above both the mean and the median**, where on 37 games
it sat between them. It is kept because the whole system runs in tens (E = 30,
R = 20, fresh 20, capacity by tens) and because the first-inning distribution is
very wide -- p25 14, p75 25 -- so the difference between 18, 19 and 20 is far
inside the noise it is drawn from. Recorded as a judgement, not a measurement.
**ASSUMPTION.**

**Capacity is per PITCHER, and it is DESIGNED.** Two corrections, both the user's
(23 Sep).

*Role is not a property of the arm.* Twenty-three of this league's thirty-nine
pitchers worked both as starter and in relief, and those arms threw 67% of all
outings. Four of them went LONGER in relief than in any start: Sato 98 against a
77-pitch best as a starter, Villarreal 77 against 29, Mackay 79 against 72, and
Hondras 51 against 37. A role median of 31 measures how long a manager PLANNED
to use her. The old
`{start: 68, relief: 31}` was reading a scheduling decision as a physical limit.

*The median is where a manager stopped, not where an arm ran out.* Separate the
pitchers a team WANTS to field from the ones it is forced to field; the first
group should be pressing its limit. Blowouts are not what does this -- contested
and decided games give nearly the same medians (starts 70.5 against 65.0, relief
31.0 against 31.0). It is WHICH ARM: the median per-arm ceiling is 82 pitches for
a team's top five by usage and 56 for everyone below them.

So capacity is fitted per arm. Her longest outing is predicted from her typical
one (**max = 35.0 + 0.73 x median, R2 0.54, residual SD 12.6**), floored at what
she has actually thrown, and rounded to a whole pitch.

**The fit is weaker in the rulebook's currency** (29 Sep): measured in PITCH_COST
it was max = 31.3 + 0.88 x median, R2 0.62, SD 12.0. The flat 3 for everything but
walks and strikeouts compresses the spread between arms.

**And the ARGUMENT this section made needs a null it never had.** The old reasoning
was that her max tracks her median at 0.79 but her outing COUNT at only 0.27, "so a
ceiling is mostly a trait rather than an artefact of having had more chances to
show one" -- comparing both against an implicit zero. Zero is the wrong baseline:
**the maximum of a sample grows with the sample**, so even pitchers with identical
arms would show both correlations simply because some of them pitched more often.
The right baseline is a simulation in which every arm IS identical and only the
outing counts are real:

| | observed | null: identical arms |
|---|---|---|
| max ~ her median | **0.71** | 0.46 (90%: 0.24-0.65) |
| max ~ her outing count | **0.49** | 0.52 (90%: 0.34-0.68) |
| spread of maxes, SD | 20.6 | 17.6 (90%: 13.9-21.2) |

**Read properly, the conclusion survives but the evidence is thinner than it
looked.** The relationship with her median clears its null -- 0.71 against 0.46,
above the null's 95th percentile -- so there is a real trait in there. The
relationship with her outing count clears nothing: 0.49 against a null of 0.52, so
it is **entirely sample size and not evidence of an artefact at all**, which also
means the old 0.27 was BELOW what chance alone predicts. The caveat is the third
row: the observed spread of maxes, 20.6, sits inside the range identical arms would
produce. **The ladder separates arms, but by less than its range suggests**, and
the FLOOR at what she actually threw is doing more of the work than the fit is. The
ladder, over 38 arms:

| capacity | 50 | 60 | 70 | 80 | 90 | 100 | 110 |
|---|---|---|---|---|---|---|---|
| arms | 8 | 5 | 8 | 7 | 6 | 3 | 1 |

Saiki at 110; Sato, Schiano and Padgham at 100; del Castillo, Leblanc, Bricker and
Park at the bottom; median 69.5. **The ladder no longer rounds to tens** (user
decision, 29 Sep): it ran 50-110 in tens, on the reasoning that a round number is
easier to hold in the head, but the boundary is read off a track that moves in
threes and fives, so rounding bought nothing at the table and cost up to five
pitches of accuracy against a residual SD of 12.0. Each arm now carries her own
number, 44 to 100 over 38 arms with 29 distinct values. That spread is what the
old constant could not express --
the difference between the arm that goes five innings and the one that goes three.
Jaida Lee lands at 90 off a 33-pitch median and a single 86-pitch outing, which is
the converted starter the league talked about.

**The top of the ladder is thin, and it should be read that way.** Saiki reaches
110 on three outings, Padgham 100 on three. At the minimum sample the fit
extrapolates from a median rather than shrinking toward the league, so a pitcher
who happened to throw three long outings is handed the highest number on the card.
The floor at her own maximum protects against setting capacity too LOW; nothing
protects against setting it too high on thin evidence. **OPEN:** whether the
estimate should shrink toward the league ceiling by outing count, the way the
cards shrink toward a cohort. It would pull Saiki and Padgham down and move
nobody else.

**Why capacity is designed rather than measured.** The fatigue curve found ONE
step, after the first inning, and flat after it. No second step was ever found, so
there is nothing in the data to fit a fading -> gassed boundary to. Putting it just
past what each arm has been shown to do makes gassed the price of pushing an arm
further than a real manager pushed it: a deterrent, not a measurement. This is
also the honest answer to the objection that two columns were being measured and
three printed -- **fresh and fading are measured, gassed is designed.**
**DECISION (23 Sep).**

**The floor makes gassed unreachable within an outing; the carry gives it back.**
Capacity is floored at her own maximum, so by construction no real plate
appearance is past it: counted within outings, gassed is 0.0%. Counted the way the
engine counts -- track = carry + entry + pitches so far, with the carry running
across days at 20 a day -- 11.2% of real outings END past the line. The shares:

| | fresh | fading | gassed |
|---|---|---|---|
| **current** (rulebook currency, exact ladder, 39 games) | **0.412** | **0.579** | **0.010** |
| superseded (measured currency, ladder in tens) | 0.366 | 0.618 | 0.017 |
| superseded (fresh 17, role capacity, 37 games) | 0.389 | 0.461 | 0.150 |

The oldest rule put a sixth of the league's plate appearances in a state the data
never identified. These shares set the centring, so they move every column.

**This table is the only statement of the shares, and `dice.COLUMN_SHARE` is the
only place they are written down** (user decision, 29 Sep, after three different
triples were found quoted around section 7 and one of them was used in an
analysis). `rules_check.check_column_share` recomputes them from the real outings
on every run and fails if the constant drifts, so a stale number cannot survive
here again. Sections 7.5 and 7.6 below quote the shares that were current when
they were written; where they differ from this table, this table wins.

**The step the model delivers is smaller than the step that was measured.** With
the columns re-centred, playing every plate appearance off the fresh column gives
7.304 runs a team-game and off the fading column 8.040: a fresh -> fading step of
**+0.0202 runs per plate appearance**, with fading -> gassed adding a further
+0.0380. (On 37 games: +0.0218 and +0.0404 -- the full season did not move it.)
The paired end-aligned measurement that motivated the whole system found
**+0.078 (2.2 SE)**. These are not the same contrast -- the measurement's late
bucket is not the model's fading column -- but the model sits on the low side of
it, about 1.6 SE below. Matching 0.078 would need the columns spaced roughly 2.3
apart in lambda instead of 1, which puts fading nearly where gassed is now.
**OPEN:** whether to widen the spacing. The evidence for 0.078 is a single 2.2-SE
result, so the conservative spacing is defensible -- but it should not be changed
silently in either direction.

### 7.5 As built (22 Sep)

`dice.fatigue_card` makes the three columns. `engine.sim_fatigue` played with them
and has since been deleted (7.21-B); `season_fatigue.sim_season` is what plays them
now, on the real calendar.

**The shift is multiplicative, not additive.** Each line is multiplied by its G3
ratio raised to the column's power and renormalised, so a strikeout pitcher sheds
a share of a big line while a pitcher with one K cell is not asked for a cell she
does not have. Keira Izumi, who has exactly one, keeps it all the way to gassed
and degrades through walks and home runs instead. Across all 37 pitchers, gassed
costs **+0.032 runs per batter faced** on average (range +0.010 to +0.068),
landing on the section 7.3 target, and no column has an entry below one cell.

**The columns must be CENTRED, and this is the one thing the build changed.** A
pitcher's card is fitted to all her plate appearances, the tired ones included,
so it already carries the average fatigue she pitched with. Hanging a penalty on
top of it counts that twice. Centring shifts all three columns so their
usage-weighted mean returns her card exactly -- a **fresh pitcher is better than
her season line**, a gassed one worse, the average unchanged. **DECISION (22
Sep).**

**What it is worth, re-measured 29 Sep in the current build:** uncentred, the game
scores **8.46 runs a team-game against a season 7.64**; centred it scores **7.63**.
So centring is worth **0.83 runs a team-game**, or +0.0144 runs per batter faced on
the cards themselves. The figures that stood here -- 8.31 uncentred and 7.95
centred against a season 7.77 -- were the old currency and the superseded
simulator.

**The weights are `dice.COLUMN_SHARE`**, and nowhere else: see the table in 7.6,
which is the single statement of them, and 7.24 for why they are counted over real
outings rather than over the game. Two earlier triples quoted here -- fresh 43% /
fading 45% / gassed 12%, and a two-column "fresh 43.3% and fading 56.7%" -- are
both superseded and neither was ever the constant.

**What the column shares mean, and why they are needed.** They are the share of
PLATE APPEARANCES resolved against a pitcher in each column. Centring needs them
because the weighted average of the columns has to return her card, and that
average is over how often each is actually read.

That is circular -- the shares depend on the columns, since a tired pitcher
allows more baserunners, faces more batters, and so spends more plate appearances
tired -- so it was iterated. It converges immediately: centring on 0.433 returns
0.432, which returns 0.4319, and it sits there. One pass is enough, now checked
rather than assumed.

**Fatigue does not touch wild pitches.** The obvious extension is that a tired
pitcher loses the ball more often, and G3 cannot say: three wild pitches in the
game, a rate of 5.26% of rolls with a runner on against a league 5.01%, a ratio
of 1.05 -- with a Poisson error of +/-0.61 on a count of three, consistent with
anything from 0.4 to 1.7. (G3 had fewer running plays per roll than the league,
5.26% against 6.73%, on the same three events.) There is also a structural cost:
the running-play band is a fixed six-cell block on neither card, so making it vary
with fatigue means the table changes with who is pitching and how tired she is,
which is the one thing the fixed-block layout exists to avoid. **DECISION (22
Sep): the running-play band is the same whoever is on the mound.** Passed balls
belong to the catcher and balks to the umpire in any case (section 6).

**The pull rule is descriptive**: a stint length is sampled from the real
distribution by role and the pitcher comes out when her track passes it. That is
all that is needed to make a fatigue setting identifiable -- a setting only has
consequences where a tired pitcher is left in. It is not the AI manager of check
3.

**Against the season.** The table that stood here reported `engine.sim_fatigue`,
which played one team at a time on no calendar and has been superseded: the figures
are in the old currency, from a simulator that used 3.45 arms a team-game and never
carried a track between days. **The current comparison is in 7.18** -- every stint
distribution matching, 2.87 arms a team-game, 7.66 runs against 7.64 -- and the
open items it leaves are in 7.23.

### 7.6 Spacing the three columns

Writing the arithmetic out nearly killed the third column. (The figures in this
paragraph describe the REJECTED even spacing, in the measured currency of the day;
the spacing that was adopted is the table below.) Centred, fading sits +0.009
from fresh and gassed +0.021 -- but one cell of a 33-cell block is worth about
0.013 runs a batter, so **fresh to fading is less than one cell**. No rounding
rule can print a distinction that small. Rounding each column independently also
breaks monotonicity: Izumi's walk line has exact counts of 8.22, 8.59, 8.91 and
rounds to 7, 9, 8, so a player would watch her walks rise and then fall as she
tires. Building the ladder by moving cells out of the fresh column instead was
worse, leaving 7 of 37 pitchers with two identical columns.

The fault was the SPACING, not the third column. Setting them evenly at 0, 0.5
and 1 put fading half a step from fresh. Spacing them by what they MEAN fixes it:
fading is the measured plateau, gassed is past her capacity where nothing is
observed and the level is extrapolation, so it sits at twice the G3 shift.

| | share of real PAs | vs her card | step |
|---|---|---|---|
| fresh | 41.2% | -0.011 | -- |
| fading | 57.9% | +0.007 | +0.018 |
| gassed | 1.0% | +0.039 | +0.032 |

**0 of 76 adjacent pairs round to the same cells.** Crossing into gassed costs
nearly double what going fading did, which is what gives a manager a reason to act
before she gets there. **DECISION (22 Sep).** Figures re-measured 29 Sep in the
rulebook currency on the exact ladder; they stood at 38.9 / 46.1 / 15.0 with steps
of +0.023 and +0.042 when the track counted measured pitches and the ladder ran in
tens. The SHAPE is unchanged -- gassed is still nearly twice the step that fading
is -- and both steps are smaller because the cheaper currency keeps a pitcher fresh
longer.

The shares are counted over the REAL outings, not a simulation. The original reason
was that the simulation used 3.45 pitchers a side against a real 2.91, so its fresh
share was inflated and centring on it would centre on a known flaw. **That reason
expired on 29 Sep** -- the simulation now uses 2.87 against 2.87 -- and the choice
was re-opened and re-made on different grounds (7.24).

**OPEN:** the rounding can move cells between lines of near-equal run value.
Gilder's fresh and fading differ by two cells, K5 against K3, but only by 0.0004
runs, because the cells went to outs -- worth almost the same as a strikeout. The
median step is +0.018; hers is not. A card can look like it changed more than it
did.

**Stamina is a pitcher trait, but a small one.** Per-pitcher median start lengths
run 58 to 92 pitches with an SD of 8.9, of which 5.5 is the noise in a median of
about five starts -- so 7.0 is real, roughly half an inning. Her own median gets
weight 49/(49+30) = 0.62 against the role default, the same shrinkage the cards
use. It scales the fresh window rather than adding a threshold, since with two
columns there is only one boundary to move. **ASSUMPTION**: a pitcher who lasts a
fifth longer stays fresh a fifth longer; nothing in the data says when a strong
arm's step comes.

### 7.7 The optimising manager is degenerate, and that is the finding

Built with no free parameter: every batter is worth the same in runs, so the
run-minimising allocation gives each to the best arm still able to take him --
keep her while her current column beats the best available arm's fresh column.

It pulls after about 17 pitches every time. **7.22 pitchers a team-game against a
real 2.91**, median starter stint zero. The logic is right and that is the
problem: within one game there is never a reason to leave a tiring pitcher in
while a fresher arm sits in the bullpen, and with a deep staff the quality gaps
between consecutive arms are smaller than the fresh-to-fading swing of 0.023, so
everyone is pulled the moment she leaves the fresh window.

**The constraint that stops a real manager is not in the game.** He keeps a
starter in because he needs those arms tomorrow and the day after. A single-game
objective has no interior optimum; it burns the whole staff every night. So check
3 cannot be met by optimising one game, and the descriptive rule of section 7.5
is not a placeholder for something better -- it is standing in for a season-level
scarcity the game does not yet represent.

**OPEN:** the manager needs a cost for using an arm, which is a season quantity.
The three candidates are an explicit arms-per-game budget (descriptive, and
honest about it), a shadow price per appearance tuned until usage matches
(fitting, and then check 3 is circular), or a season-level objective with the
schedule in it (correct, and much the largest). Nothing here decides between
them.

**Re-run 29 Sep against the current build, which now HAS a cost for using an arm:
the entry cost changes nothing.** 7.28 arms a team-game against the 7.22 recorded
here. See 7.25 -- the cost is paid in the incoming pitcher's future availability,
and a single-game objective does not value the future.

**But the degeneracy is largely about the HORIZON, not the objective (7.28).** The
same rule, valuing twenty plate appearances instead of one, keeps a starter 71
pitches against a real 65.5 and uses 2.25 arms instead of 7.28 -- with no season
term added. "Within one game there is never a reason to leave a tiring pitcher in"
is true only of a manager who values one BATTER; over an outing there is, because
the arm he spends now is not available for the rest of it. The conclusion below
should be read as narrowed: no single horizon lands both the starter's length and
the arm count, so a season objective is still wanted, but it is not what separates
7.22 arms from 2.25.

**What "testable" means here.** Not whether the curve is right -- it cannot be.
With a pull rule in the engine, the system is tested on whether it reproduces the
median 68 and 31 pitches, the 7-day loads, and 7.77 runs per team per game. That
is a real test of the whole, and section 9 check 3 is where it lives.

**A pull rule is not the same as an AI manager.** A *descriptive* rule -- pull at
the observed distribution of stint lengths -- is enough to make a fatigue setting
identifiable, since a setting only has consequences where a tired pitcher is left
in. Check 3 asks the harder question of whether a *sensible strategy* produces
realistic usage. **OPEN**: both, but they are separable and the descriptive one
is small.

### 7.8 Why the columns sit where they do

**The rules themselves live in `Two_Outs_So_What_rules.md`**, which is the player's
document and carries no rationale. This section used to restate them and the two
drifted: the rulebook re-origined the pitch count so that a rested pitcher sits at
-30, entering adds 30, and she is fresh through 20 and fading through her stamina,
while this section still printed fresh to 50 and fading to 30 + stamina. Those are
the same system with every number 30 lower -- verified boundary by boundary, and
the column shares are identical to three decimals either way -- but two statements
of one rule is one too many. **DECISION (user, 25 Sep): the rulebook's form is the
real one**, because it makes stamina the fading limit directly. `engine.column_for`
now takes that count, and `rules_check.py` compares the two across every count at
every stamina on the ladder.

What belongs here is the reasoning the rulebook leaves out.

Fresh ends at 20 pitches of game work because that is one inning, and the measured
decline is a step after a pitcher's first inning rather than a gradual slide
(section 7.2). Twenty is measured directly: a starter throws 19.5 pitches in her
first inning, mean, 19.0 median. The boundary is on the COUNT and not on the
inning because the count is being kept anyway, and a pitcher who needed thirty
pitches to get through the first has done more work than one who needed eight.

Gassed begins at her stamina number, and that boundary is DESIGNED rather than
measured. Only one step was ever found in the data, the one after the first
inning; nothing in the record marks a second. Her stamina is set just past the
longest outing she has actually thrown, so reaching GASSED means a player has
pushed her further than any real manager did. It is the price of that, not a
measurement of it (section 7.4).

**Neither boundary carries the warm-up**, because the 30 buys availability later
rather than making her worse now: the fresh window was measured in GAME pitches, on
pitchers who had all warmed up. The rulebook gets this for free by starting a
rested arm at -30 -- she takes the mound at 0, and her first twenty game pitches
are fresh however much she is carrying from earlier in the week.


### 7.9 The entry cost, and the exploit that forced it

**The exploit** (user, 22 Sep). Recovery was a flat rate per day and the fresh
window was 20 pitches, so a 14-pitch outing cleared overnight and cost nothing.
The dominant strategy is then to run eight arms through a game at 14 pitches
each: everybody stays fresh, everybody is recovered tomorrow, and the fatigue
system never engages. A player who noticed would never play any other way.

**It is not a tuning problem.** With no entry cost there is *no* recovery rate
that satisfies both of the things it has to. A starter throws 68 and rests six
days, so R >= 68/6 = 11.3. A 14-pitch outing must not clear in the two days
between a team's games, so R < 14/2 = 7. Those cannot both hold. Writing it with
an entry cost E, the constraints are R >= (68+E)/6 and R < (14+E)/2, which cross
at **E > 13**: below that the mechanic is unrepairable, above it there is a
window.

**DECISION (22 Sep): E = 30, R = 20.** E = 30 is about what a reliever throws
getting loose, which is what the cost represents. Priced against the exploit --
eight arms at 14 game-pitches each, repeated every two days:

| E, R | an arm carries in, after eight such games |
|---|---|
| 0, 14 | 0 -- the exploit is free |
| 14, 14 | 0 -- still free |
| 20, 16 | 16 |
| **30, 20** | **32** |

At 32 carried in, she is past the fresh boundary before she warms up, so the
strategy degrades the arms it depends on. It also keeps the observed rhythm: in the
rulebook's currency a starter's median 66 carries out at **96 and clears in 4.8
days** against a real seven of rest, and a reliever's 28 carries out at **58 and
clears in 2.9**. (Measured in PITCH_COST these were 98 in 4.9 days and 61 in 3.1;
the conclusion is unchanged, which is the point of 7.9's constraint arithmetic
being expressed as a ratio.)

**The track is denominated in the RULEBOOK's costs** (user decision, 29 Sep):
5 for a walk, 5 for a strikeout, 3 for anything else. The engine used to charge
the measured conditional mean of each outcome instead -- BB 5.44, K 4.89, the rest
3.04-3.26 -- which came to 3.679 pitches a plate appearance against the rulebook's
3.482. Per batter that is nothing; over a season the rulebook is **5.3% cheaper**,
so the engine was validating a game nobody would play: 19.0 plate appearances to a
capacity of 70 where a player takes 20.1. Every threshold in this section is in the
cheaper unit, and `rules_check.check_costs` holds the two together. The cost of the
change is that the currency no longer coincides with the feed's measure, which it
used to; that coincidence is given up deliberately.

**R = 20 survives the change.** Restated in rulebook units the two binding
constraints become R >= 15.9 and R < 21.6, so twenty still sits inside with room,
and the user's requirement that R stay a round number is met.

**The thresholds move up by E, not the other way.** The fresh window was measured
as one inning of GAME pitches, on pitchers who had all warmed up, so the entry
cost buys availability later rather than making her worse now. A pitcher with
stamina 80 is fresh to 20, fading to 80, gassed past that.

**This fixes the multi-day exploit and not the within-game degeneracy.** They are
different problems: the exploit was about carrying arms across days, while
section 7.7's optimiser pulls too often inside a single game, where an entry cost
does not change the comparison -- a reliever still enters fresh. That still wants
a season-level term.

**The assumptions behind that derivation**, since only the inequality is forced
and the rest are choices:

1. A starter throws **68** pitches and rests **6 days** -- both observed medians.
2. A reliever throws 31 and rests 5. This constraint never binds.
3. "Recovered" means the count returns to exactly **0**. This is what makes the
   constraint tight; allowing a pitcher to start carrying a little would loosen it.
4. A team's games are **2 days apart**.
5. The exploit uses **14** game-pitches, chosen as "just under the fresh window".
6. Recovery is flat and linear, R a day whatever the count. No evidence for that
   shape; it is the simplest one.
7. The entry cost is the same for everyone and every appearance -- a starter's
   pre-game warm-up and a reliever's mid-game scramble cost alike, and a reliever
   who warms up without entering pays nothing.
8. The pitch count is the only thing limiting usage: no roster cap, no leverage.

**Assumption 4 does most of the work**, and it was the one made most casually:

| changed | E must exceed |
|---|---|
| baseline | **13.0** |
| starters rest 5 days | 22.0 |
| starters rest 7 days | 7.6 |
| the exploit uses 17 pitches | 8.5 |
| games 1 day apart | none, auto-blocked |
| **games 3 days apart** | **40.0** |

A team's gaps are median 2 and mean 2.51, but **38% are three days or more**,
where E = 30 blocks nothing. What saves it is that the exploit only pays when the
schedule is tight: at a 3-day gap an ordinary starter recovers 63 of her 68 and
is nearly fresh anyway, so cycling eight arms gains nothing, while at a 1-day gap
an arm carries 23 in and takes the mound tired. **The cost lands where the
strategy is worth playing and misses where it is not** -- which is fortunate
rather than designed, and is recorded as such. **ASSUMPTION.**

**What "carries N after eight cycles" means.** The count is a running number. Each
cycle of the exploit adds the entry cost and the game pitches, then subtracts the
gap's recovery: 30 + 14 - 2R, or 44 - 2R a cycle. She stays fresh while her carry
is at most 20, since entry adds 30 against a boundary of 50. At R = 20 the carry
grows 4 a cycle and crosses on her sixth appearance; at R = 21, 2 a cycle and the
eleventh. The exploit is never blocked outright -- it stops delivering fresh
pitchers after a while.

**DECISION (user, 23 Sep): R = 20**, taken over 21 for playability -- a count that
moves in twenties is one a player can update in their head between games, and the
whole system now runs in tens: E = 30, R = 20, fresh 20, capacity 50 to 100 by
tens. The cost is that no arm can work consecutive days without carrying something
in, which happened four times in the league; all four followed short outings of 13
to 33 pitches, so under this rule they arrive tired rather than being blocked.

**How much of this rests on the fresh window.** The user asked, and the answer is:
almost none of it. The two constraints that pin E do not involve the fresh window
at all -- a starter's capacity must clear in her rest (E + C <= 6R) and a 14-pitch
outing must not clear in two days (E + 14 > 2R). At R = 20 those give
26 < E <= 52, and E = 30 sits inside. The fresh window only sets how fast the
exploit DECAYS, and moving it from 17 to the measured 20 costs exactly one cycle:
the carry crosses on the sixth appearance rather than the fifth. **E = 30 survives
the correction untouched.**

Per-arm capacity does bite on the first constraint, where the role median never
did. At R = 20 a 100-pitch arm needs (30 + 100) / 20 = 6.5 days, and Saiki at 110
needs exactly 7.0. Starters rest a median 7 days (mean 8.7, p25 6), so both clear
-- but only just, and an arm at the top of the ladder pitching on six days' rest
starts her next outing carrying 10 to 20. The full season made this tighter rather
than looser: the ladder gained a 110 that the 37-game fit did not have.

**Short rest cannot calibrate any of this.** There are four appearances in the
league on one day's rest, 39 batters faced between them, and every one follows a
short outing: 13, 15, 19 and 33 pitches. By rest bucket the residuals are 1 day
+0.005, 2 days -0.011, 3-4 days -0.001, 5+ days +0.003 -- no pattern. Managers
never put a pitcher in the position where recovery would show, which is the same
reason the curve past the hook is unobservable (section 7.2). **ASSUMPTION.**

**Usage, for the record:** 2.89 pitchers per team-game, and the distribution is
tight -- two in 20 team-games, three in 44, four in 12, and **never five**. Any
rule that permits eight is wrong on its face.

### 7.10 The calendar, simulated (28-29 Sep)

`pixi run season-fatigue` (`src/wpbl/season_fatigue.py`) plays every team's real
games with the track carrying between them. Until 28 Sep nothing did: the only
fatigue simulator was `engine.sim_fatigue`, which reset the track at every outing
and played one game at a time (since deleted, 7.21-B), so **E and R -- the two
settings that exist only to link one day to the next -- had never been exercised by
any code that ran.** They were chosen by solving two inequalities by
hand (7.9).

**The settings pass, and the cleanest evidence needs no simulation at all.** Take
the 232 real outings, in order, and run them through the track at E = 30, R = 20:

| | |
|---|---|
| outings entering ALREADY past capacity | **0.0%** |
| outings entering past the fresh window | 13.8% |
| outings ENDING past capacity | 11.2% |
| entered_at: median / p90 / max | 0 / 27 / 72 |

Not once in a season would a manager have been blocked from an arm he actually
used, and the 11.2% ending past capacity reproduces the 11.3% `COLUMN_SHARE` was
derived from. **E = 30 and R = 20 are compatible with how this league really
pitched.**

**The descriptive manager, on the same calendar:**

| | dice | season |
|---|---|---|
| **starter stint, median** | **66** | **66** |
| ... p25 / p75 | 57 / 77 | 55 / 76 |
| reliever stint, median | 24 | 28 |
| relief-only week, median load | 44 | 41 |
| ... p90 | 85 | 92 |
| week with a start, median load | 89 | 83 |
| ... p90 | 145 | 136 |
| runs per team-game | 8.08 | 7.77 |
| pitchers per team-game | 3.26 | 2.80 |
| team-games with nobody available | 0.0% | -- |

**Both columns are in the GAME's currency** (29 Sep). They were not before, and it
mattered: the season side came from `workload.appearances`, which counts the feed's
pitches, while the dice side spends PITCH_COST. Once that became the rulebook's
5/5/3 the two units differed by 5.3%, and the dice looked about 5% lighter than
they were. `season_fatigue.real_usage` now re-charges the same real outings at
whatever the game charges, so both sides move together when the currency does. The
figures here are not comparable with the feed-unit ones an earlier draft carried.

**The starter distribution now lands exactly** -- median 66 against 66, quartiles
57/77 against 55/76 -- and that is the clearest single result in this section. The
loads run about 7% heavy at the median, and the serial check says why rather than
leaving it vague: the draw
has no memory, so **7.7% of starts have the same arm relieving within one day,
against a real 0.0% in 79 starts**, and 18.9% of starts come on three days' rest
or fewer against a real 3.7%. A starter relieving beside her own start inflates
exactly the weeks that contain a start and leaves relief-only weeks alone, which
is the pattern observed. Carry does not disturb the run environment: 8.08 sits on
the engine's own pre-fatigue level of 8.02 (9.1), and the league check is untouched
by the currency change at 7.66 against a season 7.67.

**CORRECTION (28 Sep): three stale column-share triples.** A first version of this
section quoted 7.5's fresh 43 / fading 45 / gassed 12 as the centring weights. The
live constant is `dice.COLUMN_SHARE` = **36.6 / 61.8 / 1.7**, counted over the real
outings run through the carry, and it supersedes both 7.5's triple and 7.6's 38.9 /
46.1 / 15.0. The real-log replay above confirms it. **7.5 and 7.6 should be
reconciled to the constant. FLAGGED.**

**The simulated gassed share is an artefact of the POOLED STINT DRAW, not a
property of E and R.** The sim reads 14.6% of plate appearances off the gassed
column against the constant's 1.0%, and its outings end past capacity far more
often than the real 11.2%. `capacity()` is FLOORED at what each arm demonstrably
threw, so within one outing a real pitcher cannot exceed her own capacity -- all of
the real overshoot is carry raising her entry point. Drawing her target from the
pooled role distribution discards that: a stamina-50 arm can draw the 69-pitch
starter median and pass her ceiling in one outing. The overshoot duly concentrates
in STARTS, 46.6% against 20.4% for relief, and a pitcher's real median stint
correlates **0.75** with her capacity -- exactly the link a pooled draw throws away.
Shrinking her own median toward the role default does NOT fix it: with about five
starts against a prior of thirty outings, every scale factor lands between 0.98 and
1.03. **OPEN.**

**"Share of outings past capacity" cannot be a calibration target**, because
capacity is defined as her floored maximum, so the real rate is near-definitional.
It diagnoses the pooled-draw artefact; it cannot be tuned against.

**The final really is the hardest thing asked of a staff, and 7.9 was right.** The
regular season runs a **median of 3 games per team per rolling 7 days, p90 4,
maximum 5**; the championship is 5 in 7, about 1.7x a median week, which is the
figure `bullpen_spec.md` gives. Simulated on that cadence the staff is squeezed
monotonically -- gassed outings 12.8% to 42.2%, runs 7.78 to 8.28 -- and never
collapses, 0.4% of team-games reaching the last game with nobody available. The
DIRECTION is the result; the size inherits the pooled-draw artefact above, so
**+0.50 runs is an upper bound.**

**CORRECTION (29 Sep), recorded because it briefly reversed this section.** A
version of `schedules()` read the feed's game rows at face value and so counted
one fixture several times (see Data notes: duplicate game_ids), inflating the
season to 140 team-games against a real 80. On that calendar the staff appeared to
collapse -- 49.1% of team-games with nobody available, 62.4% gassed, 9.07 runs --
and the loads appeared half again too heavy. **None of that was real.** It is
recorded only because the failure mode is instructive: the entry cost is a strong
amplifier, so any error that inflates games or arms per game turns into an apparent
collapse of the fatigue system rather than an obviously wrong game count.

**What check 3 now says.** The settings pass on the real log. The loads and the
starter distribution land. What does not land is the relief usage -- 25 against 31,
3.22 arms against 2.90, and the serial pattern above -- and all of it is the
manager having no memory and no plan, which is 7.7's open item rather than a
fatigue setting.

### 7.11 The guard (29 Sep)

`analysis/dice/rules_check.py` used to check three printed tables and stop at the
fatigue COLUMNS. Everything about the pitch COUNT -- what a batter costs, the
warm-up, recovery between games -- and every constant behind the cards were
unchecked, and all four mistakes found while building 7.10 were in that gap. It
now covers them:

| check | cases | result |
|---|---|---|
| Matchup Table | 100 rolls | agrees |
| Outs and Singles Tables | 720 combinations | agrees |
| fatigue columns | 945 counts | agrees |
| **pitch costs** | 8 lines | agrees |
| **the track: entering, recovery, the floor** | 2,534 cases | agrees |
| **season shape, from play-by-play** | 2 invariants | agrees |
| **COLUMN_SHARE, replayed** | 3 shares | agrees |

**The track is correct**, including the rulebook's own printed example checked
verbatim: finish at 83, recover 40 over two days to 43, enter at 73, read FADING,
seven pitches from GASSED. All four assertions hold.

**The season-shape check is anchored to PLAY-BY-PLAY, and that is the point.** It
asserts the calendar holds 2 x (games with plays) = 80 team-games. Anchoring it to
the `games` table instead would have been useless, because that table is what was
wrong -- the check would have confirmed the inflated 140 against itself. A game
either has plays or it does not. It also prints the real 2.90 arms per team-game
as the manager's standing target.

**COLUMN_SHARE replays clean**: the constant is 0.366 / 0.618 / 0.017 and walking
the real outings through the track, per plate appearance and in order, gives 0.375
/ 0.613 / 0.013. This supersedes the 3.68-pitches-per-PA approximation quoted in an
earlier draft of 7.10 and confirms the constant against 7.5's and 7.6's stale
triples.

**The costs drove the currency decision.** On the guard's first run it reported 8
mismatches: the rulebook charges 5 / 5 / 3 and `PITCH_COST` charged the measured
conditional means. That is now settled in the rulebook's favour (7.9), the ladder
is each arm's own number rather than a rung in tens (7.4), and `COLUMN_SHARE` was
recomputed from the replay under both changes. **The guard is green**, and the
three things it now pins -- the costs, the carry, and the constant -- are exactly
the three that had drifted.

**What the switch actually moved**, for the record: the stamina ladder from 50-110
in tens to **44-100 with 29 distinct values, median 69.5 against 70**; `COLUMN_SHARE`
from 0.366 / 0.618 / 0.017 to **0.412 / 0.579 / 0.010**; the simulated starter
stint onto its target exactly; and nothing at all in the league check of 9.1, which
does not read the columns.


### 7.12 A manager with a memory (29 Sep)

7.10 left the descriptive rule failing on everything serial: the draw had no
memory, so **18.9% of starts came on three days' rest or fewer against a real
3.7%**, and **7.7% of starts had the same arm relieving within a day, against 0 of
78 in the real season.** Two rules fix it, neither with a constant of its own.

**Starters are not scheduled; they become eligible** (user, 29 Sep). Most of this
league did not keep a rotation, so imposing one would invent a pattern the data
does not show. Instead an arm is start-eligible once her track has recovered to
RESTED -- and how long that takes is exactly how much she threw last time, which
the track already encodes. "See what she threw, then decide" needs no schedule.
Among the cleared arms she is drawn by her real share of starts.

**Relief is weighted, not gated** (user, 29 Sep): her real relief share times her
remaining headroom, `capacity - track`, so a loaded arm becomes progressively
unlikely rather than abruptly impossible. The old hard rule -- refuse anyone whose
entry would pass capacity -- is what produced a spurious "nobody available", since
the alternative to an unwise choice is not always a wise one.

**Two arms are held back, on BOTH sides of a start, and that took two goes.**
Protecting only the arm ABOUT to start left the 9.4% within a day almost
untouched, because the case that matters is the arm who has just started: the day
after a 66-pitch start her track is 46, her headroom is still positive, and she
keeps being drawn. Smooth weighting alone cannot reproduce a zero. So an arm who
started her last outing is unavailable in relief until her track clears -- the same
moment she becomes start-eligible again -- and that is what the 0-of-78 actually
describes.

| | before | after | season |
|---|---|---|---|
| starts on 3 days' rest or fewer | 18.9% | **0.1%** | 1.9% |
| start with relief by the same arm within 1 day | 7.7% | **0.3%** | 0.0% |
| ... within 2 days | 15.4% | **0.8%** | 2.6% |
| rest between starts, median | 7.0 | 8.0 | 7.0 |

**The serial pattern is now right, and slightly over-disciplined.** Real managers
occasionally did work an arm short; this one almost never does. The median gap of
8 against 7 is the same effect, and it matches the user's reading: an arm clears in
4.8 days but the next game's start may already be taken, so she waits a turn. The
spacing is a QUEUE, not a recovery time.

**It redistributed the load rather than fixing it:**

| | before | after | season |
|---|---|---|---|
| relief-only week, median | 44 | 52 | 41 |
| week with a start, median | 89 | 73 | 83 |
| starter stint, median | 66 | 67 | 66 |
| reliever stint, median | 24 | 24 | 28 |
| **arms per team-game** | 3.26 | **3.24** | **2.80** |

Weeks with a start were 7% heavy and are now 12% light; relief-only weeks were 7%
heavy and are now 27% heavy. Protecting starters moves the between-start work onto
the arms that only relieve, and there are not enough of them to absorb it.

**The one number that did not move is the one that matters.** Arms per team-game
is 3.24 against 2.80, exactly where it was, and with the entry cost every extra arm
is 30 pitches of pure overhead -- about 13 a team-game -- which now lands entirely
on relievers. **The remaining error is not the rotation and not fatigue; it is that
relief stints are too short** (median 24 against 28, p75 34 against 45). Real
relievers sometimes go multiple innings and these do not, so more of them are
needed, and each one costs a warm-up.

**That is the pooled stint draw, and 7.13 measures what is actually wrong with
it** -- which is not what this section first guessed.

**On the final's cadence** the squeeze is unchanged in shape -- gassed outings 13.3%
to 38.9%, runs 7.90 to 8.33 -- but the staff now runs out at the end: **2.6% of
team-games reach G5 with nobody properly available**, against 0.4% under the old
rule. Protecting starters is what does it, and it is the right kind of pressure for
a five-game series to apply.

### 7.13 Why relief outings ran short (29 Sep)

7.12 blamed "the pooled stint draw" without saying what about it. Measured, there
were two mechanisms and only one was the draw.

**1. A pulled pitcher could come back, and that was a RULES violation.** The relief
draw could re-pick an arm it had already pulled: **25.3% of team-games used someone
twice, some three times**, each return charging the 30-pitch entry cost again. A
removed pitcher cannot return. Fixed.

It also showed the headline number was flattering itself. "Pitchers per team-game"
counted DISTINCT arms, so a pitcher used twice counted once: the reported 3.24 was
really **3.52 entries**, and 0.28 of them were illegal.

**2. The targets looked truncated, and mostly were not.** 52.7% of real relief
outings end the game, and sampling that pool and then truncating again in the
simulation removes the length twice -- realised mean 26.1 against a target mean of
32.3, a 19% shortfall. But **most of those game-ending outings are not censored at
all**: they are arms whose job is to finish (7.14). Of the 77, **54 belong to LATE
pitchers doing exactly that**; only 19 are middle relievers caught by the end. So
the genuinely censored group is about **13% of relief outings, not 53%**, and
un-truncating the whole pool would have stretched closer stints to lengths no
closer throws. **The un-truncation plan was dropped on that evidence (user,
29 Sep).**

**What was really wrong was the ROLE, not the draw** -- see 7.14.

### 7.14 Relief is two jobs, split by the inning she enters (29 Sep)

**EDA (user's hypothesis, 29 Sep).** Relief pitchers were grouped by the share of
their outings that ended the game, then checked against features that did NOT
define the group:

| | outings | finish | median pitches | entry inning | median lead |
|---|---|---|---|---|---|
| LATE | 67 (51%) | 81% | 24 | 6 | +1 |
| MIDDLE | 64 (49%) | 30% | 35 | 5 | -0.5 |

They separate cleanly on entry inning and length, neither of which was used to
form them, so the split is real rather than a restatement. Meidlinger is
unmistakable: 13 outings, 92% finish, 18 pitches, entering in the sixth.

**There is no save-situation closer in this league, and the role is defined by WHEN
she enters, not by the score.** Among game-ending relief outings only **8 of 77
came with a 1-3 run lead**; 37 came from behind and 26 with a lead of four or more.
The median stint is flat at 23-26 pitches in all three. So the job is "throw the
last inning", and using the INNING as the splitter keeps the rule observable to the
simulator instead of edging into the AI manager. **DECISION (user, 29 Sep):
LATE_FROM = 6.**

**Late arms are on call, but not freely.** Rest before a relief outing: late
relievers went back-to-back 5% of the time and inside two days 17%, against 2% and
6% for middle relief and 0% and 1% for starters. A real, ordered effect -- but a
median of 5 days' rest is every second or third team-game, so "i.i.d. with no
buffer" was too strong and the protection is GRADED instead: the "about to start"
hold is dropped in the late innings and kept earlier, while two rules hold
throughout -- an arm recovering from a start is unavailable until her track clears,
and one already used today cannot return.

**A change waits for the inning to end.** 83% of real late relievers enter to START
an inning and span exactly one; middle relievers 57%, spanning three. Hooking the
moment a target is passed fragmented late relief badly -- a closer brought in with
one out left throws five pitches, and the simulated late stint came out at **14
against a real 22**. Changes now wait for the boundary unless a roll says
otherwise, at the observed mid-inning rates of 17% late and 43% middle.

**HEADROOM COUNTS THE WARM-UP** (user, 29 Sep): `capacity - (track + ENTRY_COST)`
rather than `capacity - track`. A pitcher who finished near her capacity is not
available the next day, because the 30 she spends warming up would put her back
past it before she faced anybody. This is the story the entry cost exists to tell
and the arithmetic was not telling it. It also does an explicit rule's work for
starters: a 66-pitch start leaves her at 46 the next day, so `cap - (46 + 30)` is
negative and she leaves the relief draw on her own. **She pays 30 for her start and
30 again for any relief between starts, which is what stops a starter being used as
a reliever too often** (user, 29 Sep).

**Together these move the number 7.12 could not:**

| | 7.12 | now | season |
|---|---|---|---|
| **arms per team-game** | 3.51 | **2.99** | **2.87** |
| starter stint, median | 67 | 69 | 66 |
| middle relief, median | -- | **41** | 39 |
| ... p25 / p75 | -- | 30 / 52 | 26 / 50 |
| late relief, median | -- | 17 | 22 |
| relief-only week | 47 | 46 | 41 |
| week with a start | 74 | 77 | 83 |
| runs per team-game | 8.04 | 8.04 | 7.64 |
| team-games with nobody available | 0.3% | 0.0% | -- |

**Arms per team-game is the result**: 2.99 against 2.87, a 4% excess where it was
25%. Middle relief now matches on the quartiles as well as the median. **OPEN:**
late relief is still short at 17 against 22, because the simulated late reliever
enters at a boundary but the game still ends under her more often than it did in
reality.

**Two hardcoded season figures were found and computed instead**, both the same bug
9.1 records in `engine.py`. The report printed a literal "7.77" runs per team-game;
computed from the plays it is **7.64**. And arms per team-game divided by a literal
80 team-games while the outings came from the 39 TRAINING games, understating the
real figure by 3% -- 2.80 where it is 2.87. Anchoring a number to play-by-play does
not help if the denominator is typed in by hand.

### 7.15 Three questions about the closer, answered (29 Sep)

**1. Is the primary closer saved for close games?** (user's win-probability bins.)
Win probability was computed at the moment each late reliever entered, from the
pitching team's side, and closing stints binned by how close the game was. The
answer is that **the bins cannot see it, and the reason is the finding**: 60% of
closing stints come with the game already decided, and only **3 of 52** fall in the
toss-up band.

| win probability at entry | closing stints |
|---|---|
| .40-.60 (toss-up) | 3 |
| .30-.40 / .60-.70 | 2 |
| .20-.30 / .70-.80 | 5 |
| .10-.20 / .80-.90 | 11 |
| **under .10 / over .90** | **31** |

No association survives: r = -0.023 between "the primary closer pitched" and
closeness, p = 0.87, Fisher p = 0.66.

**But the SIGNED split is significant, and the symmetric bins destroyed it.**
Measuring by closeness lumps "ahead by a lot" with "behind by a lot", which are
opposite decisions:

| at entry | closing stints | by the primary closer |
|---|---|---|
| **ahead** | 26 | **69%** |
| **behind** | 26 | **35%** |

Fisher p = 0.025, odds ratio 4.25. **Managers do reserve their best late arm -- for
LEADS, not for close games.** With only 8 of 77 game-ending outings coming at a
lead of 1-3, there is no save situation to reserve her for; what there is, is a
lead worth protecting at any size. **The earlier reading in 7.14 -- "no closer
role" -- was right about save situations and wrong about the role.**

*Circularity, stated:* the primary closer is defined as the arm with the most late
outings, so her overall 52% share is fixed by that definition. The LEVEL is
circular; the ahead-versus-behind contrast is not, since both halves are drawn from
the same definition.

**2. Does she come in clean, or into a jam?** (user's question.)

| late reliever enters | n | share | then finished the game | median pitches |
|---|---|---|---|---|
| to start an inning | 50 | 77% | 78% | 23.0 |
| **into a jam, runners on** | **14** | **22%** | **86%** | 20.5 |
| mid-inning, bases empty | 1 | 2% | 100% | 17.0 |

So **about one late reliever in five comes in to rescue someone**, and when she
does she almost always finishes -- 12 of 14. Middle relief is a different job
again: 44% enter into a jam and only a third finish. The simulation's boundary rule
(7.14) sends 83% of late relievers in clean, which matches the 77% here, so the
remaining late-stint shortfall of 17 against 22 is not the entry point.

**3. Why are runs high?** Fatigue turned OFF inside the simulator, same seed,
everything else identical:

| | runs |
|---|---|
| fatigue off (season card every PA) | 7.873 |
| fatigue on | 7.904 |
| **fatigue costs** | **+0.030** |

**It is almost entirely not fatigue.** The excess decomposes as:

- **+0.17, the seventh half-inning.** This module plays SEVEN half-innings for
  every team because it simulates one staff's workload, not a contest: it has no
  home side and no score to decide whether the bottom of the seventh is played. A
  real team bats **6.85** (9.1: the home team skips it 39.6% of the time). The
  season figure is now scaled to seven half-innings so the two sides match, and the
  report line says "runs per 7 half-innings" rather than "per team-game".
- **+0.03, fatigue**, via the COLUMN_SHARE mismatch: the simulation reads gassed
  4.9% of the time against the 1.0% centring assumes. Computed independently from
  the columns' run values this predicts +0.05, which agrees.
- **the remainder, about 2.9%**, is the structural excess 9.1 already records as
  predating fatigue.

Against the corrected baseline the simulation runs **8.04 against 7.81**. Nothing
here is a fatigue problem.

### 7.16 Two staffs in one game, and the bottom of the seventh (29 Sep)

**DECISION (user, 29 Sep): the simulation plays the real game.** 7.15 scaled the
season figure to seven half-innings to make the comparison fair. The user's point
was that the missing half-inning is not only a scoring artefact -- **it changes
closer length**, because it is the AWAY staff that loses it.

So `sim_season` now iterates FIXTURES rather than team-days. The home staff works
the top of every inning, the away staff the bottom, both tracks carry across the
season, and **the bottom of the seventh is not played when the home team already
leads.** A staff needs an opponent and a score to know that, which a one-sided
simulator could not have.

| | dice | season |
|---|---|---|
| half-innings pitched | **6.80** | 6.85 |
| bottom of the 7th skipped | 34.5% | 35.9% (9.1) |
| **pitchers per team-game** | **2.87** | **2.87** |
| **middle relief, median** | **39** | **39** |
| ... p25 / p75 | 28 / 50 | 26 / 50 |
| starter, median | 69 | 66 |
| late relief, median | 17 | 22 |
| runs allowed per team-game | 7.76 | 7.64 |
| relief-only week | 44 | 41 |
| week with a start | 79 | 83 |

**Arms per team-game and middle relief now land exactly**, and runs are within
1.6% -- inside the structural excess 9.1 records as predating fatigue. The season
figure is compared per team-game again, since both sides now mean the same thing;
`season_runs(per_seven=True)` and `seventh_rule=False` are kept for judging the
one-sided version.

**On the final's cadence the staff is now genuinely stretched**: unavailability
reaches **6.0% by G5**, against 0.4% when every team played seven half-innings a
night. Taking the seventh inning away from the trailing staff frees its arms, and
the pressure lands where a five-game series should put it.

### 7.17 What is left in the relief system (29 Sep)

**Late relief is the balancing item, and that is the whole of the remaining
error.** Its COUNT is right -- 0.81 late outings a team-game against a real 0.83 --
and total arms are exact. What is wrong is the length: 17 against 22. The
arithmetic says why. A game holds a fixed amount of work, so the three roles must
sum to it, and the other two run over:

| role | dice | season | difference |
|---|---|---|---|
| starter | 69 | 66 | **+3** |
| middle relief | 39 | 39 | +0 (median), +1 (mean) |
| late relief | 17 | 22 | **-5** |

Whatever the starter and the middle take beyond their share comes off the end of
the game, and the arm at the end is the late reliever.

**The root cause is what a "target" MEANS, and it is the same error in a third
costume.** `role_stints` draws targets from REALISED outings, then the simulator
applies a mechanism that modifies them again -- the boundary rule makes a starter
finish her inning after passing her target (+3), and the end of the game cuts a
late reliever short (-5). But the realised outings already contain both effects,
because real starters also finished their innings and real closers were also cut
off. **A target is being used as a decision threshold while being measured as an
outcome.** 7.13 found this as double truncation for relief; it is double
OVERSHOOT for starters, and the two meet in the middle at the late reliever.

The fix is to define the target as the point at which a manager DECIDES and
calibrate so that the REALISED distribution matches the real one, rather than
setting the realised distribution as the target and letting the mechanism move it.
**DONE in 7.18.**

**Second, the score is not in the pitcher choice at all.** 7.15 found managers
reserve the primary closer for LEADS -- 69% of closing stints when ahead against
35% when behind, Fisher p = 0.025, odds ratio 4.25. The simulator picks a late
reliever by role share and headroom and never looks at the score, so it spreads
the primary closer evenly over won and lost games. This is real and measured, and
it is also the first thing in this module that would need the manager to read the
scoreboard. **OPEN, and it is a design question rather than a calibration one.**

**Third, entering a jam is not modelled.** 22% of real late relievers come in with
runners on and 86% of those finish (7.15). The simulator changes pitchers at an
inning boundary or not at all, so a late reliever never inherits traffic. This
matters less for fatigue than for how a player experiences the game.

### 7.18 The hook, as a decision rather than a length (29 Sep)

**The user's hypothesis**, and the data agrees with it: a real starter is replaced
either because she is in a jam and looks gassed, or because it does not look like
she can pitch another full inning -- in which case the reliever takes the inning
from the start, rather than the manager waiting for her to reach her limit.

| how 78 real starts ended | n | share | median pitches | headroom left before capacity |
|---|---|---|---|---|
| at an inning BOUNDARY | 52 | 67% | 62.5 | median **15.5**, mean 17.9 |
| MID-INNING, runners on | 21 | 27% | 72.0 | median 10.0 |
| mid-inning, bases empty | 4 | 5% | 56.5 | 20.0 |

An average half-inning is **18.3 pitches**, so a starter pulled at a boundary has
about one inning left in her and the manager does not spend it. A jam hook comes
later and deeper -- she was left in and got into trouble.

**`comes_out()` replaces the drawn target for starters**: pull at a boundary when
another inning would take her past her capacity, or mid-inning when runners are on
and she is within half an inning of it. Her stint is now an OUTCOME of her capacity
and how the game has gone.

**MARGIN = 1.4 is the one calibrated constant.** The literal reading of "she cannot
pitch another full inning" is 1.0 and leaves her in too long, because she is pulled
at the FIRST boundary under the threshold and so her realised headroom averages
half an inning less than the threshold itself. Swept against the real starter
distribution, 1.4 lands it. It is calibrated the way 7.17 asks -- a decision tuned
so the outcome matches -- rather than an outcome used as a decision.

**Fixing the starter alone did NOT fix late relief, which disproves 7.17's
explanation.** Across every margin from 1.0 to 1.8 the late stint stayed at 17-18:
an earlier hook produced an EXTRA reliever rather than a longer one, because relief
was still pinned by drawn targets. Late relief was not absorbing the starter's
overshoot; it had its own problem, and it was the 7.13 one.

**So a LATE reliever gets no target either: she pitches to the end.** 81% of real
ones do. Drawing her a target instead cut her to 17 against a real 22, because the
pool she was drawn from had already been truncated by the end of the game. Middle
relief keeps its drawn target, because it lands (40 against 39) -- a hybrid, and
noted as one.

**The result:**

| | dice | season |
|---|---|---|
| starter, median | 64 | 66 |
| ... p25 / p75 | 55 / 72 | 55 / 76 |
| middle relief, median | 40 | 39 |
| ... p25 / p75 | 29 / 51 | 26 / 50 |
| **late relief, median** | **20** | **22** |
| ... p25 / p75 | 12 / 29 | 15 / 26 |
| **pitchers per team-game** | **2.87** | **2.87** |
| half-innings pitched | 6.80 | 6.85 |
| **runs allowed per team-game** | **7.66** | **7.64** |

**All three stint distributions and both totals now land.** The run environment
closed too: 7.66 against 7.64, where it had been running 2.6-2.9% high since before
fatigue existed (9.1). That excess was never purely structural -- part of it was
tired pitchers being left in by a target rule that did not know what a manager was
deciding.

**OPEN: the weekly loads redistribute wrongly.** Relief-only weeks are 48 against
41 and weeks with a start 73 against 83, so relievers carry about 17% too much and
starters 12% too little, even though every stint distribution matches. Totals and
shapes can both be right while the split across arms is not, and that is where this
now sits.

### 7.19 Nothing in the printed game rewards pulling her early (user, 29 Sep)

**The TIMING half is confirmed by direct test (7.28).** Forcing every pitching
change to an inning boundary, or forcing every one to happen immediately, moves runs
per team-game by nothing measurable -- 7.744 against 7.720, on a standard error of
0.08. **The game is indifferent to WHEN a change happens**, because a reliever
carries her 20-pitch fresh window in whatever the situation: entering mid-inning
does not cost her any of it, only changes which batters it is spent on.

**The EARLINESS half is narrower than this section claimed.** There IS a reason to
pull her early, and it is her own next stint rather than anything in this game: past
a free zone, every pitch she throws today costs her a fresh pitch next time (7.29).
For a high-stamina arm on normal rest, and for every arm on short rest, that cost
binds BEFORE the gassed column does. What remains true is that a median arm on
normal rest has about fourteen pitches of free headroom past a typical start, so
over that range nothing at all deters a player -- and `MARGIN = 1.4`, the arm a real
manager declines to spend, is still unpriced.

**The observation.** A real manager pulls his starter at an inning boundary with a
median **15.5 pitches of headroom unspent** (7.18). A player of this game has no
reason to. The printed rules give him the exact pitch count, fixed costs of 5 / 5
/ 3, and boundaries he can see, so he can run her to the pitch before her stamina
and pull her then. A mid-inning change costs exactly what a change between innings
costs. **There is no mechanic that makes a boundary change preferable, and none
that makes pulling early preferable.**

**Why this matters, and it is not cosmetic.** `MARGIN = 1.4` is a calibrated risk
margin -- the amount of arm a real manager declines to spend. He declines it
because he does not know how long the next inning will take. A player who can read
the count exactly faces no such uncertainty, so a sensible player plays at MARGIN
close to 1.0 and hooks mid-inning whenever it suits. **The usage this section
spent its length calibrating is usage the printed game gives a player no reason to
reproduce.** Section 9 check 3 asks whether a sensible strategy produces realistic
usage; against a descriptive rule it now passes, and against a player it would not.
This is the same finding as 7.7's degenerate optimiser, sharpened: there is no
reason to keep her in, and no reason to time the change.

**Candidate mechanics, none chosen.**

- **Charge more for entering mid-inning.** A reliever brought in between innings
  had the break to get loose; one brought in mid-inning did not. The entry cost
  already represents warming up, so this costs no new concept -- only a second
  number. It must stay small: 43% of real middle relievers and 17% of late ones do
  come in mid-inning, so the game should discourage it, not forbid it.
- **Hide the count.** `bullpen_spec.md` already imagines pitchers reporting their
  own fatigue on a coarse scale with noise, read before a game and at a limited
  number of mound visits. This is the REAL reason managers leave 15 pitches
  unspent, and it would generate the margin rather than imposing it. It is also
  the largest change, and it needs the reporting mechanic built first.
- **Make crossing into gassed carry a risk, not just a cost.** Gassed is worth
  about +0.04 runs a batter, which is a price a player will happily pay for one
  more inning. `bullpen_spec.md` carries an injury chance rising with fatigue;
  nothing like it is in this spec. A small chance of losing the arm for the series
  changes the calculus at the boundary without touching any table.

**DECISION NEEDED (spec owner).** The first is cheap and targets the boundary
behaviour directly; the third targets pulling early and is the more faithful; the
second is the real answer and the largest. Until one of them exists, the fatigue
system is calibrated against managers whose incentives the game does not give the
player.

**Hiding the count is ruled out for the BOARD game (user, 29 Sep):** a player has
to know which column to read, so the count has to be visible. It stays available
to a computer implementation -- which is what `bullpen_spec.md` describes, where
pitchers report their fatigue coarsely and mound visits are limited -- so the
mechanic is not dead, it belongs to a different product.

**History Maker Baseball's mechanic, which is the cheapest of the three.** In HMB
a reliever is FRESH until the end of the half-inning she enters, so bringing her in
with two outs spends most of a free fresh window on two batters. That creates the
boundary incentive out of the fatigue system itself, with no new number and no
surcharge -- the cost of a mid-inning change is the fresh time you waste. It is a
better shape than charging more for a mid-inning entry, because it scales with HOW
FAR into the inning she comes, which a flat surcharge does not. **Worth costing
out.**

### 7.20 Innings or pitches? The data cannot say, and one obvious test is a trap

**Both HMB and Deadball degrade at INNING boundaries rather than on a pitch count**
(user, 29 Sep), which prompts the question of which this league's data supports.

**The measurement in 7.2 was always by INNING.** The step is +0.067 after her first
inning, +0.095 after her second, +0.084 thereafter, and the section's own
conclusion is that "a mechanic that accumulates linearly with pitches would get
this shape wrong." The pitch count was adopted later, in 7.8, as an implementation
convenience -- the count is being kept anyway -- with 20 pitches standing in for
one inning. **So the inning-based reading is the measured one and the pitch-based
one is the approximation**, which is the opposite of the way round it has been
described since.

**The obvious test to separate them is a trap, and it was run and discarded.**
Splitting outings by how long her first inning took and comparing the later step
gives +0.176 for a short first inning and -0.152 for a long one -- an apparently
enormous effect in the wrong direction. It is regression to the mean. A long first
inning IS an outcome: she gave up baserunners, so her first-inning run value was
high, and differencing from it must fall.

| split by her first inning's length | n | her 1st inning | her later innings |
|---|---|---|---|
| short 1st (<=18 pitches) | 74 | **-0.281** | -0.106 |
| long 1st (>18 pitches) | 37 | **+0.079** | -0.073 |

The first-inning columns differ by 0.36 and the later ones by 0.033. The split is
measuring the first inning.

**What survives is weak and points away from pitch count.** Looking only at her
LATER innings, a pitcher who needed 24.6 pitches for her first does **+0.033**
against one who needed 12.3 -- where a pitch-count mechanic predicts she should be
clearly worse, having thrown twelve more. SE 0.046, p = 0.48, 80% interval -0.027
to +0.092. **Underpowered, consistent with zero, and consistent with a modest pitch
effect** -- it cannot settle the question, but nothing in it supports pitches over
innings.

**Why it cannot be settled here.** Both clocks are endogenous. Pitches thrown is an
OUTCOME -- a pitcher in trouble throws more of them -- so conditioning on it
conditions on how she has pitched. Innings completed is a MANAGER'S DECISION, and
he removes the ones being hit. There is no third variable in this data that moves
one without the other. **The choice between them is a design question, not a
measurement**, and it should be made on what the game needs: an inning clock
motivates changing at the boundary, which 7.19 says the game currently lacks.

### 7.21 What is left to reconcile (29 Sep)

Nothing here is a disagreement about how the game works. It is prose, dead code and
one named inconsistency that have fallen out of step while section 7 was rebuilt,
and this is the list.

**A. Numbers in this section that predate the currency switch and the exact
ladder. DONE 29 Sep** -- corrected in place, and the load-bearing ones are now
pinned by `rules_check.check_spec_numbers`, which recomputes them from the data and
fails when the prose and the code disagree. A data refresh SHOULD fail it; that is
the signal to update the spec, and it is exactly what went missing before. It found
a wrong number on its first run: the ladder's median is **69.5, not 70** -- 38 arms
means it falls between the nineteenth and twentieth. The table below is what was
corrected:

| | spec says | actually |
|---|---|---|
| 7.4 capacity fit | max = 31.3 + 0.88 x median, R2 0.62, SD 12.0 | **35.0 + 0.73 x median, R2 0.54, SD 12.6** |
| 7.6 column shares | 38.9 / 46.1 / 15.0 | **41.2 / 57.9 / 1.0** |
| 7.6 vs her card | -0.012 / +0.000 / +0.043 | **-0.011 / +0.007 / +0.039** |
| 7.6 steps | +0.023, +0.042 | **+0.018, +0.032** |
| 7.5 centring weights | fresh 43%, fading 45%, gassed 12% | the constant, 41.2 / 57.9 / 1.0 |
| 7.5 scoring | 8.31 uncentred, 7.95 centred | centring is worth **+0.0144 runs/BF**; the game runs 7.66 against 7.64 |
| 7.9 recovery example | a starter's 98 clears in 4.9 days | 64 + 30 = **94, 4.7 days** |

The capacity fit is the one that matters beyond bookkeeping: R2 has fallen from
0.62 to 0.54 and the slope from 0.88 to 0.73, because the rulebook's flat 3 for
everything but walks and strikeouts compresses the spread between arms. Chasing
that down also showed 7.4's "mostly a trait" argument was comparing its
correlations against an implicit zero when the right baseline is a sampling null;
against that null the conclusion survives but the evidence is thinner. See 7.4.

**B. Superseded code. DONE 29 Sep.** `engine.sim_fatigue` played one team at a
time, reset the track at every outing, and used the two-role start/relief split;
everything it measured is now done by `season_fatigue` on the real calendar. It is
deleted, along with `engine.stint_targets` (superseded by `role_stints`, which
splits relief in two) and `engine.manager_pull` (superseded by
`sim_season(manager="optimiser")`, which runs the same rule against a season -- see
7.25 for the re-run that cleared it for removal). `engine.py` loses 93 lines and
five now-unused imports. The dead `started_last` parameter, which `_pick_reliever`
stopped reading when the hold was removed, is gone too.

**C. One live inconsistency, and it is a real one.** `COLUMN_SHARE` centres every
card on **41.2 / 57.9 / 1.0**, counted over the real outings by 7.6's deliberate
decision. The simulation realises **39.9 / 57.3 / 2.8** -- gassed nearly three
times as often as the centring assumes. Fresh and fading agree within two points,
so the run environment barely notices (7.15 priced the whole mismatch at +0.03
runs), but **the cards are centred on a usage the game does not generate**, and
that is a choice rather than an accident only because 7.6 made it one.

**D. The manager is not in the rulebook at all.** `MARGIN = 1.4`, the hook rule,
the role split and the weighting all live in `season_fatigue`. The printed rules
say when a pitcher's column changes and nothing about when to take her out. That
is correct -- the pitching change is the player's decision and 7.2 says so -- but
it means the calibrated usage of 7.18 describes a manager the player is neither
told about nor motivated to imitate (7.19).

**E. Middle relief is still target-drawn** while starters and late relievers come
out by rule (7.18). It lands, so it stays, but the system now has two different
kinds of hook in it.

### 7.22 Injury: the data is too thin to calibrate (29 Sep)

Injury is specified only in `bullpen_spec.md`, as a per-PA chance rising with that
model's φ, flagged **ASSUMPTION** on both form and consequence, in a document whose
header says nothing is built. It is not in this spec or in the rulebook, and φ is
not a quantity this game has -- porting it means re-expressing it against the track
or the columns.

**The evidence base is one confirmed injury.** Jaida Lee, who was seen in a cast
(user). Her log fits: she pitched 8 times and then missed her team's last 6 games.

**Quiet injuries are visible but unidentifiable.** Counting each pitcher's longest
gap in HER TEAM'S GAMES rather than in days, so off-days do not read as absence,
the clearest case is the user's: **Jill Albayati, 6 outings, a mid-season gap of 10
team-games, median gap 3, and she came back.** Five others show gaps of 6 or more:
Maximiliana 8, del Castillo 8, Izumi 8, Shimano 7, Mackay 6.

**Four of the six are not injuries (user, 29 Sep), and only the user could know
it.** None of this is in the play-by-play:

- **Maximiliana** did not want to pitch. She is an infielder pulled onto the mound
  when the bullpen is stretched, and she left mid-season for the softball World Cup.
- **Izumi** is the arm of last resort, used so better arms can be saved for higher
  leverage -- which is the same pattern `relievers.py` and `depth.py` found.
- **Mackay** was benched for being hit. The log agrees: +0.200 runs a batter on 14
  Aug and +0.222 on 3 Sep. It also agrees with the rest of the user's account --
  she started championship G1 on 16 Sep and was **the best she has ever been,
  -0.271 over 23 batters across 81 pitches.**
- **del Castillo** and **Shimano** are the two that still look like injuries, and
  Shimano is the shortstop whose pitching pattern `bullpen_spec.md` already records
  as unexplained.

**Of the remaining candidates, Albayati has the cleanest signature**, and it is a
different one from Mackay's: she was pitching WELL before her gap (-0.583, -0.052,
-0.028) and stopped for ten team-games. A good pitcher who stops is what an injury
looks like; a hit pitcher who stops is what benching looks like. That contrast is
the only diagnostic the data offers, and it separates two of the six.

**That is the whole sample, and it cannot support a model.** One confirmed, two or
three plausible, and a gap of that size is equally consistent with a coach's
preference, a demotion, availability outside baseball (3.3 records absences as
non-use), or rest. Nothing in the record says when an injury struck, how long it lasted, or what
workload preceded it. **Any injury mechanic is invented, and should say so in the
same words 7.4 uses about capacity: a deterrent priced by design, not a measurement
of risk.** If one is added, 7.19's third candidate is where it belongs -- as a
reason to pull a pitcher before she is gassed, which the game currently lacks.

### 7.23 What the weekly split is NOT (29 Sep)

Two candidate causes were tested and neither is it. Recorded so they are not tried
again.

**A bug found on the way.** The two-sided rewrite cleared the whole `started_last`
array whenever a game opened, so every other arm lost its "her last outing was a
start" mark the moment the next game began. The protection of 7.12 had been
silently inactive. Fixed.

**Candidate 1: starters relieve at the wrong time.** True, and fixed, and it did
not move the loads. Real starters relieve a median of **7 days** after their last
start, 15% within three; the simulation held them until their track fully cleared
and produced **11 days** and 3%. Charging the warm-up against headroom had already
made that hold redundant -- a 64-pitch start keeps her out about two days on the
arithmetic alone -- so it was removed, giving 9 days and 16%. The weekly loads
moved by one pitch. **The timing of a starter's relief work is not what makes her
week light.**

**Candidate 2: relief work is too concentrated.** Also no. The busiest third of
relievers take 57% of relief outings in the simulation against 58% in the season.

**Candidate 3: the "about to start" hold keeps starters out of middle relief in
exactly the window a manager would use them.** Plausible -- the hold fires once her
track is within a day of clearing, which is three or four days after a start -- but
removing it moves the loads by two pitches (relief-only 49 to 47, with-start 73 to
74) and costs accuracy on arms per team-game. Not it either. Kept.

**Candidate 4: the team-week aggregate is wrong.** No. A team-week with three games
uses **7 distinct arms, 9 outings, 3 distinct starters and about 390 pitches** in
the simulation, against 7, 9, 3 and 390 in the season. The totals are right at
every level; only the split between pitchers is wrong.

**What the split actually decomposes into**, measured on weeks containing a start:

| | real | dice |
|---|---|---|
| weeks with ONE start | 84%, median load 75 | 87%, median load 70 |
| weeks with TWO starts | 16%, median load 136 | 13%, median load 132 |

So it is diffuse rather than one mechanism: the starter's own stint is two pitches
short, she does a little less relief inside that week, and a few percent fewer
weeks catch two of her starts. Each is small; together they are the 10 pitches.

**Candidate 5: starts are spread over too many arms.** No. Per team-season the
simulation uses **6.0 distinct starters against a real 6.2**, with the top four
taking 86% of starts against 85%, and 1.2 one-start arms against 1.8.

**Candidate 6: a starter's relief work comes at the wrong time in the week.** No.
For regular starters, the share of relief outings falling inside the seven days
after a start is **50% against a real 53%**, and the whole distribution over 1-2,
3-4, 5-6, 7-8 and 9+ days is close.

**Where the gap actually sits.** Splitting the with-start weeks by whether she is a
REGULAR starter (three or more starts):

| | real | dice |
|---|---|---|
| week with a start, regular starter | **86** | **73** |
| week with a start, occasional starter | 76 | 69 |
| relief-only week | 41 | 49 |

So it is the regular starter's week that is 13 pitches light, and her start accounts
for only 2 of that.

**Candidate 7: the rotation is a day slow, so fewer windows catch two of her
starts.** Real regular starters rest a median 7.0 days with a p25 of 6.0 and 26% of
their start-windows hold two starts; the simulation gave 8.0, 7.0 and 19%. The
window's lower bound is strict, so a start exactly seven days back falls outside it
-- which makes the p25 the quantity that matters, and 6 against 7 is the difference
between a quarter of pairs landing inside and almost none.

**That was a real mismatch and it is NOT the cause.** Its root is concentration: the
busiest simulated starter started 5.9 of 20 games against a real 6.8, because the
eligibility filter drops her from the draw whenever she is not fully cleared, so her
realised share falls below her nominal one. Weighting the draw by her share SQUARED
recovers it -- busiest 6.8, rest 7.0, two-start windows 23% -- and taking the
highest-share eligible arm greedily reaches 26%, exactly the real figure. **Neither
moves the weekly split by more than two pitches**: with-start goes 73 to 75 against
a real 83, relief-only 49 to 48 against 41.

**Conclusion after seven candidates: the weekly split is DIFFUSE.** Within each
category the loads are already close -- one-start windows 68 against 72, two-start
132 against 136 -- and the residual is two pitches on her start, about two more of
other work inside the window, and a few points of mix. No single mechanism is worth
more than a pitch or two, and every fix tried moves the headline number by about
that much. **It should be treated as the accumulated cost of small errors rather
than as a bug with a location.**

**What was still worth doing, for its own target rather than for the split. DONE 29
Sep.** The starter draw is now re-weighted so the realised start counts match the
observed ones (`calibrated_start_weights`). The eligibility filter biases them down
-- the arms that start most often are the ones least likely to be clear -- and that
is a selection problem with an observed target, so it is corrected the standard way:
`w <- w * (observed / realised)`, renormalised, damped at 0.6 to stop it oscillating
on simulation noise. **Nothing is fitted to the weekly loads.** It converges in
about five passes and is cached per process.

| | busiest starter | rest between her starts | per-pitcher share error | wk-start | wk-relief |
|---|---|---|---|---|---|
| nominal weights | 6.03 | 8.0 | 0.0260 | 73 | 49 |
| **corrected** | **6.89** | **7.0** | **0.0109** | 76 | 48 |
| observed | 6.80 | 7.0 | -- | 83 | 41 |

**It lands its own targets** -- the busiest starter and the rotation cadence, both
mis-calibrated on their own terms -- and halves the mean per-pitcher share error.
Squaring the share happened to land the same place, but arbitrarily; this has a
target rather than an exponent.

**And it confirms the diagnosis by failing to fix the split**, which moves three
pitches. On the full run the knock-on is small and in the right direction: the
starter's median stint goes 64 to **65** against a real 66 and the with-start week 73
to **75** against 83, with arms 2.84 against 2.87 and runs 7.65 against 7.64.
**7.23's conclusion stands: the weekly split is the accumulated cost of small
errors, and the rotation cadence was one of them worth about two pitches.**

### 7.24 Centring: the decision re-opened, and re-made (29 Sep)

7.6 centred the columns on the REAL outings rather than on the simulation, because
the simulation then used 3.45 arms a game against a real 2.91 and "centring on it
would centre on a known flaw". **The flaw is gone** -- 2.87 against 2.87 (7.16,
7.18) -- so the decision was inherited rather than held, and it was tested.

**Centring has a fixed point and it converges in one step.** Centre on a share
vector, simulate, count what the game actually reads, re-centre, repeat. The
feedback is negative, as it should be: weighting gassed more heavily shifts every
column down, pitchers get better, outings run shorter, and less gassed is read.

| | fresh | fading | gassed |
|---|---|---|---|
| real outings (the constant) | 0.412 | 0.579 | **0.010** |
| fixed point | 0.395 | 0.575 | **0.030** |

They differ almost entirely in gassed, where the game reads three times what the
real outings do -- and that gap is structural, not a flaw. `capacity()` is floored
at each arm's demonstrated maximum, so a real outing can barely exceed it within a
game; a player can push past it whenever she likes.

**Runs cannot choose between them.** Three seeds of 70 seasons each:

| centring | runs per team-game | SE | vs the season's 7.641 |
|---|---|---|---|
| real outings | 7.677 | 0.059 | +0.036 |
| fixed point | 7.659 | 0.024 | +0.018 |

Difference **-0.019, SE 0.064.** Both land on the season within error, and both
realise the SAME gassed share of 0.028, so the centring barely moves the usage it
is centred on. By 9.0's rule -- "a parameter that cannot move the score is not a
result; report its leverage before reporting its fitted value" -- **this parameter
has no leverage on runs at all.**

**It is not cosmetic, though.** The printed cards differ: 12, 14 and 20 cells move
across the fresh, fading and gassed columns, touching **6, 6 and 9 of 38
pitchers**. About a fifth of the staff would print differently.

**DECISION (29 Sep): keep the real-outing shares, on new grounds.** Runs cannot
adjudicate, so the choice is about what a card MEANS, and the real-outing version
is anchored to something observed: her columns average back to her card under the
usage she actually had. The fixed point is self-referential -- the shares depend on
the cards which depend on the shares -- and although it converges, it is a game
agreeing with itself. The old justification (the simulation was flawed) is
withdrawn; the choice stands on the anchor.

**A design fact worth recording.** The game reads the gassed column about **1.1
plate appearances per team-game**, against 0.4 for the real outings replayed
through the same track. Gassed is meant to be the price of pushing an arm past
where any real manager pushed it (7.4), and in play it arrives roughly once a game.
Whether that is too often for a deterrent is a design question, not a calibration
one.

### 7.25 The optimiser is still degenerate, and the entry cost does not touch it

7.7 found that a manager who simply minimises runs pulls after about 17 pitches
every time, using **7.22 arms a team-game against a real 2.91**. That was measured
on a build with **no entry cost**. The entry cost was introduced afterwards, partly
as a price for using an arm (7.9), so the obvious question is whether it supplies
the constraint 7.7 said was missing. `sim_season(manager="optimiser")` now runs the
rule against the current build.

| | arms / team-game | starter stint | runs | nobody available | gassed PAs |
|---|---|---|---|---|---|
| descriptive (7.18) | 2.85 | 64 | 7.66 | 0.0% | 2.8% |
| **optimiser** | **7.28** | **0** | **8.01** | **9.2%** | **13.2%** |
| season | 2.87 | 65.5 | 7.64 | -- | -- |

**It does not touch it. 7.28 against the 7.22 it burned with no entry cost at
all.** The reason is exactly 7.7's: the entry cost is paid in the INCOMING
pitcher's track, so it buys nothing in this game and costs only her availability in
later ones -- and a single-game objective does not value later games. A cost that
only bites tomorrow cannot deter a manager who is not thinking about tomorrow.

**What the season adds, which 7.7 could not see.** The damage is now visible and it
is severe: **9.2% of team-games end with no legal arm**, and the gassed column is
read on 13.2% of plate appearances against 2.8%.

**And the punchline: the optimiser allows MORE runs than the manager it beats on
every individual decision** -- 8.01 against 7.66, on 2,000 team-games. Every change
charges the incoming pitcher 30 pitches of warm-up; seven changes a game is 210
pitches of pure overhead, which wrecks the staff it is drawing from. The rule is
locally optimal at every plate appearance and globally worse over a season. That is
a stronger statement of 7.7's finding than 7.7 could make, because 7.7 had no
season to lose.

**So 7.7's conclusion and its prescription both stand.** The manager needs a
season-level objective, and the three candidates it lists -- an arms-per-game
budget, a shadow price per appearance, or a scheduled objective -- are still the
choice. `engine.manager_pull` has been deleted: the rule lives here as
`sim_season(manager="optimiser")`, runs against the real calendar, and is
reproducible.

### 7.26 Two hooks, and one of them is earned (29 Sep)

7.21's item E asked whether MIDDLE relief should come out by the rule of 7.18 like
the other two roles, rather than on a drawn target. Tested:

| | starter | middle (p25/p75) | late | arms | runs |
|---|---|---|---|---|---|
| hybrid, as built | 64 | 40 (29/51) | 20 | **2.86** | 7.62 |
| one rule for all three | 64 | 40 (27/50) | 20 | 2.99 | 7.65 |
| season | 65.5 | 39 (26/50) | 22 | **2.87** | 7.64 |

**The hybrid stays.** Unifying makes middle relief's quartiles slightly better --
27/50 against a real 26/50, where the hybrid gives 29/51 -- and makes arms per
team-game clearly worse, 2.99 against a real 2.87 where the hybrid is 2.86. Arms
per team-game is a total that took the whole of 7.13 to 7.18 to land and it drives
the weekly loads through the entry cost; the middle quartiles are a shape already
inside a pitch. **DECISION (29 Sep): middle relief keeps its drawn target, and the
system has two kinds of hook in it on purpose.**

### 7.27 History Maker Baseball's boundary rule, built and measured (29 Sep)

7.19's problem: nothing in the printed game rewards changing at an inning
boundary. The user's preferred answer is HMB's, where a reliever is Fresh until the
end of the half-inning she enters, so coming in with two outs spends most of a free
fresh window on two batters.

**Adapting it needs one decision, because the two clocks disagree.** HMB counts
innings and this game counts pitches, so a reliever eighteen pitches into her
outing is Fresh on the track and past the boundary on HMB's. Stacking them would
let the boundary rule ERASE carried fatigue, which is the one thing 7.9 exists to
prevent. So: **the boundary can only demote her, never promote her.** Once the
half-inning she entered is over she is at best FADING whatever her count says, and
an arm that came in already tired stays exactly as tired as her track makes her.
`sim_season(hmb=True)`, off by default pending a decision.

**The incentive is real, and graded the way it should be** -- by how far into the
inning she arrives:

| she enters | fresh pitches HMB gives her | the track would give | she loses |
|---|---|---|---|
| to start an inning | 18.3 | 20 | **1.7** |
| with one out gone | 12.2 | 20 | **7.8** |
| with two outs gone | 6.1 | 20 | **13.9** |

A boundary entry costs almost nothing and a two-out entry costs most of her fresh
window. That is a better shape than a flat mid-inning surcharge, which cannot
distinguish the two, and it comes from inside the fatigue system with no new
number.

**It costs the run environment nothing measurable.** Three seeds of 25 seasons:
7.694 with it against 7.688 without, on an SE near 0.1. The realised fresh share
falls from 0.398 to 0.337, which arithmetic says is worth about +0.04 runs a
team-game -- below what this many games can resolve.

**The optimiser cannot see it, and that is 7.25 repeating.** Its mid-inning change
rate is 56.9% without and 56.4% with: unmoved. The rule compares only the NEXT
batter, where the incoming reliever is fresh either way, while HMB's penalty lands
later in her outing. A cost that arrives after the current plate appearance cannot
deter a manager who is only valuing the current plate appearance -- exactly the
blindness that made the entry cost useless against the same opponent. **So this
test is inconclusive about a PLAYER**, who is not one batter deep; it would need a
manager that values a whole outing to demonstrate.

**One consequence if it is adopted.** The shares move, so `COLUMN_SHARE` must be
recomputed and every card re-centred: a real reliever entering mid-inning would
read fading earlier, so the real-outing replay that 7.24 anchors on changes too.
That is a card regeneration, not just a constant.

### 7.28 The horizon, not the mechanic -- and the case against adopting HMB

`sim_season(manager="lookahead")` values a whole outing instead of the next batter.
It compares the two options a manager really weighs: **change now**, with the
reliever inheriting a part-inning, against **finish the inning and change at the
boundary**, with her coming in clean. Parameter-free apart from `HORIZON`, the
number of plate appearances it looks ahead.

| lookahead | arms | starter | middle | late | runs | relief entries mid-inning |
|---|---|---|---|---|---|---|
| H=10, HMB off | 3.81 | 14 | 30 | 18 | 7.30 | 31.5% |
| H=14, HMB off | 2.94 | 24 | 42 | 20 | 7.51 | 34.4% |
| H=20, HMB off | 2.25 | 71 | 54 | 20 | 7.75 | 32.7% |
| H=20, HMB **ON** | 2.16 | 71 | 59 | 19 | 7.87 | **22.8%** |
| the one-batter optimiser (7.25) | 7.29 | 0 | 11 | 18 | 7.86 | 57.1% |
| **season** | **2.87** | **65.5** | **39** | **22** | **7.64** | **31.4%** |

**7.7's degeneracy is largely a HORIZON artefact, which 7.7 could not have known.**
A manager valuing one batter pulls after 17 pitches and burns 7.3 arms. The same
rule valuing twenty plate appearances keeps a starter **71 pitches** against a real
65.5. Nothing else changed: no season objective, no budget, no shadow price. **The
constraint 7.7 said was missing from the game is partly just looking further ahead
INSIDE it.**

**It is not the whole answer, though.** No single horizon lands both totals: H=14
gives arms 2.94 against 2.87 but a 24-pitch starter, H=20 gives a 71-pitch starter
but 2.25 arms. A within-game horizon buys realistic behaviour on one axis at a
time, so 7.7's call for a season-level objective is **narrowed rather than
refuted**.

**HMB is visible to this manager** where it was invisible to the one-batter one --
worth about **9 points of mid-inning changes at every horizon of 10 or more** (31.5
to 22.8, 34.4 to 24.7, 32.7 to 22.8). So the mechanic does reach a manager who
looks far enough ahead, and 7.27's graded table was right about its shape.

**But changing the manager's decisions is not the same as changing the game, and
the direct test says the timing does not matter** (user's question, 29 Sep).
Forcing the descriptive manager to make every change at a boundary, or every change
immediately, with the same hook points either way:

| mid-inning change policy | runs | SE | arms |
|---|---|---|---|
| always wait for the boundary | 7.744 | 0.082 | 2.79 |
| as observed (43% / 17%) | 7.688 | 0.105 | 2.88 |
| always change immediately | 7.720 | 0.040 | 3.05 |

**No difference, and none with HMB on either** (7.653 waiting against 7.617
changing). The comparison is not perfectly clean -- forcing the timing also moves
arms per game, 2.79 against 3.05 -- but nothing like a real effect appears.

**Computed rather than simulated, HMB is worth 0.033 runs a team-game.** A
mid-inning entrant loses about 10.8 fresh pitches, or 3.1 batters, and fresh to
fading costs 0.0179 a batter, so a mid-inning change costs 0.056 runs; at 0.59
mid-inning relief entries a team-game that is 0.033. The simulation's standard
error at 75 seasons is 0.08, so resolving it at three sigma would take about **54
times more games**. It is real and it is negligible.

**RECOMMENDATION (29 Sep): do not adopt it.** Keep `hmb=False`. It changes what a
thoughtful manager decides while changing the run environment by a third of a tenth
of a run, and it would cost a full card regeneration (7.27).

**CORRECTION to an earlier draft of this section.** It claimed the printed game
"already produces the real mid-inning rate, so HMB corrects something that is not
wrong." That was reading the lookahead's 32-34% against the season's 31.4% as
agreement. It is not evidence of anything: the direct test above shows the game is
INDIFFERENT to the timing, so the lookahead's rate is not tracking a run incentive
at all -- it comes from its horizon and from which arm covers the rest of the
inning. **7.19's original claim stands: nothing in the printed game meaningfully
rewards changing at a boundary.** The match with 31.4% is a coincidence.

**What the lookahead does establish** is the horizon result above, which does not
depend on any of this: myopia causes 7.7's degeneracy.

### 7.29 The cross-day cost of one more batter, and the absence of a round-number exploit

7.19 asks what stops a player running a pitcher to her limit. The within-game
answer is only the gassed column. The cross-day answer is her OWN next stint (user,
29 Sep): pitches thrown today are carried, so they delay her next appearance or
make her arrive further along her track.

**Fresh pitches available in her next outing, by what she threw today:**

| today | 4d rest | 5d | 6d | 7d | 8d |
|---|---|---|---|---|---|
| 60 | 0 | 0 | 20 | 20 | 20 |
| 70 | 0 | 0 | 10 | 20 | 20 |
| **80** | 0 | 0 | 0 | **20** | 20 |
| 90 | 0 | 0 | 0 | 10 | 20 |
| 100 | 0 | 0 | 0 | 0 | 20 |

**There is a FREE ZONE, and a normal start sits inside it.** She costs her next
outing nothing while `game pitches <= 20d - 60`: up to 80 on seven days' rest, 60
on six, 40 on five. The real median start is 66 pitches on a real median seven
days, so **a typical start leaves about 14 pitches of headroom that are free.** The
carry does not bite until she is pushed past them.

**Which means the two deterrents are ORDERED, and the order depends on the arm.**
Gassed begins at her stamina -- median 69.5, range 44 to 100 -- and the carry
begins at 20d - 60.

- a median arm on normal rest: **gassed first** (69.5 before 80). The carry is
  slack and the within-game column is what deters.
- a high-stamina arm -- Saiki at 100, Sato and Schiano near it: **the carry first**
  (80 before 100). Her cross-day cost is the binding constraint, which is the right
  way round, since she is the arm a player most wants to over-use.
- short rest, four or five days: the free zone collapses to 20-40 pitches and the
  carry dominates everything. That is the postseason case 7.9 was designed for.

**No round-number exploit** (user's concern, 29 Sep). Past the free zone the cost
is **exactly linear -- one fresh pitch lost per pitch thrown** -- so the function is
piecewise linear with two gentle kinks, where she stops clearing fully (slope 0 to
1) and where she would arrive with no fresh window left (slope 1 to 0). Crossing
the first by one pitch costs one pitch. **There is no cliff, so there is no number
to stop on.**

The kink's LOCATION is a multiple of 20, since R is, so a player planning "she must
be fully fresh next time" has a soft target at 80 pitches on normal rest. That is
not an artefact to remove: it reads as ordinary managing -- get her through the
sixth and no further -- and overshooting it is penalised gently and proportionately
rather than punitively.

**On the final's cadence** the squeeze is sharper than any earlier version:
unavailability reaches **8.4% by G5** and runs climb 7.71 to 8.23.


## 8. Dice

**DECISION (user, 17 Sep):** cells are 1 percentage point. Even with more than
two d10, a roll is read against tables no finer than that.

**DECISION (user, 21 Sep): a single d100, its cells split between the two
cards** (the Strat-O-Matic form). One throw resolves a plate appearance: the
block the roll lands in decides whose card is read, and that *is* the
combination rule (section 4). The two schemes also on the table -- two colours
of 3d10 for independent thousandths, and d100 pitcher plus d1000 batter -- bought
finer cells and exact multiplication of the two cards. Multiplication is not the
combination rule any more, so they bought nothing the game needs. What the
choice costs is 1-point cells and a fixed card capacity, which section 4.1
spends deliberately rather than letting Out absorb.

**DECISION (user, 19 Sep):** an extra die settles splits within a card line when
one comes up: the kind of out and its +, and the number of pitches. It no longer
has a walk / HBP split to settle -- those are separate lines now (section 2).

**DECISION (21 Sep): that die is a d12**, and it settles the single as well
(section 2). Confirmed against the flavor rates as they now stand
(`out_quantize.py`). Scored on the runs each allocation misses by,
a d12 costs 0.027 runs a game against 0.068 for a d6, 0.130 for a d20 and 0.395
for a d10 -- and it wins in the state that matters, with a force on, where it is
five times better than any other die. The table is read per force state:

| d12 roll | Nobody on 1st | Force at 1st |
|---|---|---|
| 1-5 | B | B |
| 6 | B+ | B |
| 7-8 | B+ | B+ |
| 9-10 | B+ | F+ |
| 11-12 | B+ | FB+ |

With a force on, F and FB always come with the + -- their bare forms are 4.4% and
4.0% of out plays, too small for a cell of a d12, and the pooled + rate of 78.6%
(section 2) puts them on the + side. With nobody on 1st, F and FB act as B, so
only the + is rolled for.

## 9. Validation

### 9.0 How card choices are evaluated

- Held-out by game: random halves of the training games; cards built on one
  half score the other; 20 splits.
- Score: squared error of expected run value per PA (linear weights) first,
  pitches per PA second; log-likelihood is diagnostic only. Errors in
  high-value lines count more (a missed home run outweighs a missed walk).
- **Exception: choices between outcomes of similar run value are scored on
  log-likelihood.** Runs cannot see such a choice at all, so a runs search does
  not merely answer it badly -- the parameter is unidentified, and the search
  returns whatever the starting point or grid order happens to give. That has
  now happened four times: the BB \| HBP smoothing step (a walk is worth 0.45,
  an HBP 0.49, and a runs search returned k = 1, a tie); the pitcher's k when
  the mixing weight is 0, where his card is never read; bins of the d100 whose
  two cards hold the same line; and the mixing weight of a bin holding walks
  and errors (+0.45 and +0.50). Runs still govern what a choice costs on the
  field; they cannot choose between two lines worth the same. Any parameter
  scored this way must say so where it is defined. **DECISION (user, 21 Sep).**
- A parameter that cannot move the score is not a result. Report its leverage
  before reporting its fitted value.
- Comparisons between methods with different numbers of tuned constants use
  nested cross-validation: constants are tuned only inside each build half.
- Standard errors come from resampling whole games.
- Caveat: the score weights players by PA, so it barely sees players with a
  handful of PAs; their cards rest on the cohort by design.

Before anyone plays:

1. **League check.** Cards simulated under the dice rules must reproduce the
   run-expectancy table and the half-inning run distribution. **Run (section
   9.1).**
2. **Spread check.** With real cards, the spread of player outcomes must match
   the smoothed spread, with dice rounding neither erasing nor exaggerating it.
   **OPEN.**
3. **Fatigue tuning.** A simple AI manager's stint lengths and 7-day loads must
   land on the usage targets in section 7. **RUN, AND IT SEPARATES (section
   7.10).** Replaying the REAL log through the track clears the settings: E = 30
   and R = 20 never block an arm a real manager used. The 7-day loads and the
   starter distribution land. What does not is the relief usage -- 25 pitches
   against 31, 3.22 arms a team-game against 2.90, and a starter relieving beside
   her own start 7.7% of the time against a real 0.0%. Both are now fixed. A
   reactive rotation and both-sided protection put short-rest starts at 0.1% and
   starter-relieving-beside-her-start at 0.3% (7.12); splitting relief into middle
   and late by entry inning, waiting for the inning boundary to change, charging
   the warm-up against headroom, and forbidding a pulled pitcher to return took
   **arms per team-game from 3.51 to 2.99** (7.13, 7.14); playing both staffs in
   one game, with the bottom of the seventh dropped when the home team leads, took
   it to **2.87 against a real 2.87** (7.16). Middle relief lands exactly at 39,
   half-innings pitched at 6.80 against 6.85. Replacing the drawn target with a
   HOOK RULE -- pull at a boundary when another inning would pass her capacity, or
   mid-inning in a jam -- then landed the rest (7.18): **all three stint
   distributions match, arms per team-game is exact at 2.87, and runs are 7.66
   against 7.64.** Correcting the starter draw for the eligibility filter then put
   the rotation on 7.0 days against 7.0 and the busiest starter on 6.89 against 6.80
   (7.23). **What remains OPEN is the weekly split**: relievers carry about 17% too
   much and starters 12% too little, though every stint distribution, both totals
   and the rotation cadence are right. Seven candidate causes have been ruled out
   and each fix moves it a pitch or two, so it is recorded as the accumulated cost
   of small errors rather than a located defect.

### 9.1 The league check, as run (22 Sep; re-run 25 Sep with whole games)

`pixi run engine` (`src/wpbl/engine.py`) plays the printed game -- it rolls a
d100 against the cell table, rerolls on a running play, rolls a d12 for the out
flavor and the single -- rather than modelling it. Cards and pitchers are drawn
in proportion to use, which matters: the league-average card rounded into 33 and
55 cells prints home runs at 3.19% against the card's own 2.50%, a 28% relative
inflation, because both blocks scale one rate and both round the same way. Real
cards average that out (batter mean bias -0.086 cells on HR), so a check run
league-against-league validates a table nobody will play with.

| | dice | season |
|---|---|---|
| run expectancy, mean absolute difference over 24 states | 0.092 runs | -- |
| ... states where the dice are high | 12 of 24 | -- |
| transition distance, PA-weighted (`engine_transitions.py`) | 0.092 | 0.075 from sampling alone |
| runs per half-inning | 1.103 | 1.116 |
| scoreless half-innings | 55.0% | 52.1% (+/- 2.2) |
| **runs per team-game, whole games** | **7.66** | **7.67** |
| ... half-innings batted a team | 6.89 | 6.85 |
| ... runs in each | 1.113 | 1.120 |
| bottom of the 7th never played | 39.6% | 35.9% |
| games past seven innings | 6.6% | 5.1% |
| leadoff lineup slot 1 | 23.6% | 25.4% |

**The season row used to be a hardcoded string.** `engine.py` printed
"1.132 runs, 50.8% scoreless ... 7.77 runs per game" as a literal, so adding two
games silently left the dice being compared against the wrong season. It is
computed now (`engine.season_halves`).

**Runs per team-game is now measured on whole games, and the structural error is
gone.** `engine.sim_games` plays both sides with the rules that end a game
(`Two_Outs_So_What_rules.md`): the home team does not bat in the bottom of the 7th
when it is already ahead, and a tie goes to extra innings with a runner placed on
2nd. Multiplying a mean half-inning by seven counted half-innings nobody played --
which is exactly why that route reads 7.81 against a line score of 7.67.

**The decomposition matters more than the headline.** 7.67 against 7.67 is not two
errors cancelling, and the check now prints the parts so it cannot be read that
way: the dice bat 6.89 half-innings a team against the season's 6.85, so the ending
rules reproduce the COUNT, and score 1.113 in each against 1.120, so what remains
is the same small per-half-inning shortfall that was always there. The skipped
bottom of the 7th (39.6% against 35.9% on 39 games) and extra innings (6.6%
against 5.1%) both land inside the season's own noise. Every season figure in that
block is computed (`engine.season_endings`), not quoted.

**The over-scoring closed.** On 37 games the dice produced 8.02 runs a team-game
against 7.77, about 3% high and unexplained. Two things fixed it and neither was a
tuning knob: the pitcher block's largest-remainder allocation moved a cell from 1B
to BB when the last two games arrived, and a walk is worth less than a single; and
the game-ending rules stopped counting half-innings that were never played.

**What the check caught.** Comparing transition *distributions* rather than run
expectancy found a real bug that run expectancy could not see: steals were
resolving before the plate appearance instead of after. Fixing it cut the excess
transition distance from 0.059 to 0.019 while moving run expectancy by 0.003 --
the error was pure state-misplacement, and a summary statistic absorbed it
completely. **Compare transitions, not just expectancies.** Each state's distance
is judged against n draws from the engine's own distribution, because a state
seen 10 times looks far off even when the engine is exact.

**The leadoff distribution is an unturned check the engine passes:** batting nine
cards through seven innings reproduces the observed non-uniform leadoff slot
(25.4% for slot 1) without anything being fitted to it.

**The residual.** Scoreless innings run 3.0 points high, which is 1.39 SE against
the 534 observed half-innings behind the target -- the one thing neither the extra
games nor the ending rules touched, and the gap has barely moved across all of them
(3.2 points on 37 games, 2.9 on 39, 3.0 with whole games). Five explanations were
tested
and are not worth retesting without more games:

| tested | effect on the gap |
|---|---|
| the old "two outs, run on anything" rounding | real, 0.5 pts -- now fixed |
| the runner from 1st on a single (the `+` level) | real, 0.5 pts -- now fixed |
| steals missing entirely | real, 1.2 pts -- now fixed |
| league card vs cards drawn by use | rejected, 0.3 pts |
| lineup order vs batters drawn independently | rejected, 0.4 pts |

The lineup-order test is a caution worth keeping: on 15 starters-only lineups it
appeared to close 1.5 points, and on all 78 team-game lineups with substitutions
it closes 0.4. The first sample was stronger than a real batting order.

**What the check cannot do.** It reads one card per side per plate appearance, so
it cannot reproduce a league where weak pitchers populate the traffic states. The
gradient is real: pitchers facing `_2_` with nobody out walk 1.9 points more than
league, and pitchers facing bases empty with one out 1.3 points less. Drawing
pitchers by use reproduces its sign everywhere and about a fifth of its size.
**Measuring it needs care** -- leave-one-plate-appearance-out puts the gradient at
`123` with two outs at +3.3 points, and excluding the whole inning puts it at
-0.0, because the walks that loaded the bases were still in the pitcher's own
season rate. Excluding the inning, the honest spread is about -1.7 to +1.9
points. **ASSUMPTION:** the residual is sampling noise in a 37-game target rather
than a sixth unmodelled mechanism.

## 10. Open questions

- Out flavors: the + rates for F and FB rest on 13 plays between them, and
  there is no measurement at 2 outs at all (section 2).
- Whether the balk changepoint is real (section 6). At p = 0.17 it is the reason
  the running-play band is 6 cells rather than 7, so more games settle a cell.
- **The dropped third strike.** Once in 2,663 plate appearances a batter struck
  out and reached first on the wild pitch. No card line covers a strikeout that
  puts a runner on, and at one occurrence it does not earn a cell -- recorded so
  it is a decision rather than an oversight.
- Handedness: revisit when there are more games (section 5). The walk/HBP split
  is the place to look, and it needs free passes, so it resolves slowly.
- **Situational pitcher quality** (section 9.1). Weak pitchers populate the
  states with runners on, and a card carries one rate for every situation, so
  the game cannot reproduce it. Whether that matters enough to model is open.
- The scoreless residual (section 9.1): 1.44 SE, five explanations tested and
  rejected or already fixed. More games, not more tests.
- Predict vs replay: optional fan cards with smaller k; fans may not accept
  Benites's card dropping about a fifth (her 65.5% hits per ball in play).
- Whether cards must preserve league totals (the printed table gives 70.6 home
  runs against 69).
- Catcher and runner ratings for the steal game.
- Fatigue shape, size, and how readiness is reported. Nothing in section 7 is
  designed yet, and it is the game's central mechanic.
- Computer agents for testing: lineup and pitching decisions.
- Whether the bullpen spec's tryout-arm rule applies here (usage cohorts
  currently cover low-use pitchers). **ASSUMPTION.**

## Data notes

- **One game can have several `game_id`s, and only one of them is the game.** The
  `games` table holds 71 rows for 40 played games: each fixture may also carry
  "Not Started" placeholder rows scheduled for the same date and teams. BOS at NYH
  on 13 Aug appears **three times, and it was one game** (user, 29 Sep). `is_final`
  separates them exactly -- all 40 final rows have play-by-play, none of the 31
  others do -- so **anything counting games must filter `is_final`**. Taking the
  rows at face value inflates the season to 140 team-games against a real 80.
  Counting distinct dates per team happens to give the right answer today, because
  no team ever plays twice in a day, but it would swallow a real doubleheader.
  `season_fatigue.schedules()` filters `is_final`.
- The feed misspells names in some box scores (accents dropped, "Naraski",
  "Maggie Fox"), which had split three players in two and names a pitcher "/"
  in championship G2. Fixed in `parse.py` with a check in `pixi run check`
  (commit f2f50f8).
