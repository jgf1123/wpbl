# Dice-card analysis scripts

The experiments behind `dice_game_spec.md` sections 2-4, kept so any result can
be rerun rather than taken on trust. The cards themselves come from
`src/wpbl/dice.py` (`pixi run dice`); these scripts are the record of how its
choices were made.

Run from the repo root:

    pixi run python analysis/dice/<script>.py

- Results quoted here were run on 17-21 Sep. The training set grew from 36 to 37
  games on 20 Sep, so older numbers in this table may not reproduce; rerun rather
  than trust them. Numbers will keep moving as games are added.
- Many of the older scripts load another script's code from this folder by file
  name, so don't rename them. Those dependencies are listed below as `<-`. The
  scripts written from 20 Sep on import `wpbl.dice` instead and have no such
  dependency.
- **Eight scripts no longer run as written.** They expect a merged `FP` (free
  pass) line, which `wpbl.dice` dropped at v0.3.0 when walks and hit-by-pitches
  split back apart, so they raise `KeyError: 'FP'`: `mixture.py`,
  `mixture_per_line.py`, `mixture_eight.py`, `log5_fit.py`,
  `additive_vs_log5.py`, `hybrid_rules.py`, `quantize_cards.py` and
  `log5_hr.py`. Their results are quoted in the spec with that provenance.
  Porting them is not automatic: under eight lines they ask a slightly
  different question, which is the point the split was making.
- The nested cross-validation runs take several minutes each. Run them at
  below-normal priority, one at a time.

## Outcome lines (spec section 2)

| Script | Question | Result |
|---|---|---|
| `proposals.py` | Do B / F / FB / + reproduce outs with runners on? (Part A: PA-quartile targets, superseded) | 468 of 497 with F = force at 2nd |
| `force_split.py` | Fielder's choices and double plays with 2+ forced runners: which runner is out? | FC 18 at 2nd, 9 lead; DP batter + runner from 1st |
| `label_map.py` | How the feed's 15 play labels map onto card lines | Table in spec section 2 |
| `label_vs_line.py` <- `proposals.py` | Same label, different base-out result (ground balls, lineouts) | 176 ground-ball outs: 37 / 78 / 17 / 38 / 6 |
| `out_plus.py` <- `proposals.py` | Are some batters better or worse at advancing runners on an out (the + modifier)? Direct rate, the rate implied by each batter's out-type mix, and what a + is worth | no real spread either way; worth 0.1-0.2 runs a season |
| `out_flavors.py` <- `proposals.py` | League rates for the six flavors, family from the feed's label and only the + inferred. Writes `data/dice/out_flavors.csv` | B 72.7% / F 14.0% / FB 13.3%; F and FB share one + rate, pooled 10 of 13 |
| `out_quantize.py` <- `proposals.py` | Which die resolves the out flavors without costing runs | feeds the d12 assumption in spec section 8 |

## Which outcomes share a card line (section 2)

| Script | Question | Result |
|---|---|---|
| `merge_log5.py` | Does keeping 1B / ROE or BB / HBP apart improve the log5 matchup? (Now rebuilds 8 lines from the free-pass cards; the spec's result came from the 8-line module, commit d175b22.) | 1B / ROE apart: better by 2.4 SE. BB / HBP: no -- but the test is blind by construction, and `mixture_per_line.py` reversed it |
| `freepass_cv.py` <- `chain_cv.py` | Free pass: best k for three placements; nested vs 8 lines; log5 matchup | HR \| K+FP then K \| FP; ties the 8-line cards |
| `split_k.py` <- `freepass_cv.py` | k for each player's walk \| HBP split (log-likelihood and pitch counts); S2 k stability | batters 8, pitchers 16 -- superseded by `split_k_final.py` |
| `replayness.py` <- `freepass_cv.py` | How close to season lines: 8-line cards vs a league-wide free-pass split | league split erases batters' mixes |

## Targets and cohorts (section 3.2)

| Script | Question | Result |
|---|---|---|
| `recon.py` | League rates over all PAs vs qualifier pools (why the 15 Sep cards disagreed) | low-PA batters: K 16.5%, HR 0.4% |
| `followups.py` | ROE leave-one-out; HR leaders; rates by PA quartile; kept vs tryout pitchers | batter ROE has no real spread |
| `deciles.py` | Unqualified pitchers; sluggers' HR by halves; rates by PA decile | rates not linear in PA |
| `cohort_size.py` | Minimum cohort size (4k) per line | about 300 |
| `cohort_cards.py` | Sliding cohort ranked by PA share | rejected: sorts regulars by lineup spot |
| `cohort_cards2.py` | Ranked by starts share; slugger exception; per-line cards | basis of later scripts |
| `cohort_cv.py` <- `greedy_cv.py` | Cohort 150 / 300 / 600 (nested) | batters: 150 worse by 2.3 SE; pitchers insensitive |
| `cohort_grid.py` <- `greedy_cv.py` | The same test on a finer grid, 150 to 600 in eight steps | batters bottom out at 250; pitchers flat from 250 up. 250 chosen for both |
| `retune_k.py` <- `freepass_cv.py` | Best k per step for the shipped structures at a given cohort target (default 250) | 4 of 10 step k values moved when the target went to 250 |

## Choosing k (section 3.4)

| Script | Question | Result |
|---|---|---|
| `k_uncertainty.py` <- `cohort_cards2.py` | Method-of-moments k with bootstrap ranges | k = inf is one end of a wide range |
| `k_cv.py`, `k_best.py` <- `k_cv.py` | Per-line k by held-out runs, grid 0-inf; "smallest k within 2 SE" (not a user rule) | near-raw cards for tiny samples |
| `k_cv2.py`, `k_best2.py` <- `k_cv2.py` | Same on an octave grid; best k vs least smoothing within 1 SE | every best k finite |

## Structures (section 3.4, 3.6)

| Script | Question | Result |
|---|---|---|
| `tree_cv.py` <- `k_cv2.py` | 3-step tree; sluggers protected or not | |
| `tree_compare.py` <- `tree_cv.py` | Protected vs not, head to head | protected leans better (0.9 SE) |
| `tree4_cv.py` <- `k_cv2.py` | 4-step tree on a sqrt(2) grid; where Benites's drop comes from | hits per ball in play |
| `trees_cv.py` <- `k_cv2.py` | Setups a, b, 4-step; how sharp each step's k is | only the in-play step is sharp |
| `lines_cv.py` <- `trees_cv.py` | Per-line smoothing, outs a line, renormalized, vs tree (not nested) | looked 1.4 SE better |
| `hybrid_cv.py` <- `lines_cv.py` | Hybrid; first nested test of tree / per-line / hybrid | hybrid worse |
| `nested2.py` <- `lines_cv.py` | Per-line vs tree, nested 20 x 5 | tie (batters), tree (pitchers) |
| `chain_cv.py` <- `trees_cv.py` | Batter chain vs tree (nested) | tie; stabler k |
| `pchain_cv.py` <- `chain_cv.py` | Pitcher-ordered chain vs tree | tie |
| `cchain_cv.py` <- `chain_cv.py` | HR grouped with hits (batters); K-first variant (pitchers) | chain / tree better |
| `talent_corr.py` <- `trees_cv.py` | Noise-corrected correlations between lines | HR-Out -0.64; HR-1B not negative |
| `tto_cv.py` <- `chain_cv.py` | True outcomes first, branch orders A1, A2, B | all worse than chain |
| `tto_c.py` <- `chain_cv.py` | True outcomes first, increasing-k branches (current batter structure) | better than chain by 1.9 SE |
| `greedy_cv.py` <- `chain_cv.py` | Automatic "most reliable split first", fully nested | ties; different structure every half |

## Combining the two cards (section 4)

The long line of attack was log5 and its shortcuts; it ended when the mixture
turned out to beat all of them. Kept in order, because the dead ends are the
argument for what shipped.

| Script | Question | Result |
|---|---|---|
| `combine_fullpos.py` | Combination rules x card sets: additive, flat log5, two-level log5, averaging | three tie within 0.7 SE; averaging halves player differences |
| `log5_fit.py` | Is log5 the right rule at all, line by line, against league / batter / pitcher alone? | the best rule differs by line: log5 for K, the batter alone for HR / 1B / Out, the league for 2B, the pitcher for ROE |
| `additive_vs_log5.py` | How far B + P - L drifts from flat log5, reported in d100 cells | |
| `hybrid_rules.py` <- `log5_fit.py` | Rules that sum to 100% without renormalising, since a per-line best does not | the shift rules all give the offset back from Out |
| `quantize_cards.py` | Four rules for rounding a card to 100 cells, and what log5's sum-to-100 shortfall costs | superseded by `layout_round.py`, which rounds a block rather than a whole card |

The mixture -- the roll picks which card to read:

| Script | Question | Result |
|---|---|---|
| `mixture.py` | Does a mixture work as a combination rule? Plain cards and compensated cards (print B' so the mixture reproduces B exactly) | **chosen**: better than no mixing by 4.5 SE, and beats log5, additive and every zero-sum shift. Compensated cards are not printable |
| `mixture_per_line.py` | Line by line, what share should be read off the pitcher's card? Each line gets a league control, so the gap is what the pitcher's identity is worth | walks want the pitcher (0.70), hit-by-pitches the batter (0.20) |
| `mixture_eight.py` | The same with walks and HBP kept apart | the evidence that reversed the free-pass merge |
| `line_owner.py` | Who owns each line: real share of spread, k, and fitted weight, all per plate appearance so the two sides compare | 2B and ROE have no real spread on either side; sets the sort order |

Bins -- one weight per band of the d100, rather than one overall:

| Script | Question | Result |
|---|---|---|
| `bins.py` | How wide must a bin be, and what fills the rest of it? | a bin needs a filler line to absorb the slack, and its width must clear every player's total |
| `bin_alpha.py` | Fit the ten bin weights, given the cards | |
| `bin_nested.py` <- `bin_alpha.py` | Do ten fitted weights beat one, when the weights are held out too? | no -- a superset that cannot use its extra freedom |
| `bin_spread.py` | What each bin actually holds across every card, not just the average one | a bin that is one line on the average card is two or three on a real one |

The weight and the smoothing together -- they interact, because mixing is
itself shrinkage:

| Script | Question | Result |
|---|---|---|
| `alpha_sweep.py` | Sweep the weight under both metrics, for a card set built to be read alone and one built to be mixed | runs bottom near 0.15-0.20, log loss near 0.375-0.43, both curves flat |
| `alpha_cost.py` | What a weight other than the runs-optimal one costs, priced on both metrics with standard errors | turns the disagreement into a number |
| `fit_cards.py` | Alternating tuner: k on runs, the weight on log loss, until neither moves | **rejected.** Alternating two objectives descends on nothing; it drifted to a fixed point worse than its start on both scores. Kept as the record of why `joint_runs.py` uses one objective |
| `joint_runs.py` | k and the weight together on runs alone, by coordinate descent from six starts | one fixed point from every start; the shipped k |
| `k_given_mixing.py` | If a card will be mixed with the opponent's, what k should build it? | k falls: the mixing supplies the smoothing |
| `k_alpha_nested.py` | Does the joint fit survive nesting, against sequential tuning and against no mixing? | |
| `split_k_final.py` | The BB \| HBP k with both sides free on the full grid, on log loss | 2.83 on each side independently; the best shared value costs +0.000 |
| `band_two_level.py` <- `line_owner.py` | A round band plus a marked bonus group, vs one flat rate, for 2B and ROE | flat 5% and 2% chosen; the bonus group is worse at every size |

## The printed d100 table (section 4.1)

| Script | Question | Result |
|---|---|---|
| `layout_cells.py` | Lay the real cards into 35 pitcher and 58 batter cells: does a line vanish from a matchup, and how far does the realised weight drift? | |
| `layout_round.py` | Four rounding rules judged on runs, including what the home-run floor costs separately | nearest, then spend the difference where \|run error\| is smallest |
| `hr_floor_options.py` | Cards whose home-run line rounds to nothing: no floor, per card, per pair, or a shared cell split by the d12 | pitcher-only floor: 2% on league HR, and it closes every hole by itself |

## The engine and the league check (section 9.1)

`pixi run engine` (`src/wpbl/engine.py`) plays the printed game. These are the
diagnostics around it.

| Script | Question | Result |
|---|---|---|
| `running_plays.py` | Do wild pitches, passed balls and balks vary by pitcher or catcher for real? | no spread clears sampling noise; the line is a league band. A blocked pitch never enters the data, so the spread is censored, not absent |
| `running_k.py` | Sweeping k for the running-play rate, where k = inf IS the flat band | best k against the league 1024, beating the band by 0.48 SE; the usage cohort is worse than ignoring pitcher identity |
| `engine_transitions.py` | Where the engine's base-out transitions differ from the season's, each state judged against its own sampling noise | excess distance 0.019 after the steal-timing fix, from 0.059 before. **Found a bug run expectancy could not see** |

## Fatigue and pitcher state (section 7)

| Script | Question | Result |
|---|---|---|
| `fatigue.py` | Does a pitcher decline within an appearance, conditioning on survivors? And does workload carried in from previous days predict? | within an appearance, nothing: the pitch and times-through cuts disagree in sign at about 1 SE each. Across days, 25+ pitches in the prior three gives +0.050 against -0.025 rested, 1.69 SE |
| `fatigue_from_end.py` | The same question with appearances aligned on the REMOVAL, paired within one outing | **+0.078 (SE 0.035), 2.2 SE** in the inning before she was pulled, excluding the inning the removal happened in. Prints the pooled version too, with a warning: its buckets hold different appearances |
| `pitcher_state.py` | Do Deadball's and History Maker's in-game rules appear -- STRUGGLER, ACE, FRESH tiers? | none of them. HMB's tiers do not even apply: a starter's 7th inning of work has zero plate appearances in a seven-inning league |
| `roles.py` | Do relievers pitch at a higher ceiling, and burn faster? | ceiling yes, measured within the pitcher: 13 of 19 better in relief, mean -0.058 (1.7 SE). Burn untestable -- relievers rarely reach the three innings the paired test needs |

## Handedness (section 5)

| Script | Question | Result |
|---|---|---|
| `handedness.py` | Does a platoon adjustment, fitted on the build half and shrunk toward zero, predict held-out games better than none? Cards rebuilt per fold | **worse at every strength**: +75.8 (SE 25.5) on runs at quarter, +405.8 (SE 101.9) at full. The shrinkage curve rises monotonically from zero, which is the signature of noise |
| `handedness_re24.py` | The same question asked of RE24 -- one number per plate appearance instead of eight | outcome mix identical (-0.002, 0.07 SE); only situational timing differs (+0.035, 1.08 SE). Detectable effect is 0.7 SD of the batter population: no evidence, not no effect |

## Players and other checks

| Script | Question |
|---|---|
| `sluggers.py` | Where Benites's and Whitmore's HR come from; do rosters show availability? |
| `hr_quality.py` <- `cohort_cards2.py` | Sluggers' HR by pitcher tier; context-neutral raw vs card |
| `regulars.py` <- `trees_cv.py` | The regulars' (17+ games) most extreme lines and run effects. The list is computed, not fixed: 20 names on 36 games, 16 on 37. Card totals here come from the old 4-step tree, so they are not the blog's Table 3 |
| `edit_distance.py` | Pairwise name edit distances (feed spelling check) |
| `sharpness.py` <- `tto_c.py` | Which step's k is sharp (error curve around each best k), and what share of each rate's spread is real rather than luck. In-park steps are the sharpest; batter hits per ball in park is 14% real, the pitcher version 0% |
| `regress10.py` | Table 2 of the blog: the top 10 in one set of odd/even games, and the same 10 in their other set. Three selection methods compared; the post uses "rank in each set, read the other, both directions" |
| `cohort_who.py` | Whose comparison group a batter is in, and who is in hers, at the ordinary steps and at the home-run step (`--who=`) |
| `log5_hr.py` | Whether the HR gap between pitcher tiers beats noise, and how far flat log5 moves a batter's HR chance across pitcher cards |
| `post_numbers.py` | The player numbers in the published blog post, recomputed from the current cards -- so it shows how far the post has drifted, not what it says. Reads `dice.cards()`; it used to call `dice.build` by hand, which stopped working when the card became eight lines |
| `post_facts.py` | The blog's non-card numbers: season totals, the extreme cases, the sluggers, the signatures |
| `post_facts2.py` | Everyday starters, who counts as a regular, and whether a single scored the runner from 2nd |
| `post_facts3.py` | Season shape: regular season vs postseason, and which finished games are excluded |

## Figures for the blog

Written to `data/img/` (gitignored, so they are regenerated rather than
committed). **The blog post is already published**, and it shows the figures as
they were under the seven-line card. These scripts have moved on, so rerunning
them does not reproduce the published images -- they are here for the next post.

| Script | Figure |
|---|---|
| `fig_k_curve.py` <- `k_curves.csv` | Figure 1: prediction error against k for every batter step, the two in-play splits coloured. Reads the cached `k_curves.csv`, which is still a sweep of the **old seven-step tree** -- its legend names two steps (`1B \| 2B+ROE+out`, `out \| 2B+ROE`) that no longer exist. Refreshing it means porting `sharpness.py` to the five-step tree and sweeping at the mixing weight |
| `fig_card_tree.py` | Figure 2: the batter tree with one player's numbers, raw then card, each a share of the group to its left (`--who=`). Ported to the five-step tree: the root is now "not a double or an error", since those are league bands outside it. Reads `dice.cards()`, not the csv, which no longer carries percentages |
