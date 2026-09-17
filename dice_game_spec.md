# WPBL dice baseball — design spec

A tabletop baseball game played with cards and dice, using the 2026 WPBL as its
league. One roll resolves a plate appearance. The player manages pitching; the
decisions that matter are when to go to the bullpen and who to bring in.

Status: design, nothing built. Numbers are measured from this repo's training
scope (34 games: the 30-game regular season plus four of the five playoff games;
semifinal G3 on 14 Sep is excluded — see `tables.TRAINING_EXCLUDED`). Items
marked **ASSUMPTION** are choices, not findings; items marked **OPEN** are
undecided.

## 1. The chain

A play is a transition between base-out states, as in `markov.py`. The engine
needs nothing else: state is inning, half, outs, which bases are occupied,
score, and each pitcher's fatigue.

Design rule: **fidelity stops where the data stops.** 2,435 plate appearances
cannot support runner-by-runner advancement rules, so runner movement is fixed
per outcome line, with one variant line where the data shows a real coin flip.

## 2. Outcome lines

Twelve lines. Shares are of all rolls, from the training games, with the 106
running plays counted as rolls of their own (so every plate-appearance line is
scaled by 0.958).

| Line | Share | Transition |
|---|---|---|
| Out | 16.7% | batter out, nobody moves |
| Out+ | 12.4% | batter out, every runner advances one base |
| Single | 12.4% | batter to 1st, runners advance one |
| BB | 12.2% | batter to 1st, forced runners only |
| K | 11.4% | batter out, nobody moves |
| Out− | 8.4% | two out if a force exists, else a plain out |
| Single+ | 8.2% | batter to 1st, runner from 2nd or 3rd scores |
| Double | 5.9% | batter to 2nd; all runners score except the one from 1st, who stops at 3rd |
| WP / PB / balk | 4.2% | every runner advances one; bases empty, roll again |
| HBP | 3.4% | batter to 1st, forced runners only |
| HR | 2.5% | everyone scores |
| ROE | 2.2% | as a single |

Notes:

- **K and Out are the same transition.** They stay separate because the pitcher
  owns strikeouts on the card and because a strikeout costs 4.9 pitches against
  3.3 for a ball in play.
- **Two outs: runners go on contact.** Standard rule, and the data shows it: a
  runner scored from 2nd on a single 41% / 37% of the time with 0 / 1 out, and
  76% with 2 outs.
- **Single+ is 40% of singles** with fewer than two outs (measured 39%), and
  means the runner from 2nd scores. A runner from 1st never reaches 3rd on a
  single: that happened 14% of the time, below what this sample supports.
- **ROE has no player signal** on either side; keep the line only if team
  defense should matter later. **OPEN**.
- **Triples are folded into doubles.** Zero occurred in the training games.

### 2.1 Conditional lines

Out− and Out+ fire on every roll but only do anything when their condition
holds; otherwise they read as a plain out. Their shares are therefore divided
by how often the condition holds:

| Line | Condition | Condition holds | Line share | Reproduces |
|---|---|---|---|---|
| Out− | force at 1st, <2 outs | 25.5% of PAs | 8.8% of PAs | 2.26% double plays = observed |
| Out+ | any runner, <2 outs | 37.3% of PAs | 12.9% of PAs | 4.80% advancing outs = observed |

(The table in section 2 shows these scaled by 0.958 for the running-play line.)

The out lines were measured from transitions, not from play labels. Labels
would have missed 9 double plays on lineouts and 75 ground outs that advanced a
runner.

## 3. Player cards

Every card entry is a smoothed probability, printed as a range of dice numbers.
No grades or tiers: grades add a tuning layer and quantization error for
nothing. **DECISION (user, 15 Sep).**

### 3.1 Which entries exist

An entry exists when the spread of smoothed values across the league is at
least one dice cell; otherwise every card would print the same number.

| Card | Entries |
|---|---|
| Pitcher | K, BB |
| Batter | K, HR, HBP, Single, ground-ball share of outs |
| League table | Out / Out+ / Out− total, Single+, Double, ROE, running plays |

The batter's ground-ball entry shifts the split *within* the out family. Ground
balls turn two 53% of the time when a force exists, against 8% for air outs,
and advance a runner 61% against 20%. So one ground-ball number moves Out− and
Out+ together: a batter one standard deviation to the ground side gains about
1.5 points of Out− and 1.4 of Out+.

The pitcher has no out-split entry: her ground-ball spread is 0.53 points,
which is a quarter of a cell.

### 3.2 Smoothing

Each entry is smoothed toward the league on its own stability constant:

    card = (n * own rate + k * league rate) / (n + k)

where n is that player's plate appearances or batters faced. The constants come
from a method-of-moments split of observed spread into real spread and sampling
noise:

| Entry | League | k | Where 50% of a card is the player's own record |
|---|---|---|---|
| Pitcher K | 12.2% | 47 | 47 batters faced |
| Pitcher BB | 11.6% | 73 | 73 |
| Batter K | 11.4% | 36 | 36 plate appearances |
| Batter HR | 2.9% | 34 | 34 |
| Batter HBP | 3.8% | 33 | 33 |
| Batter single | 20.4% | 180 | 180 |
| Batter ground share | 46.8% | 57 | 57 outs |

These match the published MLB reliability work in spirit: Carleton's figures of
60 plate appearances (batters) and 70 batters faced (pitchers) for 0.7
reliability on strikeout rate correspond to our k of 36 and 47.

### 3.3 What the smoothed cards look like

38 pitchers, 68 batters, all percentages.

| Entry | min | p10 | median | p90 | max | SD |
|---|---|---|---|---|---|---|
| Pitcher K | 6.0 | 7.9 | 12.2 | 15.4 | 22.7 | 3.2 |
| Pitcher BB | 6.0 | 9.5 | 12.4 | 15.8 | 19.6 | 2.7 |
| Batter K | 4.0 | 8.6 | 11.1 | 16.2 | 24.4 | 3.6 |
| Batter HR | 0.9 | 1.2 | 2.1 | 4.0 | 12.1 | 2.0 |
| Batter HBP | 1.3 | 1.7 | 3.4 | 5.8 | 10.9 | 2.0 |
| Batter single | 17.6 | 19.0 | 20.3 | 21.9 | 24.8 | 1.4 |
| Batter ground share | 40.6 | 42.7 | 47.0 | 50.6 | 53.9 | 3.0 |

The rare lines are the demanding ones. Home runs span 0.9 to 12.1 points, so a
one-point cell collapses 68 batters into 7 distinct cards.

## 4. Combining pitcher and batter

log5, applied per line and renormalized:

    p(line) proportional to League(line) * (Pitcher(line) / League) * (Batter(line) / League)

with the twelve lines rescaled to sum to 1. Collapsed to two categories this is
exactly the log5 formula, and renormalizing plays the role of log5's
denominator.

Support: Healey, "Modeling the Probability of a Strikeout for a Batter/Pitcher
Matchup", IEEE TKDE 27(9), 2015 (PDF in this repo). Fitting the coefficients
freely on ~1M plate appearances returns log5's values within noise in all four
platoon configurations. The paper's batter share of variance in predicted
strikeout rate, 55-61%, matches this league: our smoothed spreads are 3.6 points
(pitcher) and 3.8 (batter), a 53% batter share.

Strikeouts are the only line on both cards, which is why this is the only place
log5 does any work. **ASSUMPTION**: log5 transfers from MLB to the WPBL; 34
games cannot test it.

The paper's ground-ball interaction term is left out: at our spreads it moves
strikeout probability by well under half a point.

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

Undecided. The requirement, from section 3.3: cells fine enough that two
players who really differ do not print the same card.

| Cell size | Mean error | Cost in runs/game | Distinct HR cards (of 68 batters) |
|---|---|---|---|
| 1.0 point (d100) | 0.24 points | 0.014 | 7 |
| 0.5 point (d200) | 0.13 | 0.008 | 12 |
| 0.1 point (d1000) | 0.03 | 0.002 | 31 |

In runs, even one-point cells cost almost nothing. What they cost is
distinctness: the home-run entry is the binding constraint, because its whole
league range is 11 points.

Candidate schemes, all resolving a plate appearance in one throw:

1. **Two colors of 3d10 (pitcher thousandths, batter thousandths).** Independent
   lookups, 0.1-point cells, probabilities multiply exactly. Six dice.
2. **d100 pitcher + d1000 batter.** Five dice, coarser where the pitcher's
   entries are wide anyway, fine where the batter's rare lines need it.
3. **Single d100, cells split between the cards** (the Strat-O-Matic form).
   Cheapest to read, but 1-point cells and card capacity limits.

**OPEN**: which scheme, and whether the pitcher and batter lookups should be
independent or deliberately dependent.

## 9. Validation

Before anyone plays:

1. **League check.** All-league cards, simulated under the dice rules, must
   reproduce the Markov run-expectancy table (1.17 runs from bases empty,
   nobody out) and the half-inning run distribution (about 50% scoreless).
2. **Spread check.** With real cards, the spread of player outcomes must match
   the smoothed spread, with dice rounding neither erasing nor exaggerating it.
3. **Fatigue tuning.** A simple AI manager's stint lengths and 7-day loads must
   land on the usage targets in section 7.

## 10. Open questions

- Whether ROE keeps its own line.
- Catcher and runner ratings for the steal game.
- Fatigue shape, size, and how readiness is reported.
- The dice scheme.
- Whether the opponent's offense runs on a simple AI, and how much of the
  lineup decisions the player makes.
