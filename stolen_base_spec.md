# Stolen bases — findings

> **Rebuilt 2026-10-01.** The original file was lost: it was never tracked in
> git, and a branch switch left no copy on disk. Every figure below was
> recomputed from `steals.py`, `steal_decision.py`, `steal_pitches.py`,
> `must_attempt.py` and `markov.py`, not transcribed. Sections 3, 4, 5, 6, 9,
> 10 and 11 reproduce the original's reasoning. Sections 1, 2, 7 and 8 are
> **reconstructed** from the scripts' own docstrings and output rather than
> recovered, so the wording is new even where the numbers are not. The d100
> face draft in section 9 is the one thing here that cannot be recomputed —
> it was a hand-laid table and is restored from a reading of the original.
> **Check it against your own intent before using it.**

Bin names are prefixed by the rating they belong to. Both ratings have a
default value and both were once called "league", so the prefix says which dial
a name is on: `attempt_goes` / `attempt_league` for the attempt rate,
`success_low` / `success_league` for success.

## 1. What the feed records

*(reconstructed)*

133 steal attempts in the play-by-play, 112 safe and 21 caught. Of the 21, 3
were pickoffs — the pitcher catching her leaning — and 18 were the catcher's.
The catcher box score agrees on the latter: 18 caught of 113 attempts faced.

The feed does not say which pitch she went on. A steal is its own play, filed
*ahead* of the plate appearance it interrupted, carrying an empty pitch string
and a 0-0 count; that count is the start of the at-bat, not the count she ran
on. 130 of the 133 have an empty pitch string. The remaining 3 are written into
a plate-appearance narrative ("struck out; she stole second") and name no pitch
either. Nothing in the pitch log mentions a steal.

The pitcher's hold is therefore a third contributor the game does not model at
all, and the 3 pickoffs are the only trace of it.

## 2. An opportunity

*(reconstructed)*

An opportunity is a plate appearance that began with her on base and the next
base open. The base state must be read from the first play of the plate
appearance, *before* the steal the feed files ahead of it. Reading the
plate-appearance row itself shows the runner already advanced whenever she
went, which deletes the very opportunity she used — and deletes it hardest for
the catchers who get run on most, inflating exactly the rates being compared.
An earlier version of this work counted that way and reported a −0.66
correlation between caught-stealing rate and attempt rate as deterrence. It was
an artefact. See section 5 for what the corrected count gives.

A pinch runner takes the base between plate appearances and the substitution
row still names the player she replaced, so the runner is read from the steal
row when there is one and from the plate appearance otherwise.

Counts: stealing second, 107 attempts in 697 opportunities across 59 runners;
stealing third, 25 attempts in 586 opportunities across 58 runners. Seven
attempts ended their half-inning on a 2-out caught stealing, so the plate
appearance never completed and has no pitch count. All seven are failures,
which matters wherever success is split by pitch count.

## 3. Two ratings

Chance (attempts per opportunity) and success (safe given an attempt) are
nearly independent: correlation about +0.19, rank correlation +0.06, so success
explains about 4% of the variance in chance rate. Represent the runner as the
pair (success, chance), with no cross term.

Real standard deviations, method of moments, leftover after the binomial term:

| quantity | subjects | rate | real SD | null at 95th pct | p |
|---|---|---|---|---|---|
| success, given an attempt | 12 runners, 78 attempts | 0.859 | 0.136 | 0.106 | 0.011 |
| chance, stealing 2nd, 15+ opportunities | 17 runners, 356 opp | 0.135 | 0.112 | 0.055 | <0.001 |
| chance, stealing 3rd, 15+ opportunities | 17 runners, 317 opp | 0.041 | 0.071 | 0.034 | <0.001 |
| catcher caught-stealing | 7 catchers, 131 attempts | 0.137 | 0.083 | 0.070 | 0.023 |

The eight busiest runners have 48% of second-base attempts on 19% of the
opportunities, and 64% of third-base attempts on 14% of the opportunities.
Counts pile up on whoever plays; the rate is what speed would move.

Catcher: Benites caught 8/21 = 0.381, the other six 10/110 = 0.091. With her
removed the remaining real SD is 0.000. Her 0.381 is a floor either way — a
good arm is only tested by runners willing to go.

Leguizamon and Studer have the same shrunk chance, built from the same 13
second-base opportunities and the same 4 attempts, and opposite outcomes (2/4
against 4/4). Low success means the attempts did not work. It does not separate
"she chose bad pitches" from "she was thrown out on ordinary ones."

## 4. Bins

Cuts were chosen where a further bin was unstable. They are not a frozen name
list in code; `steals.chance_bins` derives them every run.

**Chance.** Runners with at least 10 opportunities on second. Shrunk chance at
least 0.19 is `attempt_goes`; the rest are `attempt_league`. Two bins. A third,
higher bin was +2.4 SE and unstable.

`attempt_goes` (11): Lexi Hastings, Denae Benites, Ashton Lansdell, Amira
Hondras, Denver Bryant, Claire O'Sullivan, London Studer, Joely Leguizamon,
Suzuka Yamamoto, Ayuri Shimano, Raine Padgham.

The cut is not identified to two digits. No runner sits between 0.174 and
0.218, so anything in roughly [0.175, 0.218] produces the same eleven names.
Maximising the separation between groups does not locate a boundary either: the
contrast grows monotonically as the cut rises while the significance falls, so
the criterion trades sample size against contrast and never settles.

How wrong the labels are, from the beta posterior rather than a normal
approximation: ten of the 35 runners have between a one-in-four and a
three-in-four chance of belonging on the other side of the cut, and summing
those probabilities, **about 5 of the 35 are on the wrong side**. That figure is
stable across the whole valid range for the cut (5.40 at 0.17, 5.06 at 0.19,
5.07 at 0.22). Median posterior SD of chance is 0.067 and 15 runners lie within
one of it of the cut; the lost original reported 0.074 and 14, a difference in
the posterior-SD formula rather than in the data. Prefer the expected-
misclassification figure: it does not depend on that choice.

**Success.** Runners with at least 4 attempts. Shrunk success under 0.78 is
`success_low`; everyone else, including runners with fewer than 4 attempts, is
`success_league`. A runner with one or two attempts is not `success_low` even
if that raw rate would shrink under 0.78. A third success cut was +1.3 SE.
Median posterior SD of success is 0.081.

`success_low` is three names. Pooled raw: 8/16 = 0.500 against 101/113 = 0.894
for `success_league`.

| runner | safe / attempts | shrunk success |
|---|---|---|
| Amira Hondras | 4/7 | 0.711 |
| Joely Leguizamon | 2/5 | 0.659 |
| Suzuka Yamamoto | 2/4 | 0.724 |

Two runners fall just outside on near-identical evidence: Samaria Benitez is
0/2 and shrinks to 0.656, below Leguizamon, but stays `success_league` on the
4-attempt rule; Alexia Jorge lands at 0.779. The `success_low` list is a
function of attempt volume as much as of failure.

**Catcher, on success.** Benites against everyone else. That split is the one in
section 3.

## 5. Ghost count, and the zero that was not a zero

The prior sample size, the ghost count, is

    m = p (1 - p) / τ²

where τ² is the method-of-moments leftover: the weighted variance of the rates
minus the binomial term p(1 − p). It is in units of opportunities, because the
precision of her own record is n/p(1−p) and the precision of the league prior is
1/τ², so the two carry equal weight at n = m.

At the runner level, chance on second has τ = 0.122 at p = 0.148, so **m ≈ 8.5
opportunities**. Success has τ = 0.136 at p = 0.869, so **m ≈ 6.2 attempts**.
Thirty opportunities keep about three quarters of their own weight, and
Leblanc's 0/32 shrinks to about 0.03 rather than to the league. Those
runner-level values were not the ghost counts used on the grids.

On the attempt grid the margin was base × `attempt_goes`/`attempt_league`, with
the catcher pooled. The weighted mean squared gap from that margin was

    V_obs = Σ n (p − μ)² / Σ n = 0.203 / 1029 = 0.00020

Treating each margin as known, the binomial benchmark is

    V_chance = Σ μ(1 − μ) / Σ n = 0.803 / 1029 = 0.00078

The leftover was negative and was floored at 0, which is an infinite ghost
count: replace every cell with the margin. That comparison squares the gaps, so
a catcher who is lower in every cell looks the same as four gaps of mixed sign.
The five-point gaps are inside the noise of their own cells. On second,
`attempt_goes`, 0.306 against 0.371 is −0.066 on a standard error of 0.088
(0.75 SE). On third, `attempt_goes`, 0.071 against 0.128 is −0.056 on 0.060
(0.94 SE).

Because the margin was computed from the same two cells, the null expectation
per stratum is one copy of μ(1 − μ), not two:

    V_chance^est = 0.401 / 1029 = 0.00039

Observed 0.00020 is still below that, so the floor at zero survives the
correction. The floor is "not more spread than coin flips." It is not a
measurement that the Benites gap is exactly zero.

Asking the signed question — one odds ratio, the same in every stratum — is the
Mantel–Haenszel estimator:

    OR = Σ (a d / N) / Σ (b c / N) = 0.73,  95% 0.42 to 1.29,  −1.08 SE

The binomial logit with one intercept per stratum and one Benites coefficient,

    logit p = α_s + β · 1{Benites}

fits β = −0.308, SE 0.286, −1.08 SE, odds ratio 0.73. The same direction as the
old −0.66 correlation, on the corrected opportunity count, and too small to
call established. Replacing her attempt rate with the margin treats that as
exactly zero.

## 6. The grids

Runners with at least 10 opportunities on second, catcher known. 18
opportunities (3 attempts) had no catcher match and were dropped: 1,265
opportunities with a catcher matched, 1,029 of them to a rated runner. Two
team-games had two catchers and no innings column, so the first fielding line
was kept.

Attempt rate, raw:

| base | runner | Benites | else | margin |
|---|---|---|---|---|
| 2nd | `attempt_goes` | 11/36 = 0.306 | 49/132 = 0.371 | 60/168 = 0.357 |
| 2nd | `attempt_league` | 6/97 = 0.062 | 19/304 = 0.062 | 25/401 = 0.062 |
| 3rd | `attempt_goes` | 2/28 = 0.071 | 12/94 = 0.128 | 14/122 = 0.115 |
| 3rd | `attempt_league` | 0/74 = 0.000 | 4/264 = 0.015 | 4/338 = 0.012 |

Success, safe given the attempt. Base was pooled because the cell variance did
not clear the binomial term — second converts 0.841 (107) against third 0.846
(26), and a runner on third makes no difference (0.838 on 37 against 0.844 on
96, −0.08 SE), so one rate covers every attempt. The catcher was kept because
the head-to-head in section 3 had already established Benites. Do not shrink
these cells toward the league a second time: the runner bins were already
shrunk when the names were assigned, and a second shrink lifts the low bin
toward about 0.85.

| catcher | runner | safe / attempts | rate |
|---|---|---|---|
| Benites | `success_league` | 10/15 | 0.667 |
| Benites | `success_low` | 3/6 | 0.500 |
| else | `success_league` | 91/98 | 0.929 |
| else | `success_low` | 5/10 | 0.500 |

Total 109/129 = 0.845, which includes the seven 2-out caught stealings that
ended their half-innings. The both-marks cells are too small to see an extra
penalty.

## 7. San Francisco

*(reconstructed)*

Second-base attempt rate by team:

| team | opportunities | attempts | rate | success |
|---|---|---|---|---|
| New York Heights | 157 | 35 | 0.223 | 0.886 |
| Boston Hunters | 134 | 29 | 0.216 | 0.862 |
| Los Angeles Queens | 193 | 31 | 0.161 | 0.806 |
| San Francisco Firebells | 213 | 12 | **0.056** | 0.750 |

San Francisco is a quarter of the league's rate and is not safer when they do
run, so it is not caution paying off. This is a fact about a manager, not a
player, and the between-team gap stays off the runner card.

It does contaminate the chance rating, and that is not solved. Mean chance
rating by bench runs 0.092 (SFF) to 0.202 (BOS), a range that straddles the
0.19 cut: SFF supplies 1 `attempt_goes` runner out of 10 rated, BOS 4 out of 7.
Rating each runner against her own bench instead of the league moves 3 of the
35 across the line — Alexia Jorge and Jua Park up, Raine Padgham down — all
three already near the cut, and fewer than the ~5 the sample size misplaces
anyway.

Correcting for it would be wrong regardless. SFF's runners do look slightly
slow on plays with no stealing in them, taking an extra base on a hit 19% of
the time against 25% for the rest of the league, but that gap is far too small
to explain the attempt-rate deficit, and a manager with slow runners *ought* to
run less. His caution is a response to his roster, not an error laid on top of
it, so there is no clean way to subtract one and keep the other.

## 8. What does not move the attempt

*(reconstructed)*

Attempt rate below versus above the median of each quantity, within base state
AND out count, so only the named quantity varies:

| quantity | low | high | difference |
|---|---|---|---|
| break-even | 48/319 = 0.150 | 37/309 = 0.120 | +0.031 (+1.13 SE) |
| gain if safe | 48/341 = 0.141 | 37/287 = 0.129 | +0.012 (+0.43 SE) |
| loss if caught | 46/328 = 0.140 | 39/300 = 0.130 | +0.010 (+0.38 SE) |
| \|score margin\| | 44/326 = 0.135 | 41/302 = 0.136 | −0.001 (−0.03 SE) |
| inning | 49/393 = 0.125 | 36/235 = 0.153 | −0.029 (−0.99 SE) |

Nothing clears its own noise. Across the twelve base-out cells the correlation
between break-even and attempt rate is +0.06 on win probability and +0.12 on
run expectancy. Dropping the three first-and-third cells — where the defence
concedes the base and the rate is high for reasons that have nothing to do with
the stake — raises it to +0.53 on nine points, about 1.4 SE: suggestive that
managers run *more* where the steal is worse, not established.

Split by base state alone this test appeared to find a strong effect. It was the
out count doing the work, and it reversed once the outs were held fixed.

## 9. A d100 laid on the margins, and what run expectancy says about it

Break-evens from the Markov run-expectancy table (`markov.run_expectancy`).
Gain is the change in run expectancy if she is safe; loss is the change if she
is out, including the extra out.

| situation | 0 out | 1 out | 2 out |
|---|---|---|---|
| 2nd, runner on 1st only | 82% | 93% | 88% |
| 2nd, runners on 1st and 3rd | 81% | 83% | 92% |
| 3rd, runner on 2nd only | 68% | 66% | 88% |
| 3rd, runners on 1st and 2nd | 72% | 81% | 88% |

In runs, stealing second with a runner on first gains +0.23 at nobody out and
+0.06 at one out, against losses of −1.07 and −0.74. The loss dwarfs the gain
everywhere, which is why the break-evens sit so high. The best steal on the
board is third with only a runner on second and one out, needing 66%.

Against those lines, on the section 6 rates:

- `success_low`, 0.50, is under every line.
- `success_league` against Benites, 0.667, is under every line except stealing
  third with only a runner on second and 1 out, where the line is 66% and the
  edge is +0.01 runs. The rate is 10/15, so that one point is not a stable yes.
- `success_league` against anyone else, 0.929, is over every line except
  stealing second with only a runner on first and 1 out, where the line is 93%
  and the edge is 0.000 runs.

The standing run-expectancy rule on these rates: green-light a
`success_league` runner against an ordinary catcher, and decline the other two
matchups. The two cells on the line are ties.

Let q be the no-attempt share and p the success rate on an attempt face. The
value of green-lighting the roll, against declining it, is

    (1 − q) · [ p · gain − (1 − p) · loss ]

The no-attempt faces scale that value. They do not change its sign. The sign is
whether p beats the break-even loss / (gain + loss). An `attempt_goes` runner
and an `attempt_league` runner with the same p get the same answer; the
`attempt_goes` runner collects it on more faces.

**The face draft below could not be recomputed and is restored from a reading of
the lost original. Verify before use.** It was drafted from the pooled attempt
margins in section 6 and the four success rates. It gives Benites fewer safe
faces. It does not give her fewer attempt faces — that is the full replacement
of her attempt rate which section 5 refused to call a finding.

| situation | no attempt | `success_low` | `success_league`, Benites | `success_league`, else |
|---|---|---|---|---|
| 2nd, `attempt_goes` | 64 | 18 safe, 18 out | 24 safe, 12 out | 33 safe, 3 out |
| 2nd, `attempt_league` | 94 | 3 safe, 3 out | 4 safe, 2 out | 5 safe, 1 coin flip |
| 3rd, `attempt_goes` | 88 | 6 safe, 6 out | 8 safe, 4 out | 11 safe, 1 out |
| 3rd, `attempt_league` | 99 | 1 face, then a coin flip | 1 safe | 1 safe |

Some of those counts are not the rate. On third, `attempt_league`, the single
attempt face is safe for every `success_league` runner, including against
Benites, which is 1.00 rather than 0.667. The 6-and-0 face count and that
single safe face each move a cell off the standing rule above.

## 10. Alternative Formulation

Section 9 simulates base stealing from the manager's perspective: the manager
green-lights a runner, and the runner looks for a good opportunity, which
arrives at q = 0.182 per live pitch for an `attempt_goes` runner stealing
second and q = 0.040 per live pitch for third. On a good opportunity a
`success_league` runner is safe about 93% of the time against an ordinary
catcher.

A live pitch is a ball, a called strike or a swinging strike. A runner cannot go
on a foul or a hit batter, because the ball is dead and she is sent back, nor on
the pitch the batter puts in play, because the plate appearance is over. Of the
740 chances to steal second with a full pitch string, 378 fouls and 34 hit
batters come out, and 119 plate appearances turn out to have offered no live
pitch at all. The live count tops out at 6, since three balls and two strikes is
the most that can be taken before a pitch ends the at-bat.

Earlier drafts of this section quoted q = 0.041 for second and 0.010 for third.
Those were counted over every pitch AND pooled over every runner, so they
understated an `attempt_goes` runner's hazard by a factor of about four. The
ladder: over every pitch, pooled, 0.041 and 0.010; over live pitches, pooled,
0.063 and 0.016; over live pitches for an `attempt_goes` runner, 0.182 and
0.040. (`steal_pitches.py`)

Because q = 0.182 means a green-lit runner finds an opportunity in nearly any
plate appearance, the manager's decision is not between attempt and no attempt.
It is between potential attempt (green light) and no attempt (red light). Under
run expectancy such a manager should always green-light a `success_league`
runner except with one out and only a runner on first, because the decision is
filtered through a simulated runner with the judgement to wait. That makes it a
non-decision and not an interesting game mechanic.

An alternative is to let the player affect the simulated runner's decision. The
runner faces an optimal-stopping problem: find the best opportunity knowing
there are a limited number of pitches to steal on. The data is CONSISTENT with
runners identifying good opportunities but does not establish it — the rising
attempt rate by live-pitch count is equally well explained by exposure, and the
feed never records which pitch she went on. The extreme is a runner who always
goes on the first opportunity, which gives the third option: red light, green
light, or **must attempt**.

No estimate of the must-attempt success rate has been made, and none is
available. Writing μ for it:

    μ = q · E[S | she went] + (1 − q) · E[S | she stayed]

Every term is known except the last, and that one is unknowable by
construction. Bounding it by [0, E[S | went]] leaves μ in **[0.05, 0.84]** for
second and [0.01, 0.87] for third — the whole range. Recovering it needs
something that shifts whether she goes without shifting whether she would be
safe, and section 8 establishes there is no such thing here.

It is also a counterfactual, not merely an unmeasured quantity. All 133
attempts on record are ones somebody elected to make; the 3 pickoffs are the
closest the feed comes to a steal nobody chose. There is no forced attempt to
average, at any sample size.

What can be tested is the gradient μ sits at the bottom of. If she goes on the
best pitch available, then wherever she goes more often she is reaching further
down the pitch-quality distribution and success should FALL. It does not:

| test | spread | result |
|---|---|---|
| by base state | hazard 0.007 to 0.084, 11× | weighted corr +0.19; pooled high−low −0.026 (−0.33 SE) |
| by runner, stealing 2nd | attempt rate 0.158 to 0.571 | weighted corr +0.01 |
| by runner, either base | attempt rate 0.094 to 0.410 | weighted corr +0.05 |
| by live-pitch count | within the first 2 live pitches vs later, 0 and 1 out only | 0.893 (28) against 0.870 (46), +0.30 SE |

Nothing is negative. Three cautions against reading that as settled. The
cross-state hazards may be about how attractive the situation is rather than how
picky she is — first-and-third runs eight times first-and-second partly because
the catcher risks the runner on third. The cross-runner comparison is confounded
the other way: restoring the runners who rarely go, the rare ones convert 74%
and the frequent ones 84%, which is speed, and a real penalty could hide
underneath it. And the live-pitch test could not have seen a penalty smaller
than about 15 points.

So a must-attempt penalty would be a design choice, in the same way the gassed
column is: reasonable, directionally defensible, and not a measurement. It
should be labelled that way if it ships.

## 11. Undecided

- Whether the attempt die uses the pooled margins or the one-shift rates in
  section 6. The drafted faces use the margins.
- Whether chance is its own roll, a cue only the solo opponent uses, or glued
  onto the success die. The drafted d100 is its own roll. The current rulebook
  is a d12 that fires only because the manager declared.
- Which side of 0.19 the 14 runners within one posterior SD of the cut land on,
  and whether any SFF name is moved for the team rate.
- The both-marks cell (`success_low` runner, Benites) is a handful of attempts.
  The drafted faces multiply the two penalties. That product is not estimated.
- Win probability moves the break-even with the inning and the score, from about
  0.66 to 0.93. The section 9 rule is run expectancy only.
- Whether must-attempt ships with a penalty, and if so, labelled as invented.
