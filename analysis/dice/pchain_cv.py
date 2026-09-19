"""Pitcher-ordered chain (K | rest; HBP | rest; BB | contact; then the batter chain's
contact splits) vs the four-step tree, pitchers only. Nested 20 outer x 5 inner."""
import numpy as np
import pandas as pd
_here = __file__
__file__ = _here.replace("pchain_cv.py", "chain_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("\ngids = sorted(")])
__file__ = _here
NO_K = ("BB", "HBP") + CON
BBCON = ("BB",) + CON
PCHAIN = [(PA_, [("K",), NO_K]), (NO_K, [("HBP",), BBCON]), (BBCON, [("BB",), CON])] + CHAIN[3:]
PNAMES = ["K | rest", "HBP | rest", "BB | contact"] + CHAIN_NAMES[3:]
STRUCT = {"tree": TREE, "chain": PCHAIN}
HRS = {"tree": HR_STEP["4-step"], "chain": next(i for i, st in enumerate(PCHAIN) if ("HR",) in st[1])}
gids = sorted(pa["game_id"].unique())
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)
side = "P"
folds = folds_for(gids, side, REPEATS, np.random.default_rng(SEED))
print("pitcher chain best k (usual 20 splits):", dict(zip(PNAMES, [f(k) for k in tune("chain", folds)])), flush=True)
orng = np.random.default_rng(SEED + 11)
err = {m: np.zeros(len(pa)) for m in STRUCT}
chosen = {m: [] for m in STRUCT}
for r in range(OUTER):
    half_of = dict(zip(gids, orng.permutation(np.arange(len(gids)) % 2)))
    half = pa["game_id"].map(half_of).to_numpy()
    for fold in (0, 1):
        inner = folds_for([gg for gg in gids if half_of[gg] != fold], side, INNER, orng)
        outer_rec = record(pa[half != fold], side)
        test = np.flatnonzero(half == fold)
        pos = pos_of[side][pa.loc[test, side]].to_numpy()
        for m in STRUCT:
            ks = tune(m, inner)
            chosen[m].append(ks)
            C, T = outer_rec[m]
            err[m][test] += (w[y[test]] - (card(C, T, ks, STRUCT[m]) @ w)[pos]) ** 2
    print(f"  outer {r + 1}/{OUTER}", flush=True)
for m, nm in (("tree", TREE_NAMES), ("chain", PNAMES)):
    a = np.log2(np.clip(np.array(chosen[m]), 1, 4096))
    print(f"pitchers {m}: tuned k median [middle half]: " + "; ".join(
        f"{x} {f(2 ** md)} [{f(2 ** l_)}-{f(2 ** h_)}]" for x, md, l_, h_ in
        zip(nm, np.median(a, axis=0), np.percentile(a, 25, axis=0), np.percentile(a, 75, axis=0))))
d = (err["chain"] - err["tree"]) / OUTER
bt = (Wb @ np.bincount(g, weights=d, minlength=nG)) / (Wb @ cnt)
print(f"pitchers: pitcher-ordered chain minus tree {1e6 * d.mean():+.0f} x1e-6 per PA, SE {1e6 * bt.std():.0f}  (negative = chain better)")
