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

Evidence (`proposals.py`, 37 training games): of 514 PAs with runners on, <2
outs and an out made, these lines reproduce 482 (94%).

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

The family share is solid; the pooled + rate still rests on 13 plays. Dropped
from it are plays whose inning ended (28 of 305), because the feed never shows
the bases after the third out, and plays where the + changes nothing visible --
most of them, since with a runner forced out the batter takes the base the
runner left. The force matters far more than anything a card could carry: with a
runner on 1st the mix is B 63.5% / F 19.1% / FB 17.4%, without one B 96.4%.
**OPEN:** the 13 visible plays are selected by which base states make the +
visible, and F and FB are selected differently (2 against 11), so pooling also
assumes the + does not vary by base state -- untestable at this size. **OPEN:**
there is no measurement at 2 outs at all. **OPEN:** the 514 above and the 399
here come from different filters in two scripts and have not been reconciled.

**Singles:** Single+ (the runner from 2nd scores) is 42% of singles with 0-1
out; with 2 outs it is 67%, and the game treats every two-out single as a
Single+. Notation: Single+ rows, plus Single rows marked "acts as Single+ with
2 outs". **DECISION (user, 17 Sep).** **OPEN:** the rule was chosen when the
two-out figure read 76% on 36 games; at 67% (`pixi run advance`) "always" is a
larger rounding than it was.

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
- Home runs the batter cards produce: 68.8 against 69 actual. The printed cell
  table gives 70.6 (section 4.1). **OPEN:** whether cards must preserve league
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
| BB \| HBP k | one shared value for both sides | the full 18x18 grid returns 2.83 on each side independently; the shared value costs +0.000, so it is a result, not a simplification | `split_k_final.py` |

## 4. Combining pitcher and batter: the d100 table

**DECISION (user, 21 Sep).** One d100 resolves a plate appearance. Its hundred
cells are split into fixed blocks:

| Cells | Read | Size |
|---|---|---|
| 00-34 | the **pitcher's** card | 35 cells |
| 35-39 | **double** | 5 cells |
| 40-41 | **reached on error** | 2 cells |
| 42-99 | the **batter's** card | 58 cells |

Each card spreads its own block over its six printed lines, so a roll lands in
exactly one cell of exactly one card and the player reads the line off it. No
arithmetic, no lookup table, no second roll to decide whose card to use.

**Reading one card or the other is the combination rule.** The mechanic is a
mixture:

    p = a * (pitcher's card) + (1 - a) * (batter's card)

with a = 35 / (35 + 58) = 0.3763, the pitcher's share of the cells that are not
a band. It sums to 100% because exactly one card is read, and it gives every
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
Within that range the user chose the value that makes the cells round: 35 / 5 /
2 / 58 is the split near it with whole blocks and round bands. **DECISION
(user, 21 Sep).** A parameter this flat is a choice inside a range, not a
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

1. scale the card to the block size (58 or 35);
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

**As built** (37 games, `pixi run dice`): every pitcher card fills its 35 cells
and every batter card its 58; no pitcher entry is at zero and 47 of 402 batter
entries are; **0 of 2,479 matchups have a line that cannot happen**; the table
gives 70.6 league home runs against 69 actual.

**The 1% floor** applies once, to the combined distribution, after the two cards
are put together -- never to a card (section 3).

## 5. Handedness

Handedness rides on every batting and pitching row (`parse.py`, modal per
person; the feed contradicts itself for 10 of 80 players). The league is 54
right / 17 left / 2 switch at the plate, 61 right / 12 left on the mound.

Handedness lives in the **league table**, not on the cards: certain cells read
one way when the hands match and another when they oppose. **DECISION (user).**

| | Same hand | Opposite | Gap |
|---|---|---|---|
| K | 12.8% | 10.3% | 2.5 points |
| Hits | 27.2% | 29.3% | 2.1 points |
| BB+HBP | 16.6% | 15.7% | 0.9 points |

So a few cells on the K/out boundary and the out/single boundary switch
meaning. Home runs get no platoon cell: the measured gap points the wrong way,
which on 64 home runs is noise. Switch hitters always take the opposite-hand
reading. **ASSUMPTION**: the platoon gap is real at roughly this size; our
opposite-hand cell holds 846 plate appearances (±2 points on K).

## 6. Running plays and steals

- **The running-play line** (4.2% of rolls) covers wild pitches, passed balls
  and balks: 79 / 9 / 18 in the training games. Every runner advances one base,
  then roll again for the plate appearance. With the bases empty it is a reroll,
  which happens about once every 60 plate appearances.
- **Steals are a decision, not a line.** The offense declares before the roll;
  only the resolution is random. 119 attempts in 34 games, 99 successful.
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
- **What the data cannot say.** Observed decline with pitch count is biased,
  because managers pull pitchers who are struggling. Semifinal G3 (14 Sep) is
  the one clean look at exhausted bullpens — high on-base, 26 runs — and it is
  excluded from every other fit for exactly that reason. Fatigue strength is a
  tuned setting, not an estimate. **OPEN**: the shape and size.

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
**ASSUMPTION:** a d12, because the out flavors do not divide into tenths.
**OPEN:** confirming the die once the out-flavor bands are fixed (section 2).

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

1. **League check.** All-league cards, simulated under the dice rules, must
   reproduce the Markov run-expectancy table (1.17 runs from bases empty,
   nobody out) and the half-inning run distribution (about 50% scoreless).
2. **Spread check.** With real cards, the spread of player outcomes must match
   the smoothed spread, with dice rounding neither erasing nor exaggerating it.
3. **Fatigue tuning.** A simple AI manager's stint lengths and 7-day loads must
   land on the usage targets in section 7.

## 10. Open questions

- Out flavors: fixed bands on the extra die or fractions of each matchup's outs
  (section 2). The + rates for F and FB rest on 2 and 11 plays, and there is no
  measurement at 2 outs at all.
- The two-out Single+ rule, chosen when the figure read 76% on 36 games and now
  reading 67% (section 2).
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
