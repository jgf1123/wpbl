"""Compare tree setups for smoothing, and show how sharp each step's k is.

Setups (each step a full distribution smoothed toward the cohort with one k):
  a: PA -> K / BB / HBP / in play;          in play -> out / ROE / HR / 1B / 2B
  b: PA -> K / not K; not K -> BB / HBP / in play; in play -> out / ROE / HR / 1B / 2B
  4-step (reference): PA -> K / not K; not K -> BB / HBP / in play; in play -> out / ROE / hit; hit -> HR / 1B / 2B
Sluggers protected at whichever step splits out HR."""
import numpy as np
import pandas as pd

SRC = open(__file__.replace("trees_cv.py", "k_cv2.py"), encoding="utf-8").read()
exec(SRC[:SRC.index("def targets(")])
KGRID = [2 ** (i / 2) for i in range(23)] + [np.inf]
f = lambda v: "inf" if np.isinf(v) else (f"{v:.0f}" if v >= 10 else f"{v:.1f}")
COHORT_PA = 300
IX = {l: i for i, l in enumerate(ALL)}               # K BB HBP HR 1B 2B ROE OUT
BIP = ("HR", "1B", "2B", "ROE", "OUT")
NOTK = ("BB", "HBP") + BIP
HIT = ("HR", "1B", "2B")
PA_ = tuple(ALL)
SETUPS = {   # each step: (node, children); every child is a tuple of leaf lines
    "a": [(PA_, [("K",), ("BB",), ("HBP",), BIP]), (BIP, [("OUT",), ("ROE",), ("HR",), ("1B",), ("2B",)])],
    "b": [(PA_, [("K",), NOTK]), (NOTK, [("BB",), ("HBP",), BIP]), (BIP, [("OUT",), ("ROE",), ("HR",), ("1B",), ("2B",)])],
    "4-step": [(PA_, [("K",), NOTK]), (NOTK, [("BB",), ("HBP",), BIP]), (BIP, [("OUT",), ("ROE",), HIT]), (HIT, [("HR",), ("1B",), ("2B",)])],
}
STEP_NAME = lambda st: " / ".join(("+".join(c) if len(c) > 2 else ("not K" if c == NOTK else ("in play" if c == BIP else ("hit" if c == HIT else c[0])))) for c in st[1])
HR_STEP = {name: next(i for i, st in enumerate(steps) if ("HR",) in st[1]) for name, steps in SETUPS.items()}


def child_counts(X, steps):
    return [np.column_stack([X[:, [IX[l] for l in c]].sum(axis=1) for c in st[1]]) for st in steps]


def cohorts(side, n, exclude=None):
    sv = share[side].reindex(people[side]).fillna(0.0).to_numpy()
    out = []
    for i in range(len(sv)):
        ok = (np.arange(len(sv)) != i) & (n > 0)
        if exclude is not None:
            ok &= ~exclude
        cand = np.flatnonzero(ok)
        dist = np.round(np.abs(sv[cand] - sv[i]), 12)
        take, got = [], 0.0
        for d in np.unique(dist):
            grp = cand[dist == d]
            take.extend(grp); got += n[grp].sum()
            if got >= COHORT_PA:
                break
        out.append(np.array(take))
    return out


def all_cohorts(side, X):
    n = X.sum(axis=1)
    names = [name.get(i, i) for i in people[side]]
    slug = np.isin(names, SLUGGERS) if side == "B" else np.zeros(len(names), bool)
    base = cohorts(side, n)
    excl = cohorts(side, n, exclude=slug) if slug.any() else base
    in_slug = np.isin(names, SLUGGER_COHORT)
    special = [np.flatnonzero(in_slug & (np.arange(len(n)) != i)) if slug[i] else None for i in range(len(n))]
    return base, excl, special


def targets(C, coh, hr_step):
    base, excl, special = coh
    T = []
    for s, Cs in enumerate(C):
        t = np.zeros_like(Cs)
        for i in range(len(Cs)):
            take = special[i] if (s == hr_step and special[i] is not None) else (excl if s == hr_step else base)[i]
            tot = Cs[take].sum(axis=0)
            t[i] = tot / tot.sum() if tot.sum() > 0 else Cs.sum(axis=0) / Cs.sum()
        T.append(t)
    return T


def card(C, T, ks, steps):
    prob = {PA_: np.ones(len(C[0]))}
    for (node, children), Cs, Ts, k in zip(steps, C, T, ks):
        n = Cs.sum(axis=1, keepdims=True)
        s = Ts if np.isinf(k) else (Cs + k * Ts) / np.maximum(n + k, 1e-12)
        for j, c in enumerate(children):
            prob[c] = prob[node] * s[:, j]
    out = np.column_stack([prob[(l,)] for l in ALL])
    out = np.maximum(out, MIN_RATE)
    return out / out.sum(axis=1, keepdims=True)


def counts(frame, side):
    return pd.crosstab(frame[side], frame["line"]).reindex(index=people[side], columns=ALL, fill_value=0).to_numpy().astype(float)


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
            for sname, steps in SETUPS.items():
                C = child_counts(X, steps)
                cache[(r, fold, side, sname)] = (C, targets(C, coh, HR_STEP[sname]))
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)
pos_of = {s: pd.Series(np.arange(len(people[s])), index=people[s]) for s in ("B", "P")}


def per_pa(side, sname, ks_list):
    """Held-out squared run error per PA for each ks in ks_list (averaged over repeats)."""
    S = np.zeros((len(pa), len(ks_list)))
    steps = SETUPS[sname]
    for r, half in enumerate(splits):
        for fold in (0, 1):
            test = np.flatnonzero(half == fold)
            C, T = cache[(r, fold, side, sname)]
            pos = pos_of[side][pa.loc[test, side]].to_numpy()
            v = w[y[test]]
            for j, ks in enumerate(ks_list):
                S[test, j] += (v - (card(C, T, ks, steps) @ w)[pos]) ** 2
    return S / REPEATS


def boot(S):
    G = np.stack([np.bincount(g, weights=S[:, j], minlength=nG) for j in range(S.shape[1])], axis=1)
    return S.mean(axis=0), (Wb @ G) / (Wb @ cnt)[:, None]


# full-data pieces for the card-effect columns
full = {}
for side in ("B", "P"):
    X = counts(pa, side)
    coh = all_cohorts(side, X)
    for sname, steps in SETUPS.items():
        C = child_counts(X, steps)
        full[(side, sname)] = (X, C, targets(C, coh, HR_STEP[sname]))


def card_summary(side, sname, ks):
    X, C, T = full[(side, sname)]
    v = card(C, T, ks, SETUPS[sname]) @ w
    n = X.sum(axis=1)
    names = [name.get(i, i) for i in people[side]]
    reg = n >= (25 if side == "B" else 40)
    out = {"spread": round(1000 * v[reg].std(ddof=1))}
    for nm in (("Denae Benites", "Ashton Lansdell") if side == "B" else ("Jaida Lee",)):
        out[nm.split()[-1]] = round(1000 * v[names.index(nm)])
    return out


results = {}
for sname, steps in SETUPS.items():
    for side in ("B", "P"):
        fixed = [64.0] * len(steps)
        for p in (1, 2):
            new = []
            curves = {}
            for s in range(len(steps)):
                ks_list = [fixed[:s] + [k] + fixed[s + 1:] for k in KGRID]
                pt, bt = boot(per_pa(side, sname, ks_list))
                curves[s] = (pt, bt)
                new.append(KGRID[int(np.argmin(pt))])
            if p == 1:
                fixed_pass1 = new
                fixed = new
        results[(sname, side)] = (new, curves, fixed_pass1)
        who = "BATTERS" if side == "B" else "PITCHERS"
        print(f"\n==================== setup {sname}, {who}: best k {[f(k) for k in new]} "
              f"(pass 2, other steps at pass-1 best {[f(k) for k in fixed_pass1]}) ====================")
        for s in range(len(steps)):
            pt, bt = curves[s]
            b = int(np.argmin(pt))
            rows = []
            for j in range(max(0, b - 3), min(len(KGRID), b + 4)):
                loss = pt[j] - pt[b]
                se = (bt[:, j] - bt[:, b]).std()
                ks = list(new); ks[s] = KGRID[j]
                rows.append({"k": f(KGRID[j]), "loss vs best x1e6": round(1e6 * loss), "SE": round(1e6 * se),
                             "loss/SE": round(loss / se, 1) if se > 0 else 0.0, **card_summary(side, sname, ks)})
            print(f"\n  step {s + 1}: {STEP_NAME(steps[s])}")
            print("    " + pd.DataFrame(rows).to_string(index=False).replace("\n", "\n    "))

# ---------------- head to head, each setup at its own best k ----------------
print("\n==================== setups head to head (held-out runs error at each setup's best k) ====================")
for side in ("B", "P"):
    per = {sname: per_pa(side, sname, [results[(sname, side)][0]])[:, 0] for sname in SETUPS}
    ref = per["4-step"]
    for sname in ("a", "b"):
        d = per[sname] - ref
        G = np.bincount(g, weights=d, minlength=nG)
        bt = (Wb @ G) / (Wb @ cnt)
        print(f"  {'batters' if side == 'B' else 'pitchers'}: setup {sname} minus 4-step: {1e6 * d.mean():+.0f} x1e-6 per PA, "
              f"SE {1e6 * bt.std():.0f}  (negative = setup {sname} predicts better)")
    for sname in SETUPS:
        print(f"    setup {sname} at best k {[f(k) for k in results[(sname, side)][0]]}: {card_summary(side, sname, results[(sname, side)][0])}")
