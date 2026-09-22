"""Per-line mixing weight with walks and hit-by-pitches kept apart.

    pixi run python analysis/dice/mixture_eight.py

The free pass was merged on the grounds that the two do the same thing on the
bases and that keeping them apart predicted no better in runs. Runs cannot see
the difference -- a walk is worth 0.45 and an HBP 0.49 -- so that test was close
to blind by construction.

A mixture asks a different question: whose card should the line be read from?
If walks are the pitcher's doing and hit-by-pitches the batter's, one merged
free-pass line forces a single weight on two lines that want opposite ones, and
the merged weight is an average of nothing in particular.

Eight lines here: the seven cards plus the free pass split back into BB and HBP
using each player's own d10 share, which dice.build already returns.

Also scores fixing 2B at the league rate for everyone, against reading it off
either card.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, build, plate_appearances, usage)

pd.set_option("display.width", 240)
SPLITS, SEED, EPS = 20, 20260920, 1e-6
GRID = np.round(np.arange(0, 1.0001, 0.05), 2)
L8 = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"]
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares = usage(pa)
gids = sorted(pa["game_id"].unique())
IX8 = {l: i for i, l in enumerate(L8)}
y = pa["line"].map(IX8).to_numpy()
gcode = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = gcode.max() + 1
rng = np.random.default_rng(SEED)


def eight(c7, hs):
    """Seven printed lines plus the d10 split, back to eight."""
    fp = c7[:, CARD_LINES.index("FP")]
    cols = {"K": c7[:, CARD_LINES.index("K")], "BB": fp * (1 - hs), "HBP": fp * hs}
    for l in ("HR", "1B", "2B", "ROE", "OUT"):
        cols[l] = c7[:, CARD_LINES.index(l)]
    return np.column_stack([cols[l] for l in L8])


loss = np.zeros((nG, len(L8), len(GRID)))
ctrl = np.zeros((nG, len(L8), len(GRID)))
seen = np.zeros(nG)

for rep in range(SPLITS):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side_of = pa["game_id"].map(half).to_numpy()
    for fold in (0, 1):
        tr, te = pa[side_of != fold], np.flatnonzero(side_of == fold)
        built = {}
        for side, steps, ks, slug in (("B", BATTER_STEPS, BATTER_K, SLUGGERS),
                                      ("P", PITCHER_STEPS, PITCHER_K, ())):
            X = pd.crosstab(tr[side], tr["line"]).reindex(columns=LINES, fill_value=0)
            ids = X.index.to_numpy()
            names = [players["person_name"].get(i, i) for i in ids]
            c7, hs = build(X.to_numpy().astype(float), names,
                           shares[side].reindex(ids).fillna(0.0).to_numpy(), steps, ks, slug)
            built[side] = pd.DataFrame(eight(c7, hs), index=ids, columns=L8)
        Lh = tr["line"].value_counts(normalize=True).reindex(L8, fill_value=0).to_numpy()
        ok = [i for i in te if pa["B"].iloc[i] in built["B"].index
              and pa["P"].iloc[i] in built["P"].index]
        if not ok:
            continue
        Bm = built["B"].loc[pa["B"].iloc[ok]].to_numpy()
        Pm = built["P"].loc[pa["P"].iloc[ok]].to_numpy()
        yy, gg = y[ok], gcode[ok]
        np.add.at(seen, gg, 1.0)
        for j in range(len(L8)):
            hit = (yy == j).astype(float)
            for m, a in enumerate(GRID):
                for target, store in ((Pm[:, j], loss), (Lh[j], ctrl)):
                    p = np.clip(a * target + (1 - a) * Bm[:, j], EPS, 1 - EPS)
                    np.add.at(store[:, j, m], gg,
                              -(hit * np.log(p) + (1 - hit) * np.log(1 - p)))

tot = loss.sum(axis=0) / seen.sum()
ctot = ctrl.sum(axis=0) / seen.sum()
draws = np.random.default_rng(SEED + 3).integers(0, nG, size=(1000, nG))
rows = []
for j, line in enumerate(L8):
    best = int(np.argmin(tot[j]))
    bs_a = [GRID[int(np.argmin(loss[d, j, :].sum(axis=0)))] for d in draws]
    lg = 1000 * (ctot[j, best] - tot[j, best])
    bs_lg = (1000 * (ctrl[:, j, best][draws].sum(axis=1) - loss[:, j, best][draws].sum(axis=1))
             / seen[draws].sum(axis=1))
    rows.append({"line": line, "best a": GRID[best],
                 "a, 90% of resamples": f"{np.percentile(bs_a, 5):.2f}-{np.percentile(bs_a, 95):.2f}",
                 "gain vs batter-only": round(1000 * (tot[j, 0] - tot[j, best]), 2),
                 "pitcher beats league by": f"{lg:+.2f} (SE {bs_lg.std():.2f})",
                 "loss at best a": round(1000 * tot[j, best], 1),
                 "loss, flat league": round(1000 * ctot[j, -1], 1)})
print(f"held-out, {SPLITS} splits x 2 folds; log loss x1000 per PA\n")
print(pd.DataFrame(rows).to_string(index=False))
print("\n('loss, flat league' is a = 1 toward the league: the same fixed band for everyone)")
print("\ncurve by alpha, walks and HBP:")
curve = pd.DataFrame(1000 * tot, index=L8, columns=[f"{a:.2f}" for a in GRID])
print(curve.loc[["BB", "HBP", "2B"], ["0.00", "0.20", "0.40", "0.60", "0.80", "1.00"]].round(2).to_string())
