"""Correlation of players' true rates between lines, sampling noise removed.

Observed covariance of player rates minus the covariance multinomial sampling alone
produces ((diag(p) - p p') / n per player; plus the cohort average's own noise when
rates are taken relative to the cohort). Correlations only where both lines have
positive estimated true variance. 90% intervals: resample players."""
import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("talent_corr.py", "trees_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("\ngids = sorted(")])
__file__ = _here
pd.set_option("display.width", 250)
LAB = {"K": "K", "BB": "BB", "HBP": "HBP", "HR": "HR", "1B": "1B", "2B": "2B", "ROE": "ROE", "OUT": "Out"}
FLOOR = {"B": 25, "P": 40}
rng = np.random.default_rng(20260919)


def talent_cov(D, N, P, Nc=None):
    """D: deviations (players x 8); N: PAs; P: rate the noise is computed at; Nc: cohort PAs."""
    obs = D.T @ D / len(D)
    noise = np.zeros((D.shape[1], D.shape[1]))
    for p, n, nc in zip(P, N, Nc if Nc is not None else [np.inf] * len(N)):
        m = np.diag(p) - np.outer(p, p)
        noise += m / n + (m / nc if np.isfinite(nc) else 0)
    return obs - noise / len(D)


def corr(C):
    sd = np.sqrt(np.where(np.diag(C) > 0, np.diag(C), np.nan))
    return C / np.outer(sd, sd), sd


def analyse(side, keep_mask, relative, title):
    X = counts(pa, side)
    n = X.sum(axis=1)
    R = X / np.maximum(n[:, None], 1)
    L = X.sum(axis=0) / X.sum()
    q = (n >= FLOOR[side]) & keep_mask
    if relative == "cohort":
        base, _, _ = all_cohorts(side, X)
        T = np.array([X[c].sum(axis=0) / X[c].sum() for c in base])
        Nc = np.array([X[c].sum() for c in base])
        D, P = R - T, T
    else:
        D = R - R[q].mean(axis=0)
        P, Nc = np.tile(L, (len(R), 1)), None
    Dq, Nq, Pq = D[q], n[q], P[q]
    Ncq = Nc[q] if Nc is not None else None
    Cm, sd = corr(talent_cov(Dq, Nq, Pq, Ncq))
    boots = []
    for _ in range(2000):
        i = rng.integers(0, len(Dq), len(Dq))
        Cb, _ = corr(talent_cov(Dq[i], Nq[i], Pq[i], Ncq[i] if Ncq is not None else None))
        boots.append(Cb)
    boots = np.array(boots)
    lo, hi = np.nanpercentile(boots, 5, axis=0), np.nanpercentile(boots, 95, axis=0)
    print(f"\n=== {title}: {int(q.sum())} players ===")
    print("true spread SD (pts): " + ", ".join(f"{LAB[l]} {100 * s:.1f}" if np.isfinite(s) else f"{LAB[l]} none"
                                                for l, s in zip(ALL, sd)))
    rows = []
    for a in range(len(ALL)):
        for b in range(a + 1, len(ALL)):
            if np.isfinite(Cm[a, b]):
                rows.append({"pair": f"{LAB[ALL[a]]}-{LAB[ALL[b]]}", "r": round(float(np.clip(Cm[a, b], -1.5, 1.5)), 2),
                             "90% interval": f"{np.clip(lo[a, b], -1.5, 1.5):+.2f} to {np.clip(hi[a, b], -1.5, 1.5):+.2f}",
                             "clear of 0": "yes" if lo[a, b] > 0 or hi[a, b] < 0 else ""})
    t = pd.DataFrame(rows).sort_values("r")
    print(t.to_string(index=False))


names = {s: np.array([name.get(i, i) for i in people[s]]) for s in ("B", "P")}
notslug = ~np.isin(names["B"], SLUGGERS)
everyone = {s: np.ones(len(people[s]), bool) for s in ("B", "P")}
analyse("B", everyone["B"], "cohort", "BATTERS, rates relative to usage cohort")
analyse("B", notslug, "cohort", "BATTERS without Benites and Whitmore, relative to usage cohort")
analyse("B", everyone["B"], "league", "BATTERS, rates relative to league average (includes regular-vs-bench differences)")
analyse("P", everyone["P"], "cohort", "PITCHERS, rates relative to usage cohort")
analyse("P", everyone["P"], "league", "PITCHERS, rates relative to league average")
