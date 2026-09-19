# WPBL dice baseball — design spec

A two-player tabletop baseball game with cards and dice, using the 2026 WPBL.
One roll resolves a plate appearance. Both players set lineups and make the
pitching decisions; computer agents will be needed to test the game. It may
precede or replace the bullpen simulator (`bullpen_spec.md`). **DECISION
(user, 17 Sep).**

Status: design; player cards built (`pixi run dice`, section 3). Numbers are
from this repo's training scope: 36 games (the 30-game regular season,
semifinal G1-G2 of both series, and championship G1-G2). Semifinal G3 (14 Sep)
is excluded because both bullpens were exhausted (`tables.TRAINING_EXCLUDED`);
later championship games join training unless the same happens, decided game by
game. **DECISION (user, 17 Sep).** Items marked **ASSUMPTION** are choices, not
findings; items marked **OPEN** are undecided.

Policy: the probability distribution must reflect the data first; game
mechanics are then designed to reproduce it. Which card carries which line is
a finding, not a rule. **DECISION (user, 17 Sep).**

## 1. The chain

A play is a transition between base-out states, as in `markov.py`. The engine
needs nothing else: state is inning, half, outs, which bases are occupied,
score, and each pitcher's fatigue.

Design rule: **fidelity stops where the data stops.** 2,584 plate appearances
cannot support runner-by-runner advancement rules, so runner movement is fixed
per outcome line, with one variant line where the data shows a real coin flip.

## 2. Outcome lines

Lines are defined by what happens to the base-out state, not by the play's
label. **DECISION (user, 17 Sep).** Labels hid the defect this fixes: the
15 Sep table priced 53 fielder's choices and 6 singles with a runner thrown
out as singles, losing 59 outs (roughly one run per team per game too many).

**Outs** come in three flavors, each with an optional + modifier:

| Flavor | With a force at 1st | Without one |
|---|---|---|
| B | batter out | batter out |
| F | runner from 1st out at 2nd, batter to 1st, forced runners advance one | as B |
| FB | batter and runner from 1st out, other forced runners advance one | as B |
| + | unforced runners also advance one (B+: every runner advances one) | |

Evidence (36 training games): of 497 PAs with runners on, <2 outs and an out
made, these lines reproduce 468 (94%).

- F uses the force at 2nd: of 27 fielder's choices with 2+ forced runners,
  18 took the runner from 1st and 9 the lead runner. A lead-runner fielder's
  choice leaves the same base-out state as B, so both kinds are covered.
- FB: 10 of 11 nobody-out double plays retired the batter and the runner from
  1st; in all 9 ground-ball double plays from 1st and 2nd, the runner from 2nd
  reached 3rd.
- Sacrifice flies are B+ (the runner from 2nd also advances). **DECISION (user).**
- The other unreproduced plays (hits with a runner thrown out, non-force double
  plays) map to the line nearest in run value. **DECISION (user).**

**Singles:** Single+ (the runner from 2nd scores) is 40% of singles with 0-1
out; with 2 outs, every single is a Single+. Notation: Single+ rows, plus Single
rows marked "acts as Single+ with 2 outs". **DECISION (user, 17 Sep).**

**Errors:** ROE is its own line, by label, and is excluded from Single and
Double. The 15 Sep table counted the 14 ROE that put the batter on 2nd twice.

**Doubles** include triples (none in the training games). **Running plays**
(wild pitch, passed ball, balk) remain a league line: every runner advances one,
then roll again; with the bases empty it is a reroll.

Line shares, and each out flavor's share of outs, are to be measured by
`pixi run dice` (not yet added). **OPEN:** whether out flavors are fixed dice
bands (fire rates, as in the 15 Sep table) or fractions of each matchup's outs.

## 3. Player cards

Every pitcher and batter has a full card: K, BB, HBP, HR, 1B, 2B, ROE, Out,
summing to 100%. Smoothing decides how far each player differs from her
cohort; no line is left off a card by rule. This replaces the 15 Sep rule that
an entry exists only if its league spread exceeds one dice cell, and the batter
ground-ball entry is dropped. **DECISION (17 Sep).**

`pixi run dice` (`src/wpbl/dice.py`) builds every card and writes
`data/dice/cards_batters.csv` and `data/dice/cards_pitchers.csv`. The tuning
runs behind the constants below are analysis, not part of the module.

### 3.1 Smoothing in steps

Outcomes are split step by step. Each step divides a group of outcomes and is
smoothed toward the player's cohort with its own constant k:

    step share = (her count + k * cohort share) / (her count at the step + k)

A card line is the product of the shares along its path, so cards sum to 100%
and outs are an explicit outcome, not a remainder. A hole in one outcome can
be filled only from within its own step: smoothing cannot give a player hits
she did not make. **DECISION (user, 18 Sep).**

**Batters** (working choice, still exploratory):

| Step | Split | k | Tuned inside build halves: median (middle half) |
|---|---|---|---|
| 1 | true outcomes (K+BB+HBP+HR) \| in park (1B+2B+ROE+Out) | 45 | 16 (6-197) |
| 2 | HBP \| K+BB+HR | 2 | 7 (3-1448) |
| 3 | HR \| K+BB | 5.7 | 6 (3-9) |
| 4 | K \| BB | 16 | 13 (8-23) |
| 5 | 1B \| 2B+ROE+Out | 64 | 64 (32-304) |
| 6 | Out \| 2B+ROE | 256 | 64 (32-inf) |
| 7 | ROE \| 2B | 16 | inf (1-inf) |

Inside each branch, two-way splits run in order of increasing k (the most
individual outcome first).

**Pitchers:**

| Step | Split | k | Tuned inside build halves: median (middle half) |
|---|---|---|---|
| 1 | K \| not K | 45 | 32 (21-64) |
| 2 | BB / HBP / in play | 256 | 64 (21-inf) |
| 3 | Out / ROE / hit | 181 | 362 (91-inf) |
| 4 | HR / 1B / 2B | inf (the cohort's mix) | inf (83-inf) |

The k column is each step's best score on all 20 game splits (section 3.4).
The last column is the same tuning repeated inside each build half of the
nested test: a narrow middle half means the step's k is well determined (batter
HR \| K+BB, K \| BB; pitcher K), and one spanning most of the grid means almost
any value fits equally well (ROE \| 2B: both rare, with no measurable batter
signal, so its 16 is noise).

Every line is floored at 1%; lines raised to the floor take their extra share
from the other lines in proportion, so the card still sums to 100%.
(Renormalizing the whole card would push the raised lines back under 1%.)

### 3.2 Cohorts

- Ranked by usage, never by performance (a performance ranking is circular):
  batters by share of team games started, pitchers by share of team batters
  faced. **DECISION (user, 17 Sep).**
- Share is measured over the player's tenure with each team; a traded player's
  tenure splits at her first game for the new team. **ASSUMPTION.**
- Cohort = nearest players by share, excluding her, until they total 300 PA
  (batters) or 300 BF (pitchers). Tied players enter together, so the 8
  everyday starters form one group. **DECISION (user).** Tested (nested): for
  batters 150 is worse than 300 by 2.3 SE and 600 is no better; pitchers are
  insensitive to the size.
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

- **k:** each step's k is the best held-out score (section 9.0) on a grid of
  powers of sqrt(2) from 1 to 2048, plus inf. The best score is used; there is
  no tie rule. **DECISION (user, 18 Sep).**
- **Structures:** compared by nested cross-validation, where k is tuned only
  inside each build half. Results are held-out runs error, x1e-6 per PA:

| Comparison (batters) | Difference (SE) |
|---|---|
| per-line smoothing (8 k, renormalized) minus 4-step tree | +159 (316): tie |
| chain (HBP, K, BB, HR \| contact, hit \| fielded, 2B \| 1B, ROE \| out) minus tree | -169 (413): tie |
| true outcomes first, then increasing-k chains (above) minus chain | **-360 (193)** |
| true outcomes first, other branch orders minus chain | +129 to +290: chain better |
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
  traits (tuned k about 16, middle half 6-197). Once that total is smoothed,
  the mix inside it needs little smoothing (HR \| K+BB about 6, middle half
  3-9; K \| BB 13, middle half 8-23).
- **Caveats:** the correlations and the in-branch order used all 36 games,
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

### 3.5 What the cards look like

Runs above an average PA, x1000:

| | Raw | Card |
|---|---|---|
| Benites | 359 | 279 |
| Whitmore | 177 | 202 |
| Lansdell | 199 | 108 |
| Jorge | 136 | 85 |

- Spread among batters with 25+ PA: 128 raw, 76 on cards.
- Home runs the batter cards produce: 71.4 against 67 actual. **OPEN:** whether
  cards must preserve league totals.
- **OPEN:** optional fan-facing "replay" cards with k shifted toward raw.

### 3.6 What was tested (don't retest without new data)

Every alternative tried, with its result. Scripts are in `analysis/dice/` (see
its README). "Nested" results are held-out runs error, x1e-6 per PA, SE in
parentheses, against the comparison named.

| Area | Tested | Result | Script |
|---|---|---|---|
| Target | one league average | flattened regulars; overrated bench (low-PA batters strike out 16.5%, homer 0.4%) | `recon.py` |
| | halves of PA, straight line between (quartile anchors) | rates not linear in PA (K steps down after the bench; HR jumps at the sluggers) | `followups.py`, `deciles.py` |
| | sliding cohort ranked by PA share | sorts everyday players by lineup spot | `cohort_cards.py` |
| | ranked by quality (context-neutral runs, FIP) | not run: circular | |
| | cohort 150 / 300 / 600 | batters: 150 worse by 2.3 SE, 600 no better; pitchers insensitive | `cohort_cv.py` |
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
| Pitcher structure | 4-step tree | **chosen** | `trees_cv.py` |
| | chain ordered HBP first | worse than tree by 1.5 SE: +252 (169) | `chain_cv.py` |
| | chain ordered K first | tie: -66 (111), +137 (142) | `pchain_cv.py`, `cchain_cv.py` |
| | K first, HR grouped with hits | tie with K-first chain: +16 (52) | `cchain_cv.py` |
| Combination (section 4) | additive, flat log5, two-level log5, averaging | three tie; averaging halves player differences | `combine_fullpos.py` |

## 4. Combining pitcher and batter

**OPEN (waiting for more games).** On held-out games, three rules tie within
0.7 SE: additive (league + both deviations), flat log5 (every line multiplied by
both cards' ratios to league, then renormalized), and two-level log5 (K / BB /
HBP / in play, then within in play). Averaging the two cards is rejected: it
predicts player differences at about half their real size (calibration slopes
2-4). Players cannot do log5 in their heads; if it is chosen, the game ships a
lookup table. These tests used earlier cards; rerun on the section 3 cards.

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

Candidate schemes, all resolving a plate appearance in one throw:

1. **Two colors of 3d10 (pitcher thousandths, batter thousandths).** Independent
   lookups, 0.1-point cells, probabilities multiply exactly. Six dice.
2. **d100 pitcher + d1000 batter.** Five dice, coarser where the pitcher's
   entries are wide anyway, fine where the batter's rare lines need it.
3. **Single d100, cells split between the cards** (the Strat-O-Matic form).
   Cheapest to read, but 1-point cells and card capacity limits.

**OPEN**: which scheme, and whether the pitcher and batter lookups should be
independent or deliberately dependent (depends on section 4).

## 9. Validation

### 9.0 How card choices are evaluated

- Held-out by game: random halves of the training games; cards built on one
  half score the other; 20 splits.
- Score: squared error of expected run value per PA (linear weights) first,
  pitches per PA second; log-likelihood is diagnostic only. Errors in
  high-value lines count more (a missed home run outweighs a missed walk).
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

- Combination rule (section 4): additive, flat log5 or two-level log5.
- Out flavors: fixed dice bands or fractions of each matchup's outs (section 2).
- Predict vs replay: optional fan cards with smaller k; fans may not accept
  Benites's card dropping about a fifth (her 65.5% hits per ball in play).
- Whether cards must preserve league totals (home runs run 71 against 67).
- The dice scheme (section 8).
- Catcher and runner ratings for the steal game.
- Fatigue shape, size, and how readiness is reported.
- Computer agents for testing: lineup and pitching decisions.
- Whether the bullpen spec's tryout-arm rule applies here (usage cohorts
  currently cover low-use pitchers). **ASSUMPTION.**

## Data notes

- The feed misspells names in some box scores (accents dropped, "Naraski",
  "Maggie Fox"), which had split three players in two and names a pitcher "/"
  in championship G2. Fixed in `parse.py` with a check in `pixi run check`
  (commit f2f50f8).
