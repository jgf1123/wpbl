"""Two-step (tree) smoothing, k per step chosen on held-out games.

Step 1 per PA: K / BB / HBP / in play.  Step 2 per ball in play: out / ROE / hit.
Step 3 per hit: HR / 1B / 2B.  Each step is a full distribution smoothed toward the
cohort's with one k:  (counts + k * cohort share) / (n + k), so it sums to 1.
Card line = product along its path; 1% floor, then renormalised to 100%.
Cohort: nearest players by usage share (whole tie groups), excluding her, until
300 PA/BF. Variants: 'protect' (Benites/Whitmore hit split toward each other +
Lansdell + Mackay, and out of everyone else's hit-split cohort) and 'same'."""
import numpy as np
import pandas as pd

SRC = open(__file__.replace("tree_cv.py", "k_cv2.py"), encoding="utf-8").read()
exec(SRC[:SRC.index("def targets(")])                  # data, shares, people, weights w over ALL
KGRID = [2 ** i for i in range(12)] + [np.inf]
LAB = [str(k) if np.isfinite(k) else "inf" for k in KGRID]
COHORT_PA = 300
IX = {l: i for i, l in enumerate(ALL)}                 # ALL = K BB HBP HR 1B 2B ROE OUT
STEPS = ["PA split", "in-play split", "hit split"]


def step_counts(X):
    """Per-person counts at each step from an 8-line count matrix."""
    K, BB, HBP, HR, B1, B2, ROE, OUT = (X[:, IX[l]] for l in ALL)
    hit = HR + B1 + B2
    bip = hit + ROE + OUT
    return [np.column_stack([K, BB, HBP, bip]), np.column_stack([OUT, ROE, hit]), np.column_stack([HR, B1, B2])]


def cohorts(side, n, exclude=None):
    """Indices of each person's cohort: nearest by usage share, whole ties, >= COHORT_PA."""
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


def targets(side, X, variant):
    """Cohort share at each step, per person."""
    C = step_counts(X)
    n = X.sum(axis=1)
    names = [name.get(i, i) for i in people[side]]
    slug = np.isin(names, SLUGGERS) if (side == "B" and variant == "protect") else np.zeros(len(names), bool)
    base = cohorts(side, n)
    hit_cohort = cohorts(side, n, exclude=slug) if slug.any() else base
    in_slug = np.isin(names, SLUGGER_COHORT)
    T = []
    for s, Cs in enumerate(C):
        t = np.zeros((len(n), Cs.shape[1]))
        for i in range(len(n)):
            if s == 2 and slug[i]:
                take = np.flatnonzero(in_slug & (np.arange(len(n)) != i))
            else:
                take = (hit_cohort if s == 2 else base)[i]
            tot = Cs[take].sum(axis=0)
            t[i] = tot / tot.sum() if tot.sum() > 0 else Cs.sum(axis=0) / Cs.sum()
        T.append(t)
    return C, T


def card(C, T, ks):
    """8-line card from step counts, cohort shares and one k per step."""
    S = []
    for Cs, Ts, k in zip(C, T, ks):
        n = Cs.sum(axis=1, keepdims=True)
        s = Ts if np.isinf(k) else (Cs + k * Ts) / (n + k)
        S.append(s)
    s1, s2, s3 = S
    bip = s1[:, 3:4]
    hit = bip * s2[:, 2:3]
    out = np.column_stack([s1[:, 0], s1[:, 1], s1[:, 2], hit[:, 0] * s3[:, 0], hit[:, 0] * s3[:, 1],
                           hit[:, 0] * s3[:, 2], bip[:, 0] * s2[:, 1], bip[:, 0] * s2[:, 0]])   # ALL order
    out = np.maximum(out, MIN_RATE)
    return out / out.sum(axis=1, keepdims=True)


def counts(frame, side):
    return pd.crosstab(frame[side], frame["line"]).reindex(index=people[side], columns=ALL, fill_value=0).to_numpy().astype(float)


# ---------------- held-out scoring: two coordinate passes ----------------
gids = sorted(pa["game_id"].unique())
splits = []
rng = np.random.default_rng(SEED)
for r in range(REPEATS):
    half_of = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    splits.append(pa["game_id"].map(half_of).to_numpy())

# cache targets per (split, fold, side, variant): the expensive part
cache = {}
for r, half in enumerate(splits):
    for fold in (0, 1):
        build = pa[half != fold]
        for side in ("B", "P"):
            X = counts(build, side)
            for variant in (("protect", "same") if side == "B" else ("same",)):
                cache[(r, fold, side, variant)] = targets(side, X, variant)
    print(f"  targets for split {r + 1}/{REPEATS}", flush=True)

g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)


def scan(side, variant, fixed):
    """Held-out runs score for each step's k, other steps at `fixed`. Returns {step: (point, boot)}."""
    res = {}
    for s in range(3):
        S = np.zeros((len(pa), len(KGRID)))
        for r, half in enumerate(splits):
            for fold in (0, 1):
                test = np.flatnonzero(half == fold)
                C, T = cache[(r, fold, side, variant)]
                pos = pd.Series(np.arange(len(people[side])), index=people[side])[pa.loc[test, side]].to_numpy()
                v = w[y[test]]
                for j, k in enumerate(KGRID):
                    ks = list(fixed); ks[s] = k
                    m = card(C, T, ks) @ w
                    S[test, j] += (v - m[pos]) ** 2
        S /= REPEATS
        G = np.stack([np.bincount(g, weights=S[:, j], minlength=nG) for j in range(len(KGRID))], axis=1)
        res[s] = (S.mean(axis=0), (Wb @ G) / (Wb @ cnt)[:, None])
    return res


best = {}
for side, variant in (("B", "protect"), ("B", "same"), ("P", "same")):
    fixed = [64, 64, 64]
    for p in (1, 2):
        res = scan(side, variant, fixed)
        new = [KGRID[int(np.argmin(res[s][0]))] for s in range(3)]
        if p == 1:
            fixed = new
    best[(side, variant)] = new
    title = f"{'BATTERS' if side == 'B' else 'PITCHERS'} ({variant})" if side == "B" else "PITCHERS"
    print(f"\n==================== {title}: pass 2 (other steps at their pass-1 best {fixed}) ====================")
    print("runs score gain over k = inf, x1e6 per PA (higher is better)")
    rows = []
    for s in range(3):
        pt, bt = res[s]
        b = int(np.argmin(pt))
        se = np.array([(bt[:, j] - bt[:, b]).std() for j in range(len(KGRID))])
        n1 = [KGRID[j] for j in range(len(KGRID)) if pt[j] - pt[b] <= se[j]]
        n2 = [KGRID[j] for j in range(len(KGRID)) if pt[j] - pt[b] <= 2 * se[j]]
        f = lambda v: "inf" if np.isinf(v) else str(int(v))
        rows.append({"step": STEPS[s], **{LAB[j]: round(1e6 * (pt[-1] - pt[j])) for j in range(len(KGRID) - 1)},
                     "best": LAB[b], "within 1 SE": f"{f(min(n1))}-{f(max(n1))}", "within 2 SE": f"{f(min(n2))}-{f(max(n2))}",
                     "SE best vs inf": round(1e6 * se[-1])})
    print(pd.DataFrame(rows).to_string(index=False))
    print("best k per step:", dict(zip(STEPS, [f(k) for k in new])))

# ---------------- full-data cards at the best k ----------------
LINES8 = ALL
print("\n==================== full-data cards at best k ====================")
raw_rates = {}
for side in ("B", "P"):
    X = counts(pa, side)
    raw_rates[side] = X / np.maximum(X.sum(axis=1, keepdims=True), 1)
for side, variant, who in (("B", "protect", ["Ashton Lansdell", "Denae Benites", "Kelsie Whitmore", "Jamie Mackay"]),
                           ("B", "same", ["Ashton Lansdell", "Denae Benites", "Kelsie Whitmore", "Jamie Mackay"]),
                           ("P", "same", ["Brittany Apgar", "Jua Park", "Jaida Lee"])):
    X = counts(pa, side)
    C, T = targets(side, X, variant)
    cd = card(C, T, best[(side, variant)])
    n = X.sum(axis=1)
    raw = raw_rates[side]
    val = pd.DataFrame({"PA": n, "raw": raw @ w, "card": cd @ w}, index=[name.get(i, i) for i in people[side]])
    reg = val["PA"] >= (25 if side == "B" else 40)
    label = f"{'batters' if side == 'B' else 'pitchers'}, {variant}"
    print(f"\n--- {label}: k = {best[(side, variant)]}; spread among regulars raw {1000 * val.loc[reg, 'raw'].std():.0f}, "
          f"card {1000 * val.loc[reg, 'card'].std():.0f} (per-line best-k cards: batters 74, pitchers 42)")
    if side == "B":
        print(f"    total HR: actual {int(X[:, IX['HR']].sum())}, card {float((cd[:, IX['HR']] * n).sum()):.1f}")
    for nm in who:
        i = list(val.index).index(nm)
        t = pd.DataFrame({"raw %": 100 * raw[i], "card %": 100 * cd[i]}, index=LINES8).round(1).T
        print(f"    {nm} ({int(n[i])} {'PA' if side == 'B' else 'BF'}): runs/PA x1000 raw {1000 * val['raw'].iloc[i]:.0f} -> card {1000 * val['card'].iloc[i]:.0f}")
        print("      " + t.to_string().replace("\n", "\n      "))
