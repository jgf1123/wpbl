"""Which card choice is sharp, and which rate is the most luck-driven.

A: error curve around each step's best k, in the chosen batter and pitcher structures.
   "Sharp" = moving k off the best value costs prediction. Reported as the rise at
   k/4 and 4k, in 1e-6 runs per PA, against the SE of that rise.
B: the share of each rate's spread across players that is real rather than sampling
   noise (method of moments, each rate on its own denominator).
"""
from pathlib import Path

import numpy as np
import pandas as pd
_here = __file__
__file__ = _here.replace("sharpness.py", "tto_c.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("# ---- nested ----")])
__file__ = _here
pd.set_option("display.width", 220)

# ---------------- A. sharpness of each step ----------------
print("\n=== A. cost of moving each step's k, x1e-6 runs per PA (0 = best) ===")


def per_pa_err(m, folds, ks):
    """Squared error per PA, and per game, so the rise can carry an SE."""
    tot = np.zeros(nG)
    cntg = np.zeros(nG)
    for rec, test, pos in folds:
        C, T = rec[m]
        e = (w[y[test]] - (card(C, T, ks, STRUCT[m]) @ w)[pos]) ** 2
        np.add.at(tot, g[test], e)
        np.add.at(cntg, g[test], 1.0)
    return tot, cntg


def sweep(m, folds, ks, s):
    base_t, base_c = per_pa_err(m, folds, ks)
    rows = []
    for k in KGRID:
        t, c = per_pa_err(m, folds, ks[:s] + [k] + ks[s + 1:])
        d = (t - base_t) / np.maximum(c, 1e-9).sum()
        bt = (Wb @ (t - base_t)) / (Wb @ c)
        rows.append({"k": f(k), "rise": 1e6 * float((t - base_t).sum() / c.sum()),
                     "SE": 1e6 * float(bt.std())})
    return pd.DataFrame(rows)


CURVES = {}                      # (structure, step) -> (name, best k, curve)
for m, s_list in (("C", C_),):
    ks = best[m]
    for s, st in enumerate(s_list):
        cur = sweep(m, std, ks, s)
        CURVES[(m, s)] = (sname(st), ks[s], cur)
        print(f"\nbatter step {s + 1}: {sname(st)}   best k = {f(ks[s])}")
        print("  " + "  ".join(f"{r.k}:{r.rise:+.0f}" for r in cur.itertuples()))
        worst = cur.loc[cur["rise"].idxmax()]
        print(f"  worst k on the grid: {worst['k']} costs {worst['rise']:+.0f} (SE {worst['SE']:.0f})")

# The sweep is slow, so keep it: the figure script reads this instead of rerunning.
CURVE_CSV = Path(_here).parent / "k_curves.csv"
pd.concat([c.assign(structure=m, step=s, split=nm, best=f(bk))
           for (m, s), (nm, bk, c) in CURVES.items()]).to_csv(CURVE_CSV, index=False)
print(f"\ncurves -> {CURVE_CSV}")


# ---------------- B. how much of each rate's spread is real ----------------
print("\n\n=== B. real share of the spread across players (method of moments) ===")
print("low share = mostly luck. Each rate on its own denominator; 25+ in the denominator.")
GROUPS = {"per PA": {"K": ["K"], "BB": ["BB"], "HBP": ["HBP"], "HR": ["HR"],
                     "in park": ["1B", "2B", "ROE", "OUT"]},
          "per ball in park": {"1B": ["1B"], "hits (1B+2B)": ["1B", "2B"],
                               "2B": ["2B"], "ROE": ["ROE"], "out": ["OUT"]}}
DEN = {"per PA": None, "per ball in park": ["1B", "2B", "ROE", "OUT"]}
rows = []
for sd, label in (("B", "batters"), ("P", "pitchers")):
    Xs = counts(pa, sd)
    for denom, lines in GROUPS.items():
        dcols = DEN[denom]
        m = Xs.sum(axis=1) if dcols is None else Xs[:, [IX[c] for c in dcols]].sum(axis=1)
        keep = m >= 25
        for nm, cols in lines.items():
            if dcols is not None and set(cols) == set(dcols):
                continue
            x = Xs[:, [IX[c] for c in cols]].sum(axis=1)[keep]
            mk = m[keep].astype(float)
            r = x / mk
            lgr = x.sum() / mk.sum()
            obs = float(((r - lgr) ** 2).mean())
            noise = float((lgr * (1 - lgr) / mk).mean())
            rows.append({"side": label, "rate": f"{nm} {denom}", "players": int(keep.sum()),
                         "league": round(100 * lgr, 1),
                         "observed SD": round(100 * np.sqrt(obs), 1),
                         "luck SD": round(100 * np.sqrt(noise), 1),
                         "real SD": round(100 * np.sqrt(max(obs - noise, 0)), 1),
                         "real share": f"{max(obs - noise, 0) / obs:.0%}"})
t = pd.DataFrame(rows)
for label in ("batters", "pitchers"):
    print(f"\n{label}:")
    print(t[t["side"] == label].drop(columns="side").to_string(index=False))
