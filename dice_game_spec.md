# WPBL dice baseball — design spec

A two-player tabletop baseball game with cards and dice, using the 2026 WPBL.
One roll resolves a plate appearance. Both players set lineups and make the
pitching decisions; computer agents will be needed to test the game. It may
precede or replace the bullpen simulator (`bullpen_spec.md`). **DECISION
(user, 17 Sep).**

Status: design; cards and the d100 table built (`pixi run dice`, sections 3 and
4), v0.4.0. Numbers are from this repo's training scope: 37 games (the 30-game
regular season, semifinal G1-G2 of both series, and championship G1-G3).
Semifinal G3 (14 Sep) is excluded because both bullpens were exhausted
(`tables.TRAINING_EXCLUDED`); later championship games join training unless the
same happens, decided game by game. **DECISION (user, 17 Sep).** Items marked
**ASSUMPTION** are choices, not findings; items marked **OPEN** are undecided.

Policy: the probability distribution must reflect the data first; game
mechanics are then designed to reproduce it. Which card carries which line is
a finding, not a rule. **DECISION (user, 17 Sep).**

## 1. The chain

A play is a transition between base-out states, as in `markov.py`. The engine
needs nothing else: state is inning, half, outs, which bases are occupied,
score, and each pitcher's fatigue.

Design rule: **fidelity stops where the data stops.** 2,663 plate appearances
cannot support runner-by-runner advancement rules, so runner movement is fixed
per outcome line, with one variant line where the data shows a real coin flip.

## 2. Outcome lines

Two different jobs, kept apart:

1. **Card lines** come from the feed's play labels, consolidated from 15 to 8
   by `batters.contact()`. Counts are the 37 training games:

| Card line | Feed labels |
|---|---|
| K | strikeout 314; generic "out" 3 (batter's interference: an out with no ball in play) |
| BB | walk 336 |
| HBP | hit by pitch 94 |
| HR | home run 69 |
| 1B | single 562; fielder's choice 1 (the ball got through to the outfield) |
| 2B | double 121 (triples included; none this season) |
| ROE | reached on error 59 |
| Out | groundout 367, flyout 282, popup 114, fielder's choice 95, lineout 91, generic "out" 70, foul out 54, sacrifice 31 |

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

Evidence (37 training games): of the 399 plays the flavor table governs -- a
plate appearance with runners on, <2 outs, and a label that is an out -- these
lines reproduce 374 (94%).

`proposals.py` reports the same coverage on a wider set of 514 (482, also 94%):
it counts any plate appearance where an out was *recorded*, whatever the label,
which adds 104 strikeouts, 8 singles with a runner thrown out and 3 unlabelled
plays. Strikeouts are reproduced 98% of the time and are not governed by the
flavor table at all -- a strikeout cannot be a fielder's choice -- so 399 is the
denominator that means something. The two counts now reconcile exactly.

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
| F | 14.0% | 76.9% | 13 plays, pooled with FB |
| FB | 13.3% | 76.9% | 13 plays, pooled with F |

**F and FB share one + rate, because they are the same play with a different
number of outs recorded.** 45 of the 56 F plays read "reached on a fielder's
choice; [runner] out at second", and not one of the 56 mentions a throw to 1st.
The 49 ground-ball double plays are the identical fielding sequence with "to 1b"
on the end -- "ss to 2b" against "ss to 2b to 1b". An F is a double-play attempt
whose relay did not retire the batter, so whatever the other runners do on one
they do on the other. Measured apart the two read 1 of 2 and 9 of 11, which is
no evidence of a difference (Fisher exact p = 0.42); pooled they are 10 of 13 =
76.9%, and the rate rests on 13 plays instead of 2. **DECISION (user, 21 Sep).**
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

Every pitcher and batter has a full card. Six lines are printed -- K, BB, HBP,
HR, 1B, Out -- and together they fill that player's block of the d100 (section
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
| | flat 5% and 2% vs the measured 4.54% and 2.22% | round levels no worse and nominally better (log loss x1000 -0.151, SE 0.348; -0.236, SE 0.308). **Chosen: 5 and 2 cells** | `band_two_level.py` |
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
| 33-36 | **double** | 4 cells |
| 37-38 | **reached on error** | 2 cells |
| 39-44 | **running play** | 6 cells |
| 45-99 | the **batter's** card | 55 cells |

Each card spreads its own block over its six printed lines, so a roll lands in
exactly one cell of exactly one card and the player reads the line off it. No
arithmetic, no lookup table, no second roll to decide whose card to use.

**The running-play block is the odd one out.** A wild pitch, passed ball or balk
advances every runner and the roll is then *taken again*, so those six cells do
not resolve a plate appearance at all (section 6). A card is therefore a
distribution over the **94 cells that do end a plate appearance**, not over all
100, and the bands divide by 94: doubles at 4/94 = 4.26% and errors at 2/94 =
2.13%, against measured rates of 4.54% and 2.22%. With the bases empty the block
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
Within that range the user chose the value that makes the cells round. The
running-play block later forced the split to be redrawn (section 6), and 33 / 4 /
2 / 6 / 55 lands the weight on 33/88 = 0.375 exactly -- a move of 0.003, far
inside the flat region, so the k were not refitted. **DECISION (user, 21 Sep).** A parameter this flat is a choice inside a range, not a
measurement (section 9.0).

**The bands.** 2B and ROE sit on neither card because neither shows real spread
on either side: a flat league rate predicts held-out doubles better than the
batter's own record by 3.9 SE, and the pitcher's record is worse still
(`line_owner.py`). Printed at 5 and 2 cells against measured rates of 4.54% and
2.22%, the round levels score no worse and nominally better (log loss x1000:
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

**As built** (37 games, `pixi run dice`): every pitcher card fills its 33 cells
and every batter card its 55; no pitcher entry is at zero and 47 of 402 batter
entries are; **0 of 2,479 matchups have a line that cannot happen**; the table
gives 71.3 league home runs against 69 actual.

**The 1% floor** applies once, to the combined distribution, after the two cards
are put together -- never to a card (section 3).

## 5. Handedness

Handedness rides on every batting and pitching row (`parse.py`, modal per
person; the feed contradicts itself for 10 of 80 players). The league is 54
right / 17 left / 2 switch at the plate, 61 right / 12 left on the mound. Of
2,663 plate appearances, 1,668 are same-handed and 995 opposite (switch hitters
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

- **The running-play line** covers wild pitches, passed balls and balks: 87 / 12
  / 18 in the training games, 117 in all. Every runner advances one base, then
  roll again for the plate appearance. It owns **6 cells** of the d100 (section
  4). With the bases empty it is a plain reroll, about once every 43 plate
  appearances. **DECISION (user, 21 Sep).**
- **Six cells, not the four "4.2% of rolls" implied.** Every one of the 117 plays
  on record happened with a runner on, so the block is dead 39% of the time and
  has to be bigger to land the same rate. Against rolls that can actually produce
  one -- the 1,621 plate appearances that began with a runner on, plus the running
  plays themselves -- the rate is 6.5%, not 4.2%. Four cells would produce 69
  plays a season against 117 actual, a 38% undercount.
- **It is on neither card.** Sweeping the smoothing constant, where k = inf *is*
  the flat band, the best k against the league is 1024 and beats the flat band by
  0.48 SE -- a tie. Smoothing toward the player's usage cohort instead is worse
  than ignoring pitcher identity altogether (log loss 99.5-99.9 against 98.27),
  because a cohort's own running-play count is too small to be a better target
  than the league rate. So the line joins doubles and errors as a fixed band.
  (`running_plays.py`, `running_k.py`)
- **What that result cannot say.** The feed records one of these plays only when
  it has a visible consequence -- all 117 describe a runner advancing or scoring,
  and the one wild pitch on record with the bases empty appears only because the
  batter reached on a dropped third strike. A pitch the catcher blocks never
  enters the data. So each pitcher's observed rate is her wildness times one
  minus her catcher's block rate, the two cannot be separated, and the part that
  was prevented is invisible. The spread is **censored, not absent**: what the
  test establishes is that at this sample size, on the quantity the game needs,
  no pitcher differentiation earns its place. **ASSUMPTION.**
- **The knuckleballer.** Liz Gilder threw 8 wild pitches in 282 pitches with a
  runner on, 2.84% against a league 1.43% -- twice the field, on eight events.
  Named here so it is revisited rather than lost in a null result, as the slugger
  exception was (section 3.3). Keira Izumi and London Studer sit higher still,
  but they are position players pressed into pitching by a league-wide shortage
  of arms, which is inexperience rather than a repeatable trait.
- **Balks and the umpire.** 18 balks, and the rate falls 3.6x after game 22
  (4.41 per 1000 pitches with a runner on, against 1.22), which is consistent
  with the mid-season replacement of an umpire who called them freely. It is not
  established: a changepoint test that prices the search over all split points
  gives p = 0.17, and 18 events cannot carry more than that. The band is set at
  6 cells, which is what both ways of acting on the theory give -- applying the
  post-change rate (~106 plays) and dropping balks entirely (99) both round to 6,
  while keeping all 117 rounds to 7. Capping at one balk per game, the other
  proposal, removes only 4 and still rounds to 7. **DECISION (user, 21 Sep).**
- **Steals are a decision, not a line.** The offense declares before the roll;
  only the resolution is random. 128 attempts, 107 successful.
- **A league-rate stand-in exists for the validation only** (`engine.steal`),
  because a check that never steals reproduces only the half-innings nobody stole
  in. Attempts per plate appearance by state: `1__` 0.145, `1_3` 0.370, `_2_`
  0.047, `12_` 0.035; success 83% stealing 2nd, 88% stealing 3rd. It resolves
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
- **Tired columns.** **ASSUMPTION**: a pitcher card carries fresh / tired /
  gassed columns; the pitch track selects one; tired columns shrink K and widen
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
  usage targets above already describe; the tired column should shrink K and
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
| capacity, starter / reliever | **anchored**: median 68 / 31 pitches, max about 100 for both |
| daily recovery | **start at 14 pitches a day** (user, 22 Sep): a starter recovers 84 over six days, about her 68-pitch outing, and 98 over a week against the 85 load. Relief-only weeks run 45 |
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

What varies is BATTERS FACED. An inning averages 4.80 batters (SD 1.84) and 17.5
pitches (SD 7.8), and a pitcher who cannot get outs faces more of them. So a
plain pitch count already burns faster for her, by the batter rather than by the
pitch -- the compounding arrives on its own, without a surcharge and without
distorting a measured quantity. **DECISION (22 Sep): the track counts measured
pitches, unweighted.**

**Measure in innings, implement in pitches.** The decline is measured per inning
because pitches are endogenous; the track counts pitches because that is the work.
The conversion is 17.5 pitches an inning, and it is noisy -- a coefficient of
variation of 0.44 -- so the step should be applied on the track's own scale rather
than by pretending an inning is a fixed quantity of work. Batting around is rare
enough not to matter: 1.7% of innings face ten or more batters and 1.9% see a
batter twice.

### 7.3 What a tired column looks like

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
| tired | 0.5x | +0.020 | 3 | 3 | 5 | 2 | 2 | 6 | 15 |
| gassed | 1.0x | +0.032 | 3 | 3 | 5 | 2 | 2 | 7 | 14 |

Three cells of 33 between fresh and gassed -- small enough to print on one card as
three columns, and large enough for a player to feel. **DECISION (22 Sep): size
anchored at G3's own shift, not at the +0.09 step.** The rounding is why tired and
gassed differ by only one cell despite differing by half the shift; at 33 cells
the mechanic has about that much resolution, which is an argument for two tired
states rather than four.

### 7.4 The track: thresholds, and what it is for

**There is no burn multiplier** (`burn_or_capacity.py`). Other games give a
reliever one fresh inning against a starter's three, which is where a 3x burn
rate comes from. Within an outing a rate and a capacity are algebraically the
same thing -- a threshold of 31 at rate 1 behaves exactly like 93 at rate 3 --
so nothing could distinguish them there. Across days they differ, and the data
decides: at rate 3 a reliever's 31-pitch outing puts 93 on her track and needs
6.6 days to clear at 14 a day, while she actually rests 5. She would arrive
tired every time. At rate 1 she carries 31, clears in 2.2 days, and shows up
fresh, which is the observed rhythm. **DECISION (22 Sep): capacity carries the
role difference; there is no burn parameter.** The model has no free parameters
left.

Observed rhythm, for the record: relievers 31 pitches every 5 days (6.2 a day
sustained), starters 68 every 6 (11.3 a day). Seven-day loads reproduce section
7's targets exactly -- 45 relief-only, 85 for a week with a start.

**The cross-day track rarely binds, and that is the point.** At 14 pitches a day
four outings in five start from zero, and the mean carried in is 2.5 pitches in
the regular season and 2.6 in the postseason -- the playoffs are not tighter
(median rest 5 days against 6). So the track is not reproducing something real
managers hit. **It exists to stop the PLAYER doing what a real manager would
not** -- running one arm out every game -- and the fact that real usage almost
never engages it is evidence the limit is set in the right place, not that it is
useless. **ASSUMPTION.** (The figure looks only at the previous outing; a track
that sums will bite harder on back-to-back appearances.)

**Thresholds** follow from the measured shape. The decline is a step after her
first inning and flat after (section 7.2), and an inning is 17.5 pitches (section
7.2), so:

| column | starter | reliever |
|---|---|---|
| fresh | 0-17 pitches | 0-17 |
| tired | 18 to 68 | 18 to 31 |
| gassed | past 68 | past 31 |

A starter reaches gassed at her median hook of 68; a reliever is fresh for about
the first half of a median 31-pitch outing. Both boundaries are measured
quantities rather than chosen ones. **DECISION (22 Sep).**

### 7.5 As built (22 Sep)

`dice.fatigue_card` makes the three columns; `engine.sim_fatigue` plays with them.

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
top of it counts that twice: uncentred, the game scored 8.31 runs a team-game
against a season 7.77. Centring shifts all three columns so their usage-weighted
mean returns her card exactly -- a **fresh pitcher is better than her season
line**, a gassed one worse, the average unchanged -- and scoring returns to 7.95,
which is the engine's pre-existing level. **DECISION (22 Sep).** The weights come
from one pass of the pull rule (fresh 43%, tired 45%, gassed 12%); re-running with
centred columns moves them by well under a point.

**The pull rule is descriptive**: a stint length is sampled from the real
distribution by role and the pitcher comes out when her track passes it. That is
all that is needed to make a fatigue setting identifiable -- a setting only has
consequences where a tired pitcher is left in. It is not the AI manager of check
3.

**Against the season:**

| | dice | season |
|---|---|---|
| runs per team-game | 7.97 | 7.77 |
| median starter stint, pitches | 70 | 69 |
| starter p25 / p75 | 61 / 81 | 60 / 79 |
| median reliever stint | 25 | 30 |
| pitchers per team-game | 3.45 | 2.80 |

The starter distribution matches closely. **OPEN:** relievers run short and the
game uses too many of them, because each is sampled independently and the last
one is cut off by the end of the game rather than by her target. A staff plan
rather than independent draws would fix it, and that is the AI manager's job. The
2.6% excess in scoring predates fatigue -- the engine ran 8.02 before any of this
(section 9.1) -- so centring has left the run environment where it found it,
which is what it is for.

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
4.0% of out plays, too small for a cell of a d12, and the pooled + rate of 76.9%
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
   land on the usage targets in section 7. **OPEN**, and blocked on section 7.

### 9.1 The league check, as run (22 Sep)

`pixi run engine` (`src/wpbl/engine.py`) plays the printed game -- it rolls a
d100 against the cell table, rerolls on a running play, rolls a d12 for the out
flavor and the single -- rather than modelling it. Cards and pitchers are drawn
in proportion to use, which matters: the league-average card rounded into 33 and
55 cells prints home runs at 3.19% against the card's own 2.59%, a 23% relative
inflation, because both blocks scale one rate and both round the same way. Real
cards average that out (batter mean bias -0.086 cells on HR), so a check run
league-against-league validates a table nobody will play with.

| | dice | season |
|---|---|---|
| run expectancy, mean absolute difference over 24 states | 0.105 runs | -- |
| ... states where the dice are high | 13 of 24 | -- |
| transition distance, PA-weighted (`engine_transitions.py`) | 0.095 | 0.076 from sampling alone |
| runs per half-inning | 1.146 | 1.132 |
| scoreless half-innings | 54.0% | 50.8% (+/- 2.2) |
| runs per 7-inning game, one team | 8.02 | 7.77 |
| leadoff lineup slot 1 | 23.6% | 25.4% |

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

**The residual.** Scoreless innings run 3.2 points high, which is 1.44 SE against
the 506 observed half-innings behind the target. Five explanations were tested
and are not worth retesting without more games:

| tested | effect on the gap |
|---|---|
| the old "two outs, run on anything" rounding | real, 0.5 pts -- now fixed |
| the runner from 1st on a single (the `+` level) | real, 0.5 pts -- now fixed |
| steals missing entirely | real, 1.2 pts -- now fixed |
| league card vs cards drawn by use | rejected, 0.3 pts |
| lineup order vs batters drawn independently | rejected, 0.4 pts |

The lineup-order test is a caution worth keeping: on 15 starters-only lineups it
appeared to close 1.5 points, and on all 74 team-game lineups with substitutions
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

- The feed misspells names in some box scores (accents dropped, "Naraski",
  "Maggie Fox"), which had split three players in two and names a pitcher "/"
  in championship G2. Fixed in `parse.py` with a check in `pixi run check`
  (commit f2f50f8).
