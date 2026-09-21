"""Cohort size on a finer grid: 150 / 200 / 250 / 300 / 350 / 400 / 500 / 600 PA (BF).

Same nested design as cohort_cv.py (k tuned inside each build half for each size,
scored on the held-out half, reported against 300), just more points. Worth doing
because tie groups enter whole: 250 and 350 pick a different cohort from 300 for
14 and 11 of the 46 qualified batters, so the grid is not degenerate.

Slow: eight sizes x 20 outer x 5 inner. Run it at below-normal priority."""
import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("cohort_grid.py", "greedy_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("# ---- the rule on all 36 games ----")])
__file__ = _here
SIZES = (150, 200, 250, 300, 350, 400, 500, 600)
TREE_P = SETUPS["4-step"]
OUTER, INNER = 20, 5
gids = sorted(pa["game_id"].unique())
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)
for SIDE, steps, label in (("B", STRUCT_C, "batters (structure C)"), ("P", TREE_P, "pitchers (tree)")):
    orng = np.random.default_rng(SEED + 29)
    err = {s: np.zeros(len(pa)) for s in SIZES}
    chosen = {s: [] for s in SIZES}
    for r in range(OUTER):
        half_of = dict(zip(gids, orng.permutation(np.arange(len(gids)) % 2)))
        half = pa["game_id"].map(half_of).to_numpy()
        inner_seed = int(orng.integers(1 << 30))
        for fold in (0, 1):
            build_games = [gg for gg in gids if half_of[gg] != fold]
            test = np.flatnonzero(half == fold)
            pos = pos_of[SIDE][pa.loc[test, SIDE]].to_numpy()
            for size in SIZES:
                COHORT_PA = size                          # read by cohorts() at call time
                inner = inner_folds(build_games, np.random.default_rng(inner_seed + fold))   # same games for every size
                ks = tune(steps, inner)
                chosen[size].append(ks)
                C, T = ct(base_record(pa[half != fold]), steps)
                err[size][test] += (w[y[test]] - (card(C, T, ks, steps) @ w)[pos]) ** 2
        print(f"  {SIDE}: outer {r + 1}/{OUTER}", flush=True)
    print(f"\n=== {label} ===")
    for size in SIZES:
        a = np.log2(np.clip(np.array(chosen[size]), 1, 4096))
        print(f"  cohort {size}: median tuned k " + ", ".join(f(2 ** v) for v in np.median(a, axis=0)))
    for size in [s for s in SIZES if s != 300]:
        d = (err[size] - err[300]) / OUTER
        bt = (Wb @ np.bincount(g, weights=d, minlength=nG)) / (Wb @ cnt)
        print(f"  cohort {size} minus 300: {1e6 * d.mean():+.0f} x1e-6 per PA, SE {1e6 * bt.std():.0f}  (negative = {size} better)", flush=True)
    COHORT_PA = 300
