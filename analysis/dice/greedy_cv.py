"""Greedy "most reliable split first" structure, chosen inside each build half, vs structure C.

At each group of outcomes, every two-way split is scored by its method-of-moments k
(spread of players' conditional shares around their usage cohort's, minus player and
cohort sampling noise); the smallest k is taken and the rule recurses into both parts.
Sluggers are left out of the k estimates (ASSUMPTION). Nested: structure choice and k
tuning happen inside each outer build half; the outer half is scored once."""
from collections import Counter
from itertools import combinations
import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("greedy_cv.py", "chain_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("\ngids = sorted(")])
__file__ = _here
OUTER, INNER, SIDE = 20, 5, "B"
MIN_NODE = 10
ORDER = {l: i for i, l in enumerate(ALL)}
canon = lambda s: tuple(sorted(s, key=ORDER.get))
TTO = ("K", "BB", "HBP", "HR")
STRUCT_C = [(PA_, [TTO, INPARK]), (TTO, [("HBP",), ("K", "BB", "HR")]), (("K", "BB", "HR"), [("HR",), ("K", "BB")]),
            (("K", "BB"), [("K",), ("BB",)]), (INPARK, [("1B",), ("2B", "ROE", "OUT")]),
            (("2B", "ROE", "OUT"), [("OUT",), ("2B", "ROE")]), (("2B", "ROE"), [("ROE",), ("2B",)])]
names_all = np.array([name.get(i, i) for i in people[SIDE]])
not_slug = ~np.isin(names_all, SLUGGERS)


def describe(steps):
    return " ; ".join(" | ".join("+".join(c) for c in parts) for _, parts in steps)


def greedy(X, base):
    """Structure (and each step's k estimate) by smallest-k-first splitting."""
    XC = np.array([X[c].sum(axis=0) for c in base])
    npa = X.sum(axis=1)
    qual = (npa >= 25) & not_slug
    steps, kest, queue = [], [], [tuple(ALL)]
    while queue:
        node = queue.pop(0)
        if len(node) < 2:
            continue
        idx = [IX[l] for l in node]
        n, cn = X[:, idx].sum(axis=1), XC[:, idx].sum(axis=1)
        ok = qual & (n >= MIN_NODE) & (cn > 0)
        best = None
        for r in range(len(node) - 1):
            for extra in combinations(node[1:], r):
                S = (node[0],) + extra
                sidx = [IX[l] for l in S]
                x, cx = X[:, sidx].sum(axis=1), XC[:, sidx].sum(axis=1)
                if ok.sum() >= 8:
                    t, rr, nn, cc = cx[ok] / cn[ok], x[ok] / n[ok], n[ok], cn[ok]
                    tau2 = float(np.mean((rr - t) ** 2 - t * (1 - t) / nn - t * (1 - t) / cc))
                else:
                    tau2 = -np.inf
                pbar = X[:, sidx].sum() / X[:, idx].sum()
                k = pbar * (1 - pbar) / tau2 if tau2 > 0 else np.inf
                key = (k, -tau2)
                if best is None or key < best[0]:
                    best = (key, S)
        S = canon(best[1])
        R = canon([l for l in node if l not in S])
        steps.append((node, [S, R]))
        kest.append(best[0][0])
        queue += [S, R]
    return steps, kest


def hr_step(steps):
    return next(i for i, (_, parts) in enumerate(steps) if ("HR",) in parts)


def base_record(frame):
    X = counts(frame, SIDE)
    return X, all_cohorts(SIDE, X)


def ct(rec, steps):
    X, coh = rec
    C = child_counts(X, steps)
    return C, targets(C, coh, hr_step(steps))


def inner_folds(game_ids, rng):
    out, gl = [], sorted(game_ids)
    sub = pa[pa["game_id"].isin(gl)]
    for _ in range(INNER):
        half = sub["game_id"].map(dict(zip(gl, rng.permutation(np.arange(len(gl)) % 2)))).to_numpy()
        for fold in (0, 1):
            test = sub.index[half == fold].to_numpy()
            out.append((base_record(sub[half != fold]), test, pos_of[SIDE][pa.loc[test, SIDE]].to_numpy()))
    return out


def tune(steps, folds):
    prepared = [(ct(rec, steps), test, pos) for rec, test, pos in folds]

    def err(ks):
        tot, n = 0.0, 0
        for (C, T), test, pos in prepared:
            tot += float(((w[y[test]] - (card(C, T, ks, steps) @ w)[pos]) ** 2).sum()); n += len(test)
        return tot / n
    ks = [64.0] * len(steps)
    for _ in range(2):
        for s in range(len(ks)):
            ks[s] = KGRID[int(np.argmin([err(ks[:s] + [k] + ks[s + 1:]) for k in KGRID]))]
    return ks


# ---- the rule on all 36 games ----
X_all, coh_all = base_record(pa)
g_steps, g_k = greedy(X_all, coh_all[0])
print("greedy structure on all training games (step: split, k estimate):")
for (node, parts), k in zip(g_steps, g_k):
    print(f"  {' | '.join('+'.join(c) for c in parts):32s} k {f(k)}")
print("same as C:", describe(g_steps) == describe(STRUCT_C) or set(map(str, g_steps)) == set(map(str, STRUCT_C)), flush=True)

# ---- nested ----
gids = sorted(pa["game_id"].unique())
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)
orng = np.random.default_rng(SEED + 23)
err = {"greedy": np.zeros(len(pa)), "C": np.zeros(len(pa))}
found = Counter()
for r in range(OUTER):
    half_of = dict(zip(gids, orng.permutation(np.arange(len(gids)) % 2)))
    half = pa["game_id"].map(half_of).to_numpy()
    for fold in (0, 1):
        build_games = [gg for gg in gids if half_of[gg] != fold]
        brec = base_record(pa[half != fold])
        steps_g, _ = greedy(*[brec[0], brec[1][0]])
        key = describe(sorted(steps_g, key=lambda s: len(s[0]), reverse=True))
        found[key] += 1
        inner = inner_folds(build_games, orng)
        test = np.flatnonzero(half == fold)
        pos = pos_of[SIDE][pa.loc[test, SIDE]].to_numpy()
        for m, steps in (("greedy", steps_g), ("C", STRUCT_C)):
            ks = tune(steps, inner)
            C, T = ct(brec, steps)
            err[m][test] += (w[y[test]] - (card(C, T, ks, steps) @ w)[pos]) ** 2
    print(f"  outer {r + 1}/{OUTER}", flush=True)
key_c = describe(sorted(STRUCT_C, key=lambda s: len(s[0]), reverse=True))
print(f"\nstructures the rule chose across {2 * OUTER} build halves (C counted {found.get(key_c, 0)} times):")
for k_, v in found.most_common(5):
    print(f"  {v:2d}x  {k_}")
d = (err["greedy"] - err["C"]) / OUTER
bt = (Wb @ np.bincount(g, weights=d, minlength=nG)) / (Wb @ cnt)
print(f"\ngreedy rule minus C: {1e6 * d.mean():+.0f} x1e-6 per PA, SE {1e6 * bt.std():.0f}  (negative = rule better)")
