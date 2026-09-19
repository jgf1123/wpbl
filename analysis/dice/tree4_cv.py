"""Four-step tree: K / not K; then BB / HBP / in play; then out / ROE / hit; then HR / 1B / 2B.
k grid spaced by sqrt(2). Sluggers protected at the hit split. Otherwise as tree_cv.py."""
import numpy as np
import pandas as pd

SRC = open(__file__.replace("tree4_cv.py", "k_cv2.py"), encoding="utf-8").read()
exec(SRC[:SRC.index("def targets(")])
KGRID = [2 ** (i / 2) for i in range(23)] + [np.inf]          # 1, 1.41, 2, ... 2048
LAB = ["inf" if np.isinf(k) else (f"{k:.0f}" if k >= 10 else f"{k:.1f}") for k in KGRID]
COHORT_PA = 300
IX = {l: i for i, l in enumerate(ALL)}
STEPS = ["K / not K", "BB / HBP / in play", "out / ROE / hit", "HR / 1B / 2B"]
HIT_STEP = 3


def step_counts(X):
    K, BB, HBP, HR, B1, B2, ROE, OUT = (X[:, IX[l]] for l in ALL)
    hit = HR + B1 + B2
    bip = hit + ROE + OUT
    return [np.column_stack([K, BB + HBP + bip]), np.column_stack([BB, HBP, bip]),
            np.column_stack([OUT, ROE, hit]), np.column_stack([HR, B1, B2])]


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


def targets(side, X):
    C = step_counts(X)
    n = X.sum(axis=1)
    names = [name.get(i, i) for i in people[side]]
    slug = np.isin(names, SLUGGERS) if side == "B" else np.zeros(len(names), bool)
    base = cohorts(side, n)
    hit_cohort = cohorts(side, n, exclude=slug) if slug.any() else base
    in_slug = np.isin(names, SLUGGER_COHORT)
    T = []
    for s, Cs in enumerate(C):
        t = np.zeros((len(n), Cs.shape[1]))
        for i in range(len(n)):
            if s == HIT_STEP and slug[i]:
                take = np.flatnonzero(in_slug & (np.arange(len(n)) != i))
            else:
                take = (hit_cohort if s == HIT_STEP else base)[i]
            tot = Cs[take].sum(axis=0)
            t[i] = tot / tot.sum() if tot.sum() > 0 else Cs.sum(axis=0) / Cs.sum()
        T.append(t)
    return C, T


def card(C, T, ks):
    S = []
    for Cs, Ts, k in zip(C, T, ks):
        n = Cs.sum(axis=1, keepdims=True)
        S.append(Ts if np.isinf(k) else (Cs + k * Ts) / np.maximum(n + k, 1e-12))
    s0, s1, s2, s3 = S
    notk = s0[:, 1]
    bip = notk * s1[:, 2]
    hit = bip * s2[:, 2]
    out = np.column_stack([s0[:, 0], notk * s1[:, 0], notk * s1[:, 1], hit * s3[:, 0], hit * s3[:, 1],
                           hit * s3[:, 2], bip * s2[:, 1], bip * s2[:, 0]])          # ALL order
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
            cache[(r, fold, side)] = targets(side, counts(build, side))
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)


def scan(side, fixed):
    res = {}
    for s in range(4):
        S = np.zeros((len(pa), len(KGRID)))
        for r, half in enumerate(splits):
            for fold in (0, 1):
                test = np.flatnonzero(half == fold)
                C, T = cache[(r, fold, side)]
                pos = pd.Series(np.arange(len(people[side])), index=people[side])[pa.loc[test, side]].to_numpy()
                v = w[y[test]]
                for j, k in enumerate(KGRID):
                    ks = list(fixed); ks[s] = k
                    S[test, j] += (v - (card(C, T, ks) @ w)[pos]) ** 2
        S /= REPEATS
        G = np.stack([np.bincount(g, weights=S[:, j], minlength=nG) for j in range(len(KGRID))], axis=1)
        res[s] = (S.mean(axis=0), (Wb @ G) / (Wb @ cnt)[:, None])
    return res


f = lambda v: "inf" if np.isinf(v) else (f"{v:.0f}" if v >= 10 else f"{v:.1f}")
best = {}
for side in ("B", "P"):
    fixed = [64] * 4
    for p in (1, 2):
        res = scan(side, fixed)
        new = [KGRID[int(np.argmin(res[s][0]))] for s in range(4)]
        if p == 1:
            fixed = new
    best[side] = new
    print(f"\n==================== {'BATTERS (sluggers protected)' if side == 'B' else 'PITCHERS'}: pass 2, "
          f"other steps at {[f(k) for k in fixed]} ====================")
    curve = pd.DataFrame({STEPS[s]: [round(1e6 * (res[s][0][-1] - res[s][0][j])) for j in range(len(KGRID))]
                          for s in range(4)}, index=LAB)
    print("runs score gain over k = inf, x1e6 per PA (rows = k):")
    print(curve.to_string())
    for s in range(4):
        pt, bt = res[s]
        b = int(np.argmin(pt))
        se = np.array([(bt[:, j] - bt[:, b]).std() for j in range(len(KGRID))])
        n1 = [KGRID[j] for j in range(len(KGRID)) if pt[j] - pt[b] <= se[j]]
        n2 = [KGRID[j] for j in range(len(KGRID)) if pt[j] - pt[b] <= 2 * se[j]]
        print(f"  {STEPS[s]:20s} best {f(KGRID[b]):>5s}   within 1 SE {f(min(n1))}-{f(max(n1))}   "
              f"within 2 SE {f(min(n2))}-{f(max(n2))}   SE best vs inf {1e6 * se[-1]:.0f}")

# ---------------- full-data cards ----------------
print("\n==================== full-data cards at best k ====================")
for side, who in (("B", ["Ashton Lansdell", "Denae Benites", "Kelsie Whitmore", "Jamie Mackay"]),
                  ("P", ["Jaida Lee", "Brittany Apgar", "Jua Park"])):
    X = counts(pa, side)
    C, T = targets(side, X)
    ks = best[side]
    cd = card(C, T, ks)
    n = X.sum(axis=1)
    raw = X / np.maximum(n[:, None], 1)
    val = pd.DataFrame({"PA": n, "raw": raw @ w, "card": cd @ w}, index=[name.get(i, i) for i in people[side]])
    reg = val["PA"] >= (25 if side == "B" else 40)
    print(f"\n--- {'batters' if side == 'B' else 'pitchers'}: k = {[f(k) for k in ks]}; spread among regulars raw "
          f"{1000 * val.loc[reg, 'raw'].std():.0f}, card {1000 * val.loc[reg, 'card'].std():.0f}")
    if side == "B":
        print(f"    total HR: actual {int(X[:, IX['HR']].sum())}, card {float((cd[:, IX['HR']] * n).sum()):.1f}")
    for nm in who:
        i = list(val.index).index(nm)
        t = pd.DataFrame({"raw %": 100 * raw[i], "card %": 100 * cd[i]}, index=ALL).round(1).T
        print(f"    {nm} ({int(n[i])} {'PA' if side == 'B' else 'BF'}): runs/PA x1000 raw {1000 * val['raw'].iloc[i]:.0f} "
              f"-> card {1000 * val['card'].iloc[i]:.0f}")
        print("      " + t.to_string().replace("\n", "\n      "))
        if side == "B" and nm in ("Denae Benites", "Ashton Lansdell"):
            # switch steps from raw (k = 0) to smoothed one at a time, in tree order
            prev, parts = None, []
            for m in range(5):
                kk = [ks[s] if s < m else 0 for s in range(4)]
                v = (card([c[i:i + 1] for c in C], [t_[i:i + 1] for t_ in T], kk) @ w)[0]
                if prev is not None:
                    parts.append(f"{STEPS[m - 1]} {1000 * (v - prev):+.0f}")
                prev = v
            sh = [c[i] / c[i].sum() for c in C]
            tg = [t_[i] for t_ in T]
            print(f"      step effects on runs/PA x1000: " + "; ".join(parts))
            print(f"      her raw shares vs cohort target:  K {100 * sh[0][0]:.1f} vs {100 * tg[0][0]:.1f};  "
                  f"hits per ball in play {100 * sh[2][2]:.1f} vs {100 * tg[2][2]:.1f};  HR share of hits {100 * sh[3][0]:.1f} vs {100 * tg[3][0]:.1f}")
