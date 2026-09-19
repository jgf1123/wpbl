"""Seven-step chain of two-way splits vs the four-step tree.

Chain: HBP | rest;  K | rest;  BB | contact;  HR | in-park contact;  hit | fielded;
2B | 1B;  ROE | out.  Each split gives that outcome its own k.  Sluggers protected
at the HR split.  (1) chain k tuned on the usual 20 game splits; (2) nested
comparison (20 outer x 5 inner) with the tree; (3) cards for the 20 regulars."""
import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("chain_cv.py", "trees_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("\ngids = sorted(")])
__file__ = _here
pd.set_option("display.width", 250)
OUTER, INNER = 20, 5
NO_HBP = ("K", "BB") + BIP
CON = BIP                                        # HR 1B 2B ROE OUT
INPARK = ("1B", "2B", "ROE", "OUT")
HITS2 = ("1B", "2B")
FIELDED = ("ROE", "OUT")
CHAIN = [(PA_, [("HBP",), NO_HBP]), (NO_HBP, [("K",), ("BB",) + CON]), (("BB",) + CON, [("BB",), CON]),
         (CON, [("HR",), INPARK]), (INPARK, [HITS2, FIELDED]), (HITS2, [("2B",), ("1B",)]), (FIELDED, [("ROE",), ("OUT",)])]
CHAIN_NAMES = ["HBP | rest", "K | rest", "BB | contact", "HR | in-park", "hit | fielded", "2B | 1B", "ROE | out"]
TREE = SETUPS["4-step"]
TREE_NAMES = ["K | not K", "BB / HBP / in play", "out / ROE / hit", "HR / 1B / 2B"]
TREE_K = {"B": [32, 64, 45, 11], "P": [45, 256, 181, np.inf]}
STRUCT = {"tree": TREE, "chain": CHAIN}
HRS = {"tree": HR_STEP["4-step"], "chain": next(i for i, st in enumerate(CHAIN) if ("HR",) in st[1])}
pos_of = {s: pd.Series(np.arange(len(people[s])), index=people[s]) for s in ("B", "P")}


def record(build, side):
    X = counts(build, side)
    coh = all_cohorts(side, X)
    rec = {}
    for m, steps in STRUCT.items():
        C = child_counts(X, steps)
        rec[m] = (C, targets(C, coh, HRS[m]))
    return rec


def folds_for(game_ids, side, repeats, rng):
    out, gl = [], sorted(game_ids)
    sub = pa[pa["game_id"].isin(gl)]
    for _ in range(repeats):
        half = sub["game_id"].map(dict(zip(gl, rng.permutation(np.arange(len(gl)) % 2)))).to_numpy()
        for fold in (0, 1):
            test = sub.index[half == fold].to_numpy()
            out.append((record(sub[half != fold], side), test, pos_of[side][pa.loc[test, side]].to_numpy()))
    return out


def scores(m, folds, ks):
    tot, n = 0.0, 0
    for rec, test, pos in folds:
        C, T = rec[m]
        tot += float(((w[y[test]] - (card(C, T, ks, STRUCT[m]) @ w)[pos]) ** 2).sum()); n += len(test)
    return tot / n


def tune(m, folds, passes=2):
    ks = [64.0] * len(STRUCT[m])
    for _ in range(passes):
        for s in range(len(ks)):
            ks[s] = KGRID[int(np.argmin([scores(m, folds, ks[:s] + [k] + ks[s + 1:]) for k in KGRID]))]
    return ks


gids = sorted(pa["game_id"].unique())
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)

# ---------------- 1. chain tuned on the usual 20 splits, with 1-SE ranges ----------------
chain_k = {}
print("==================== chain: best k per split (usual 20 splits) ====================", flush=True)
for side in ("B", "P"):
    folds = folds_for(gids, side, REPEATS, np.random.default_rng(SEED))
    ks = tune("chain", folds)
    chain_k[side] = ks
    parts = []
    for s in range(len(ks)):
        S = np.zeros((len(pa), len(KGRID)))
        for rec, test, pos in folds:
            C, T = rec["chain"]
            for j, k in enumerate(KGRID):
                kk = ks[:s] + [k] + ks[s + 1:]
                S[test, j] += (w[y[test]] - (card(C, T, kk, CHAIN) @ w)[pos]) ** 2
        S /= REPEATS
        G = np.stack([np.bincount(g, weights=S[:, j], minlength=nG) for j in range(len(KGRID))], axis=1)
        pt, bt = S.mean(axis=0), (Wb @ G) / (Wb @ cnt)[:, None]
        b = int(np.argmin(pt))
        near = [KGRID[j] for j in range(len(KGRID)) if pt[j] - pt[b] <= (bt[:, j] - bt[:, b]).std()]
        parts.append(f"{CHAIN_NAMES[s]} {f(ks[s])} (1 SE {f(min(near))}-{f(max(near))})")
    print(f"  {'batters' if side == 'B' else 'pitchers'}: " + "; ".join(parts), flush=True)

# ---------------- 3. cards for the regulars ----------------
REGULARS = ["Denae Benites", "Ashton Lansdell", "Kelsie Whitmore", "Alexia Jorge", "Andreanne Leblanc", "Skylar Kaplan",
            "Natsuki Yonetani", "Kylee Lahners", "Caitlin Eynon", "Jua Park", "Jamie Mackay", "Ticara Geldenhuis",
            "Sarah Edwards", "Maggie Foxx", "Samaria Benitez", "Amanda Gianelloni", "Diana Ibarra", "Amira Hondras",
            "Joely Leguizamon", "Mo'ne Davis"]
full = record(pa, "B")
X = counts(pa, "B")
n = X.sum(axis=1)
L = X.sum(axis=0) / X.sum()
w_avg = float(L @ w)
cards = {m: card(*full[m], (TREE_K["B"] if m == "tree" else chain_k["B"]), STRUCT[m]) for m in STRUCT}
names = [name.get(i, i) for i in people["B"]]
rows = []
for nm in REGULARS:
    i = names.index(nm)
    raw = X[i] / n[i]
    row = {"player": nm, "raw": round(1000 * float((raw - L) @ (w - w_avg))),
           "tree": round(1000 * float((cards["tree"][i] - L) @ (w - w_avg))),
           "chain": round(1000 * float((cards["chain"][i] - L) @ (w - w_avg)))}
    for l in ("HBP", "HR", "2B", "1B", "K"):
        j = IX[l]
        row[l] = f"{100 * raw[j]:.1f}/{100 * cards['tree'][i, j]:.1f}/{100 * cards['chain'][i, j]:.1f}"
    rows.append(row)
reg = n >= 25
print("\n==================== the 20 regulars: runs above average per PA x1000, and line % as raw/tree/chain ====================")
print(pd.DataFrame(rows).to_string(index=False))
for m in STRUCT:
    v = (cards[m] - L) @ (w - w_avg)
    print(f"  {m}: spread among batters with 25+ PA {1000 * v[reg].std(ddof=1):.0f} (raw {1000 * (((X / np.maximum(n[:, None], 1)) - L) @ (w - w_avg))[reg].std(ddof=1):.0f}); "
          f"total HR {float((cards[m][:, IX['HR']] * n).sum()):.1f} (actual {int(X[:, IX['HR']].sum())})", flush=True)

# ---------------- 2. nested comparison ----------------
print("\n==================== nested: chain vs tree ====================", flush=True)
orng = np.random.default_rng(SEED + 11)
for side in ("B", "P"):
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
        print(f"  {side}: outer {r + 1}/{OUTER}", flush=True)
    label = "batters" if side == "B" else "pitchers"
    for m, nm in (("tree", TREE_NAMES), ("chain", CHAIN_NAMES)):
        a = np.log2(np.clip(np.array(chosen[m]), 1, 4096))
        med, lo, hi = np.median(a, axis=0), np.percentile(a, 25, axis=0), np.percentile(a, 75, axis=0)
        print(f"  {label} {m}: tuned k median [middle half]: " + "; ".join(
            f"{x} {f(2 ** md)} [{f(2 ** l_)}-{f(2 ** h_)}]" for x, md, l_, h_ in zip(nm, med, lo, hi)))
    d = (err["chain"] - err["tree"]) / OUTER
    bt = (Wb @ np.bincount(g, weights=d, minlength=nG)) / (Wb @ cnt)
    print(f"  {label}: chain minus tree {1e6 * d.mean():+.0f} x1e-6 per PA, SE {1e6 * bt.std():.0f}  (negative = chain predicts better)", flush=True)
