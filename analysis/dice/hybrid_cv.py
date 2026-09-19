"""Hybrid smoothing (4-step tree, own k per outcome within each step, renormalised within
the step), plus a nested comparison of tree / per-line / hybrid.

Nested: for each outer game split and fold, every method's k values are tuned only on
the outer build half (3 inner game splits x 2 folds), then scored on the outer test half."""
import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("hybrid_cv.py", "lines_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("\ngids = sorted(")])
__file__ = _here
OUTER, INNER = 10, 3
TREE_N = [len(st[1]) for st in TREE]                 # children per step: 2, 3, 3, 3
N_K = {"tree": len(TREE), "lines": len(ALL), "hybrid": sum(TREE_N)}


def hybrid_card(C, T, ks):
    prob, off = {PA_: np.ones(len(C[0]))}, 0
    for (node, children), Cs, Ts, m in zip(TREE, C, T, TREE_N):
        k = np.array(ks[off:off + m])[None, :]
        off += m
        n = Cs.sum(axis=1, keepdims=True)
        kf = np.where(np.isinf(k), 0.0, k)
        s = np.where(np.isinf(k), Ts, (Cs + kf * Ts) / np.maximum(n + kf, 1e-12))
        s = s / s.sum(axis=1, keepdims=True)            # renormalise within the step
        for j, c in enumerate(children):
            prob[c] = prob[node] * s[:, j]
    out = np.maximum(np.column_stack([prob[(l,)] for l in ALL]), MIN_RATE)
    return out / out.sum(axis=1, keepdims=True)


def make_card(method, rec, ks):
    X, LT, C, T = rec
    if method == "lines":
        return line_card(X, LT, ks)
    if method == "tree":
        return card(C, T, ks, TREE)
    return hybrid_card(C, T, ks)


def record(build, side):
    X = counts(build, side)
    coh = all_cohorts(side, X)
    C = child_counts(X, TREE)
    return (X, line_targets(X, coh), C, targets(C, coh, HR_STEP["4-step"]))


pos_of = {s: pd.Series(np.arange(len(people[s])), index=people[s]) for s in ("B", "P")}


def folds_for(game_ids, side, repeats, rng):
    """Records for random halves of the given games: [(record, test PA indices, positions)]."""
    out = []
    gl = sorted(game_ids)
    for _ in range(repeats):
        half_of = dict(zip(gl, rng.permutation(np.arange(len(gl)) % 2)))
        sub = pa[pa["game_id"].isin(gl)]
        half = sub["game_id"].map(half_of).to_numpy()
        for fold in (0, 1):
            test = sub.index[half == fold].to_numpy()
            out.append((record(sub[half != fold], side), test, pos_of[side][pa.loc[test, side]].to_numpy()))
    return out


def error(method, folds, ks):
    tot, n = 0.0, 0
    for rec, test, pos in folds:
        v = w[y[test]]
        tot += float(((v - (make_card(method, rec, ks) @ w)[pos]) ** 2).sum()); n += len(test)
    return tot / n


def tune(method, folds, passes=2):
    ks = [64.0] * N_K[method]
    for _ in range(passes):
        for s in range(len(ks)):
            errs = [error(method, folds, ks[:s] + [k] + ks[s + 1:]) for k in KGRID]
            ks[s] = KGRID[int(np.argmin(errs))]
    return ks


def names_of(method):
    if method == "lines":
        return ALL
    if method == "tree":
        return [STEP_NAME(st) for st in TREE]
    return [f"{('+'.join(c) if len(c) > 2 else ('not K' if c == NOTK else ('in play' if c == BIP else ('hit' if c == HIT else c[0]))))}"
            f" (step {i + 1})" for i, st in enumerate(TREE) for c in st[1]]


# ---------------- 1. hybrid tuned on the usual 20 splits, full-data cards ----------------
rng = np.random.default_rng(SEED)
gids = sorted(pa["game_id"].unique())
std_folds = {side: folds_for(gids, side, REPEATS, np.random.default_rng(SEED)) for side in ("B", "P")}
hyb = {side: tune("hybrid", std_folds[side]) for side in ("B", "P")}
full_rec = {side: record(pa, side) for side in ("B", "P")}
print("==================== hybrid: best k per outcome (tuned on the usual 20 splits) ====================")
for side in ("B", "P"):
    print(f"  {'batters' if side == 'B' else 'pitchers'}: " + ", ".join(f"{nm} {f(k)}" for nm, k in zip(names_of("hybrid"), hyb[side])))
X = full_rec["B"][0]
nb = X.sum(axis=1)
names = [name.get(i, i) for i in people["B"]]
reg = nb >= 25
for method, ks in (("hybrid", hyb["B"]), ("tree", TREE_K["B"])):
    cd = make_card(method, full_rec["B"], ks)
    v = cd @ w
    print(f"\n  batters, {method}: spread {1000 * v[reg].std(ddof=1):.0f} (raw 128); total HR "
          f"{float((cd[:, IX['HR']] * nb).sum()):.1f} (actual {int(X[:, IX['HR']].sum())})")
    for nm in ("Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Jamie Mackay"):
        i = names.index(nm)
        print(f"    {nm:16s} {1000 * v[i]:4.0f} | " + " ".join(f"{l} {100 * cd[i, j]:5.1f}" for j, l in enumerate(ALL)))
cdp = make_card("hybrid", full_rec["P"], hyb["P"])
npit = full_rec["P"][0].sum(axis=1)
print(f"\n  pitchers, hybrid: spread {1000 * (cdp @ w)[npit >= 40].std(ddof=1):.0f} (tree 46, raw 86)")

# ---------------- 2. nested comparison ----------------
print("\n==================== nested comparison: k tuned inside each outer build half ====================", flush=True)
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)
METHODS = ("tree", "lines", "hybrid")
orng = np.random.default_rng(SEED + 7)
for side in ("B", "P"):
    err = {m: np.zeros(len(pa)) for m in METHODS}
    chosen = {m: [] for m in METHODS}
    for r in range(OUTER):
        half_of = dict(zip(gids, orng.permutation(np.arange(len(gids)) % 2)))
        half = pa["game_id"].map(half_of).to_numpy()
        for fold in (0, 1):
            build_games = [gg for gg in gids if half_of[gg] != fold]
            inner = folds_for(build_games, side, INNER, orng)
            outer_rec = record(pa[half != fold], side)
            test = np.flatnonzero(half == fold)
            pos = pos_of[side][pa.loc[test, side]].to_numpy()
            for m in METHODS:
                ks = tune(m, inner)
                chosen[m].append(ks)
                err[m][test] += (w[y[test]] - (make_card(m, outer_rec, ks) @ w)[pos]) ** 2
        print(f"  {side}: outer split {r + 1}/{OUTER}", flush=True)
    label = "batters" if side == "B" else "pitchers"
    for m in METHODS:
        med = np.median(np.array(chosen[m]), axis=0)
        print(f"  {label} {m}: median tuned k " + ", ".join(f"{nm} {f(k)}" for nm, k in zip(names_of(m), med)))
    for a, b in (("lines", "tree"), ("hybrid", "tree"), ("hybrid", "lines")):
        d = (err[a] - err[b]) / OUTER
        bt = (Wb @ np.bincount(g, weights=d, minlength=nG)) / (Wb @ cnt)
        print(f"  {label}: {a} minus {b}: {1e6 * d.mean():+.0f} x1e-6 per PA, SE {1e6 * bt.std():.0f}"
              f"  (negative = {a} predicts better)")
