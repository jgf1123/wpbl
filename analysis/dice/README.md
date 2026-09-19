# Dice-card analysis scripts

The experiments behind `dice_game_spec.md` sections 2-4, kept so any result can
be rerun rather than taken on trust. The cards themselves come from
`src/wpbl/dice.py` (`pixi run dice`); these scripts are the record of how its
choices were made.

Run from the repo root:

    pixi run python analysis/dice/<script>.py

- They are snapshots as run on 17-18 Sep (36 training games). Numbers will move
  as games are added.
- Many scripts load another script's code from this folder by file name, so
  don't rename them. Those dependencies are listed below.
- The nested cross-validation runs take several minutes each. Run them at
  below-normal priority, one at a time.

## Outcome lines (spec section 2)

| Script | Question | Result |
|---|---|---|
| `proposals.py` | Do B / F / FB / + reproduce outs with runners on? (Part A: PA-quartile targets, superseded) | 468 of 497 with F = force at 2nd |
| `force_split.py` | Fielder's choices and double plays with 2+ forced runners: which runner is out? | FC 18 at 2nd, 9 lead; DP batter + runner from 1st |

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
| `regulars.py` <- `trees_cv.py` | The 20 regulars' most extreme lines and run effects |
| `edit_distance.py` | Pairwise name edit distances (feed spelling check) |
