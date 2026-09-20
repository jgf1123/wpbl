# Dice-card analysis scripts

The experiments behind `dice_game_spec.md` sections 2-4, kept so any result can
be rerun rather than taken on trust. The cards themselves come from
`src/wpbl/dice.py` (`pixi run dice`); these scripts are the record of how its
choices were made.

Run from the repo root:

    pixi run python analysis/dice/<script>.py

- Results quoted here were run on 17-20 Sep. The training set grew from 36 to 37
  games on 20 Sep, so older numbers in this table may not reproduce; rerun rather
  than trust them. Numbers will keep moving as games are added.
- Many scripts load another script's code from this folder by file name, so
  don't rename them. Those dependencies are listed below.
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

## Which outcomes share a card line (section 2)

| Script | Question | Result |
|---|---|---|
| `merge_log5.py` | Does keeping 1B / ROE or BB / HBP apart improve the log5 matchup? (Now rebuilds 8 lines from the free-pass cards; the spec's result came from the 8-line module, commit d175b22.) | 1B / ROE apart: better by 2.4 SE; BB / HBP: no |
| `freepass_cv.py` <- `chain_cv.py` | Free pass: best k for three placements; nested vs 8 lines; log5 matchup | HR \| K+FP then K \| FP; ties the 8-line cards |
| `split_k.py` <- `freepass_cv.py` | k for each player's walk \| HBP split (log-likelihood and pitch counts); S2 k stability | batters 8, pitchers 16 |
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

## Players and other checks

| Script | Question |
|---|---|
| `combine_fullpos.py` | Combination rules x card sets (section 4) |
| `sluggers.py` | Where Benites's and Whitmore's HR come from; do rosters show availability? |
| `hr_quality.py` <- `cohort_cards2.py` | Sluggers' HR by pitcher tier; context-neutral raw vs card |
| `regulars.py` <- `trees_cv.py` | The regulars' (17+ games) most extreme lines and run effects. The list is computed, not fixed: 20 names on 36 games, 16 on 37. Card totals here come from the old 4-step tree, so they are not the blog's Table 3 |
| `edit_distance.py` | Pairwise name edit distances (feed spelling check) |
| `sharpness.py` <- `tto_c.py` | Which step's k is sharp (error curve around each best k), and what share of each rate's spread is real rather than luck. In-park steps are the sharpest; batter hits per ball in park is 14% real, the pitcher version 0% |
| `regress10.py` | Table 2 of the blog: the top 10 in one set of odd/even games, and the same 10 in their other set. Three selection methods compared; the post uses "rank in each set, read the other, both directions" |
| `cohort_who.py` | Whose comparison group a batter is in, and who is in hers, at the ordinary steps and at the home-run step (`--who=`) |
| `log5_hr.py` | Whether the HR gap between pitcher tiers beats noise, and how far flat log5 moves a batter's HR chance across pitcher cards |
| `post_numbers.py` | Player numbers quoted in the blog draft, from the current cards. Calls `dice.build` directly, so it must pass `dice.SLUGGERS` for batters |
| `post_facts.py` | The blog's non-card numbers: season totals, the extreme cases, the sluggers, the signatures |
| `post_facts2.py` | Everyday starters, who counts as a regular, and whether a single scored the runner from 2nd |
| `post_facts3.py` | Season shape: regular season vs postseason, and which finished games are excluded |

## Figures for the blog

Written to `data/img/` (gitignored, so they are regenerated rather than committed).

| Script | Figure |
|---|---|
| `fig_k_curve.py` <- `k_curves.csv` | Figure 1: prediction error against k for all seven batter steps, the two in-play splits coloured. Reads the cached sweep, so run `sharpness.py` first when the data changes |
| `fig_card_tree.py` | Figure 2: the batter tree with one player's numbers, raw then card, each a share of the group to its left (`--who=`). Reads `data/dice/cards_batters.csv`, so run `pixi run dice` first |
