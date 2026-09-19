"""Per-line smoothing with OUT as a line, then renormalised to 100%, vs the 4-step tree.

Each of the 8 lines: (own count + k_line * cohort rate) / (own PA + k_line); floor 1%;
divide by the row sum. k per line chosen on held-out games in runs (two coordinate
passes, sqrt(2) grid). Slugger exception on the HR line only (ASSUMPTION, 18 Sep)."""
import numpy as np
import pandas as pd

SRC = open(__file__.replace("lines_cv.py", "trees_cv.py"), encoding="utf-8").read()
SRC = SRC.replace('__file__.replace("trees_cv.py", "k_cv2.py")', repr(__file__.replace("lines_cv.py", "k_cv2.py")))
exec(SRC[:SRC.index("gids = sorted(")])
TREE = SETUPS["4-step"]
TREE_K = {"B": [32, 64, 45, 11], "P": [45, 256, 181, np.inf]}      # chosen 18 Sep


def line_targets(X, coh):
    base, excl, special = coh
    T = np.zeros_like(X)
    for i in range(len(X)):
        for j, l in enumerate(ALL):
            take = (special[i] if special[i] is not None else excl[i]) if l == "HR" else base[i]
            tot = X[take].sum(axis=0)
            T[i, j] = tot[j] / tot.sum() if tot.sum() > 0 else X[:, j].sum() / X.sum()
    return T


def line_card(X, T, ks):
    n = X.sum(axis=1, keepdims=True)
    k = np.array(ks)[None, :]
    c = np.where(np.isinf(k), T, (X + np.where(np.isinf(k), 0, k) * T) / np.maximum(n + np.where(np.isinf(k), 0, k), 1e-12))
    c = np.maximum(c, MIN_RATE)
    return c / c.sum(axis=1, keepdims=True)


gids = sorted(pa["game_id"].unique())
rng = np.random.default_rng(SEED)
splits = [pa["game_id"].map(dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))).to_numpy() for _ in range(REPEATS)]
cache = {}
for r, half in enumerate(splits):
    for fold in (0, 1):
        build = pa[half != fold]
        for side in ("B", "P"):
            X = counts(build, side)
            coh = all_cohorts(side, X)
            C = child_counts(X, TREE)
            cache[(r, fold, side)] = (X, line_targets(X, coh), C, targets(C, coh, HR_STEP["4-step"]))
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)
pos_of = {s: pd.Series(np.arange(len(people[s])), index=people[s]) for s in ("B", "P")}


def per_pa(side, method, ks_list):
    S = np.zeros((len(pa), len(ks_list)))
    for r, half in enumerate(splits):
        for fold in (0, 1):
            test = np.flatnonzero(half == fold)
            X, LT, C, T = cache[(r, fold, side)]
            pos = pos_of[side][pa.loc[test, side]].to_numpy()
            v = w[y[test]]
            for j, ks in enumerate(ks_list):
                cd = line_card(X, LT, ks) if method == "lines" else card(C, T, ks, TREE)
                S[test, j] += (v - (cd @ w)[pos]) ** 2
    return S / REPEATS


def boot(S):
    G = np.stack([np.bincount(g, weights=S[:, j], minlength=nG) for j in range(S.shape[1])], axis=1)
    return S.mean(axis=0), (Wb @ G) / (Wb @ cnt)[:, None]


full = {}
for side in ("B", "P"):
    X = counts(pa, side)
    coh = all_cohorts(side, X)
    C = child_counts(X, TREE)
    full[side] = (X, line_targets(X, coh), C, targets(C, coh, HR_STEP["4-step"]))


def summary(side, method, ks, who=None):
    X, LT, C, T = full[side]
    cd = line_card(X, LT, ks) if method == "lines" else card(C, T, ks, TREE)
    v = cd @ w
    n = X.sum(axis=1)
    names = [name.get(i, i) for i in people[side]]
    reg = n >= (25 if side == "B" else 40)
    out = {"spread": round(1000 * v[reg].std(ddof=1))}
    for nm in (who or (("Denae Benites", "Ashton Lansdell") if side == "B" else ("Jaida Lee",))):
        out[nm.split()[-1]] = round(1000 * v[names.index(nm)])
    return out, cd


best = {}
for side in ("B", "P"):
    fixed = [64.0] * len(ALL)
    for p in (1, 2):
        new, curves = [], {}
        for s in range(len(ALL)):
            pt, bt = boot(per_pa(side, "lines", [fixed[:s] + [k] + fixed[s + 1:] for k in KGRID]))
            curves[s] = (pt, bt)
            new.append(KGRID[int(np.argmin(pt))])
        if p == 1:
            pass1 = new
            fixed = new
    best[side] = new
    print(f"\n==================== per-line, {'BATTERS' if side == 'B' else 'PITCHERS'}: best k "
          f"{dict(zip(ALL, [f(k) for k in new]))}  (pass 2; pass-1 best {[f(k) for k in pass1]}) ====================")
    for s, line in enumerate(ALL):
        pt, bt = curves[s]
        b = int(np.argmin(pt))
        rows = []
        for j in range(max(0, b - 3), min(len(KGRID), b + 4)):
            loss, se = pt[j] - pt[b], (bt[:, j] - bt[:, b]).std()
            ks = list(new); ks[s] = KGRID[j]
            rows.append({"k": f(KGRID[j]), "loss x1e6": round(1e6 * loss), "SE": round(1e6 * se),
                         "loss/SE": round(loss / se, 1) if se > 0 else 0.0, **summary(side, "lines", ks)[0]})
        print(f"\n  {line}")
        print("    " + pd.DataFrame(rows).to_string(index=False).replace("\n", "\n    "))

print("\n==================== per-line vs 4-step tree, each at its chosen k ====================")
for side in ("B", "P"):
    a = per_pa(side, "lines", [best[side]])[:, 0]
    t = per_pa(side, "tree", [TREE_K[side]])[:, 0]
    d = a - t
    bt = (Wb @ np.bincount(g, weights=d, minlength=nG)) / (Wb @ cnt)
    print(f"  {'batters' if side == 'B' else 'pitchers'}: per-line minus tree {1e6 * d.mean():+.0f} x1e-6 per PA, SE {1e6 * bt.std():.0f}"
          f"  (negative = per-line predicts better)")
who = ("Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Jamie Mackay")
X = full["B"][0]
for method, ks in (("lines", best["B"]), ("tree", TREE_K["B"])):
    s, cd = summary("B", method, ks, who)
    print(f"\n  batters, {method}: {s}; total HR {float((cd[:, IX['HR']] * X.sum(axis=1)).sum()):.1f} (actual {int(X[:, IX['HR']].sum())})")
    names = [name.get(i, i) for i in people["B"]]
    for nm in who:
        i = names.index(nm)
        print(f"    {nm:16s} raw  " + " ".join(f"{l} {100 * X[i, j] / X[i].sum():5.1f}" for j, l in enumerate(ALL)))
        print(f"    {'':16s} card " + " ".join(f"{l} {100 * cd[i, j]:5.1f}" for j, l in enumerate(ALL)))
