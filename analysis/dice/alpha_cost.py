"""What does choosing a mixing weight other than the runs-optimal one cost?

    pixi run python analysis/dice/alpha_cost.py

joint_runs.py converged on a = 0.20 from six starts, with k converging to the
same values every time. Log loss and playability both want something nearer
0.45. This prices that disagreement: at the converged k, every weight is scored
on both metrics, and each is compared against its own metric's best with a
standard error, so "0.45 costs X runs" becomes a number rather than a worry.

Both scores and both standard errors come from the same held-out plate
appearances, accumulated per game so the bootstrap can resample games.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (BATTER_STEPS, CARD_LINES, LINES, PITCHER_STEPS, SLUGGERS,
                       TO_LINE, bands, build, plate_appearances, usage)

pd.set_option("display.width", 250)
SPLITS = 20
AGRID = np.round(np.arange(0, 0.7001, 0.025), 3)
# the converged values from joint_runs.py; BB | HBP keeps split_k.py's 8 and 16
KB = [16.0, 2.0, 16.0, 8.0, 2 ** 5.5]
KP = [1.0, 64.0, 16.0, np.inf, np.inf]
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares, band = usage(pa), bands(pa)
gids = sorted(pa["game_id"].unique())
IX = {l: i for i, l in enumerate(CARD_LINES)}
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES).to_numpy()
y = pa["line"].map(IX).to_numpy()
gcode = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = gcode.max() + 1


def make(frame, side, ks):
    steps = BATTER_STEPS if side == "B" else PITCHER_STEPS
    X = pd.crosstab(frame[side], frame["line"]).reindex(columns=LINES, fill_value=0)
    ids = X.index.to_numpy()
    nms = [players["person_name"].get(i, i) for i in ids]
    c = build(X.to_numpy().astype(float), nms,
              shares[side].reindex(ids).fillna(0).to_numpy(), steps, ks,
              SLUGGERS if side == "B" else (), band)
    return pd.DataFrame(c, index=ids, columns=CARD_LINES)


runs = np.zeros((nG, len(AGRID)))
lls = np.zeros((nG, len(AGRID)))
cnt = np.zeros(nG)
rng = np.random.default_rng(20260921)
for rep in range(SPLITS):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side_of = pa["game_id"].map(half).to_numpy()
    for fold in (0, 1):
        tr, te = pa[side_of != fold], np.flatnonzero(side_of == fold)
        cb, cp = make(tr, "B", KB), make(tr, "P", KP)
        ok = [i for i in te if pa["B"].iloc[i] in cb.index and pa["P"].iloc[i] in cp.index]
        if not ok:
            continue
        Bm = cb.loc[pa["B"].iloc[ok]].to_numpy()
        Pm = cp.loc[pa["P"].iloc[ok]].to_numpy()
        yy, gg = y[ok], gcode[ok]
        np.add.at(cnt, gg, 1.0)
        for m, a in enumerate(AGRID):
            mix = a * Pm + (1 - a) * Bm
            np.add.at(runs[:, m], gg, (W[yy] - mix @ W) ** 2)
            np.add.at(lls[:, m], gg, -np.log(np.clip(mix[np.arange(len(yy)), yy], 1e-9, None)))
    print(f"  split {rep + 1}/{SPLITS}", flush=True)

draws = np.random.default_rng(5).integers(0, nG, size=(4000, nG))
r_tot, l_tot = runs.sum(axis=0), lls.sum(axis=0)
r_best, l_best = int(np.argmin(r_tot)), int(np.argmin(l_tot))
rows = []
for m, a in enumerate(AGRID):
    dr = runs[:, m] - runs[:, r_best]
    dl = lls[:, m] - lls[:, l_best]
    br = 1e6 * dr[draws].sum(axis=1) / cnt[draws].sum(axis=1)
    bl = 1000 * dl[draws].sum(axis=1) / cnt[draws].sum(axis=1)
    rows.append({"alpha": a,
                 "runs x1e6": round(1e6 * r_tot[m] / cnt.sum(), 1),
                 "cost vs runs-best": f"{1e6 * dr.sum() / cnt.sum():+.1f}",
                 "in SE": round((1e6 * dr.sum() / cnt.sum()) / br.std(), 2) if br.std() else 0.0,
                 "log loss x1000": round(1000 * l_tot[m] / cnt.sum(), 2),
                 "cost vs ll-best": f"{1000 * dl.sum() / cnt.sum():+.2f}",
                 "in SE ": round((1000 * dl.sum() / cnt.sum()) / bl.std(), 2) if bl.std() else 0.0})
t = pd.DataFrame(rows)
print(f"\nat the converged k, {SPLITS} splits x 2 folds\n")
print(t.to_string(index=False))
print(f"\nruns best at a={AGRID[r_best]}, log loss best at a={AGRID[l_best]}")
for a in (0.35, 0.40, 0.45, 0.50):
    m = int(np.argmin(np.abs(AGRID - a)))
    print(f"  choosing a={AGRID[m]}: {t.iloc[m]['cost vs runs-best']} runs "
          f"({t.iloc[m]['in SE']} SE), {t.iloc[m]['cost vs ll-best']} log loss "
          f"({t.iloc[m]['in SE ']} SE)")
