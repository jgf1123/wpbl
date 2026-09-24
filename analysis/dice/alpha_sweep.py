"""Sweep the mixing weight under both metrics, for both candidate k sets.

    pixi run python analysis/dice/alpha_sweep.py

Runs picked a weight near 0.15, log loss near 0.43. Before treating that as a
conflict it is worth seeing the curves: a flat-bottomed runs curve would mean
there is no disagreement, only imprecision, and its "minimum" is wherever the
noise happened to dip.

Both k candidates are swept, because the two choices interact -- mixing is
itself shrinkage, so a card built with large k is already smoothed and may want
less mixing:

  SHIPPED  whatever dice.py holds, read at import -- never copied
  high k   64 4 16 8 64 | 32 1024 16 inf inf   built for a card read ALONE

Cards are built once per fold per k set; every weight is then scored on the same
held-out plate appearances, so the curves are directly comparable.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, TO_LINE, bands, build,
                       plate_appearances, usage)

pd.set_option("display.width", 250)
SPLITS = 15
AGRID = np.round(np.arange(0, 0.8001, 0.05), 3)
# The shipped set is READ FROM dice.py, not copied here. It used to be copied,
# and by 23 Sep the copy had drifted: this file swept [11.3, 1, 8, 8, 32] under a
# label saying "in dice.py now" while dice.py shipped [16, 2, 16, 2.83, 45.25].
# Section 4's "runs bottom near 0.15-0.20" was measured on the copy, so it
# described a configuration nobody was playing with. Never copy them again.
K_SETS = {
    "SHIPPED (dice.py)": (list(BATTER_K), list(PITCHER_K)),
    "high k (card alone)": ([64.0, 4.0, 16.0, 8.0, 64.0],
                            [32.0, 1024.0, 16.0, np.inf, np.inf]),
}
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


def make(frame, side, steps, ks):
    X = pd.crosstab(frame[side], frame["line"]).reindex(columns=LINES, fill_value=0)
    ids = X.index.to_numpy()
    nms = [players["person_name"].get(i, i) for i in ids]
    c = build(X.to_numpy().astype(float), nms,
              shares[side].reindex(ids).fillna(0).to_numpy(), steps, ks,
              SLUGGERS if side == "B" else (), band)
    return pd.DataFrame(c, index=ids, columns=CARD_LINES)


runs = {k: np.zeros((nG, len(AGRID))) for k in K_SETS}
lls = {k: np.zeros((nG, len(AGRID))) for k in K_SETS}
cnt = np.zeros(nG)
rng = np.random.default_rng(20260921)

for rep in range(SPLITS):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side_of = pa["game_id"].map(half).to_numpy()
    for fold in (0, 1):
        tr, te = pa[side_of != fold], np.flatnonzero(side_of == fold)
        first = True
        for name, (kb, kp) in K_SETS.items():
            cb, cp = make(tr, "B", BATTER_STEPS, kb), make(tr, "P", PITCHER_STEPS, kp)
            ok = [i for i in te if pa["B"].iloc[i] in cb.index and pa["P"].iloc[i] in cp.index]
            if not ok:
                continue
            Bm = cb.loc[pa["B"].iloc[ok]].to_numpy()
            Pm = cp.loc[pa["P"].iloc[ok]].to_numpy()
            yy, gg = y[ok], gcode[ok]
            if first:
                np.add.at(cnt, gg, 1.0)
                first = False
            for m, a in enumerate(AGRID):
                mix = a * Pm + (1 - a) * Bm
                np.add.at(runs[name][:, m], gg, (W[yy] - mix @ W) ** 2)
                np.add.at(lls[name][:, m], gg,
                          -np.log(np.clip(mix[np.arange(len(yy)), yy], 1e-9, None)))
    print(f"  split {rep + 1}/{SPLITS}", flush=True)

draws = np.random.default_rng(3).integers(0, nG, size=(2000, nG))
out = {}
for name in K_SETS:
    r = 1e6 * runs[name].sum(axis=0) / cnt.sum()
    l = 1000 * lls[name].sum(axis=0) / cnt.sum()
    out[(name, "runs")] = r
    out[(name, "log loss")] = l
tab = pd.DataFrame(out, index=[f"{a:.2f}" for a in AGRID]).round(2)
tab.index.name = "alpha"
print("\nheld-out score by mixing weight (lower is better)\n")
print(tab.to_string())

print("\n=== where each curve bottoms out, and how deep the bowl is ===")
for name in K_SETS:
    for metric, store, scale in (("runs", runs, 1e6), ("log loss", lls, 1000)):
        tot = store[name].sum(axis=0)
        best = int(np.argmin(tot))
        # SE of (worst sensible end - best), resampling games
        d = store[name][:, 0] - store[name][:, best]         # a = 0 minus the best
        bs = scale * d[draws].sum(axis=1) / cnt[draws].sum(axis=1)
        depth = scale * d.sum() / cnt.sum()
        # how wide is the region within one SE of the minimum?
        curve = scale * tot / cnt.sum()
        near = [f"{AGRID[i]:.2f}" for i in range(len(AGRID))
                if curve[i] - curve[best] <= bs.std()]
        print(f"  {name:22s} {metric:9s} best a {AGRID[best]:.2f}; "
              f"gain over a=0 {depth:+.2f} (SE {bs.std():.2f}); "
              f"within 1 SE of the best: {near[0]}-{near[-1]}")
