"""True-outcome trees for batters: step 1 splits (HR+K+HBP+BB) from in-park contact
(out+1B+2B+ROE). Variants differ inside the true-outcome branch. Compared with the
batter chain by nested cross-validation (20 outer x 5 inner). Slugger exception at the
step that splits HR off alone."""
import numpy as np
import pandas as pd
_here = __file__
__file__ = _here.replace("tto_c.py", "chain_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("\ngids = sorted(")])
__file__ = _here
TTO = ("K", "BB", "HBP", "HR")
INPARK_T = [(INPARK, [FIELDED, HITS2]), (FIELDED, [("ROE",), ("OUT",)]), (HITS2, [("2B",), ("1B",)])]
TOP = [(PA_, [TTO, INPARK])]
A1 = TOP + [(TTO, [("K",), ("BB", "HBP", "HR")]), (("BB", "HBP", "HR"), [("BB",), ("HBP", "HR")]),
            (("HBP", "HR"), [("HR",), ("HBP",)])] + INPARK_T
A2 = TOP + [(TTO, [("K", "BB"), ("HBP", "HR")]), (("K", "BB"), [("K",), ("BB",)]),
            (("HBP", "HR"), [("HR",), ("HBP",)])] + INPARK_T
B_ = TOP + [(TTO, [("HBP",), ("K", "BB", "HR")]), (("K", "BB", "HR"), [("K",), ("BB", "HR")]),
            (("BB", "HR"), [("HR",), ("BB",)])] + INPARK_T
C_ = TOP + [(TTO, [("HBP",), ("K", "BB", "HR")]), (("K", "BB", "HR"), [("HR",), ("K", "BB")]), (("K", "BB"), [("K",), ("BB",)]), (INPARK, [("1B",), ("2B", "ROE", "OUT")]), (("2B", "ROE", "OUT"), [("OUT",), ("2B", "ROE")]), (("2B", "ROE"), [("ROE",), ("2B",)])]
PLAN = {"chain": CHAIN, "C": C_}
sname = lambda st: " | ".join("+".join(c) for c in st[1])
STRUCT = PLAN
HRS = {m: next(i for i, st in enumerate(s) if ("HR",) in st[1]) for m, s in PLAN.items()}
side = "B"
gids = sorted(pa["game_id"].unique())
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)

# ---- best k on the usual 20 splits, and cards ----
std = folds_for(gids, side, REPEATS, np.random.default_rng(SEED))
best = {}
for m, s in PLAN.items():
    best[m] = tune(m, std)
    print(f"{m} best k: " + "; ".join(f"{sname(st)} {f(k)}" for st, k in zip(s, best[m])), flush=True)
full = record(pa, side)
X = counts(pa, side)
n = X.sum(axis=1)
L = X.sum(axis=0) / X.sum()
w_avg = float(L @ w)
names = [name.get(i, i) for i in people[side]]
reg = n >= 25
print("\nruns above average per PA x1000 (raw, then each structure); spread = SD among batters with 25+ PA")
cards = {m: card(*full[m], best[m], PLAN[m]) for m in PLAN}
val = lambda M: (M - L) @ (w - w_avg)
print(f"  spread: raw {1000 * val(X / np.maximum(n[:, None], 1))[reg].std(ddof=1):.0f}, " +
      ", ".join(f"{m} {1000 * val(cards[m])[reg].std(ddof=1):.0f}" for m in PLAN) +
      "; total HR: " + ", ".join(f"{m} {float((cards[m][:, IX['HR']] * n).sum()):.1f}" for m in PLAN) + f" (actual {int(X[:, IX['HR']].sum())})")
for nm in ("Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Alexia Jorge", "Andreanne Leblanc", "Skylar Kaplan", "Natsuki Yonetani"):
    i = names.index(nm)
    raw = X[i] / n[i]
    print(f"  {nm:18s} raw {1000 * val(raw):4.0f} | " + " | ".join(f"{m} {1000 * val(cards[m][i]):4.0f}" for m in PLAN) +
          "   HR% " + "/".join(f"{100 * v:.1f}" for v in [raw[IX['HR']]] + [cards[m][i, IX['HR']] for m in PLAN]) +
          "  K% " + "/".join(f"{100 * v:.1f}" for v in [raw[IX['K']]] + [cards[m][i, IX['K']] for m in PLAN]) +
          "  HBP% " + "/".join(f"{100 * v:.1f}" for v in [raw[IX['HBP']]] + [cards[m][i, IX['HBP']] for m in PLAN]), flush=True)

# ---- nested ----
orng = np.random.default_rng(SEED + 19)
err = {m: np.zeros(len(pa)) for m in PLAN}
chosen = {m: [] for m in PLAN}
for r in range(OUTER):
    half_of = dict(zip(gids, orng.permutation(np.arange(len(gids)) % 2)))
    half = pa["game_id"].map(half_of).to_numpy()
    for fold in (0, 1):
        inner = folds_for([gg for gg in gids if half_of[gg] != fold], side, INNER, orng)
        outer_rec = record(pa[half != fold], side)
        test = np.flatnonzero(half == fold)
        pos = pos_of[side][pa.loc[test, side]].to_numpy()
        for m in PLAN:
            ks = tune(m, inner)
            chosen[m].append(ks)
            C, T = outer_rec[m]
            err[m][test] += (w[y[test]] - (card(C, T, ks, PLAN[m]) @ w)[pos]) ** 2
    print(f"  outer {r + 1}/{OUTER}", flush=True)
print()
for m, s in PLAN.items():
    a = np.log2(np.clip(np.array(chosen[m]), 1, 4096))
    print(f"{m}: tuned k median [middle half]: " + "; ".join(
        f"{sname(st)} {f(2 ** md)} [{f(2 ** l_)}-{f(2 ** h_)}]" for st, md, l_, h_ in
        zip(s, np.median(a, axis=0), np.percentile(a, 25, axis=0), np.percentile(a, 75, axis=0))))
for m in ("C",):
    d = (err[m] - err["chain"]) / OUTER
    bt = (Wb @ np.bincount(g, weights=d, minlength=nG)) / (Wb @ cnt)
    print(f"{m} minus chain: {1e6 * d.mean():+.0f} x1e-6 per PA, SE {1e6 * bt.std():.0f}  (negative = {m} better)")
