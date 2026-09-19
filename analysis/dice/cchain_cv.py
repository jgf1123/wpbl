"""Correlation-informed chains: contact splits into not-out (HR+1B+2B) | fielded (ROE+out),
then HR | in-park hits, 2B | 1B, ROE | out.  Batters: vs the batter chain.  Pitchers (K first):
vs the tree and the pitcher-ordered chain.  Nested 20 outer x 5 inner."""
import numpy as np
import pandas as pd
_here = __file__
__file__ = _here.replace("cchain_cv.py", "chain_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("\ngids = sorted(")])
__file__ = _here
NOTOUT = ("HR", "1B", "2B")
CONTACT_C = [(CON, [NOTOUT, FIELDED]), (NOTOUT, [("HR",), HITS2]), (HITS2, [("2B",), ("1B",)]), (FIELDED, [("ROE",), ("OUT",)])]
CCHAIN = CHAIN[:3] + CONTACT_C
NO_K = ("BB", "HBP") + CON
BBCON = ("BB",) + CON
PHEAD = [(PA_, [("K",), NO_K]), (NO_K, [("HBP",), BBCON]), (BBCON, [("BB",), CON])]
PCHAIN = PHEAD + CHAIN[3:]
PCCHAIN = PHEAD + CONTACT_C
NAMES = {"chain": CHAIN_NAMES, "cchain": CHAIN_NAMES[:3] + ["not-out | fielded", "HR | in-park hits", "2B | 1B", "ROE | out"],
         "tree": TREE_NAMES, "pchain": ["K | rest", "HBP | rest", "BB | contact"] + CHAIN_NAMES[3:],
         "pcchain": ["K | rest", "HBP | rest", "BB | contact", "not-out | fielded", "HR | in-park hits", "2B | 1B", "ROE | out"]}
PLAN = {"B": {"chain": CHAIN, "cchain": CCHAIN}, "P": {"tree": TREE, "pchain": PCHAIN, "pcchain": PCCHAIN}}
gids = sorted(pa["game_id"].unique())
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)
for side, plan in PLAN.items():
    STRUCT = plan
    HRS = {m: next(i for i, st in enumerate(s) if ("HR",) in st[1]) for m, s in plan.items()}
    label = "batters" if side == "B" else "pitchers"
    std = folds_for(gids, side, REPEATS, np.random.default_rng(SEED))
    for m in plan:
        if m in ("cchain", "pcchain"):
            print(f"{label} {m} best k (usual 20 splits): " + dict(zip(NAMES[m], [f(k) for k in tune(m, std)])).__repr__(), flush=True)
    orng = np.random.default_rng(SEED + 13)
    err = {m: np.zeros(len(pa)) for m in plan}
    chosen = {m: [] for m in plan}
    for r in range(OUTER):
        half_of = dict(zip(gids, orng.permutation(np.arange(len(gids)) % 2)))
        half = pa["game_id"].map(half_of).to_numpy()
        for fold in (0, 1):
            inner = folds_for([gg for gg in gids if half_of[gg] != fold], side, INNER, orng)
            outer_rec = record(pa[half != fold], side)
            test = np.flatnonzero(half == fold)
            pos = pos_of[side][pa.loc[test, side]].to_numpy()
            for m in plan:
                ks = tune(m, inner)
                chosen[m].append(ks)
                C, T = outer_rec[m]
                err[m][test] += (w[y[test]] - (card(C, T, ks, plan[m]) @ w)[pos]) ** 2
        print(f"  {side}: outer {r + 1}/{OUTER}", flush=True)
    for m in plan:
        a = np.log2(np.clip(np.array(chosen[m]), 1, 4096))
        print(f"{label} {m}: tuned k median [middle half]: " + "; ".join(
            f"{x} {f(2 ** md)} [{f(2 ** l_)}-{f(2 ** h_)}]" for x, md, l_, h_ in
            zip(NAMES[m], np.median(a, axis=0), np.percentile(a, 25, axis=0), np.percentile(a, 75, axis=0))))
    ms = list(plan)
    for i in range(len(ms)):
        for j in range(i + 1, len(ms)):
            d = (err[ms[j]] - err[ms[i]]) / OUTER
            bt = (Wb @ np.bincount(g, weights=d, minlength=nG)) / (Wb @ cnt)
            print(f"{label}: {ms[j]} minus {ms[i]} {1e6 * d.mean():+.0f} x1e-6 per PA, SE {1e6 * bt.std():.0f}  (negative = {ms[j]} better)", flush=True)
