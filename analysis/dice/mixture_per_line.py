"""How much of each line should be read off the pitcher's card?

    pixi run python analysis/dice/mixture_per_line.py

For one line at a time, with the line treated as a binary outcome:

    p = a * pitcher's rate + (1 - a) * batter's rate

and a swept from 0 (read the batter) to 1 (read the pitcher). Scored on games
the cards were not built from.

This ignores the sum-to-100 constraint on purpose: it is the diagnostic that
tells you which lines want the pitcher, so that blocks of the d100 can be built
around them afterwards. A block gets the guarantee back, because the roll lands
in exactly one cell of exactly one card.

Each line also gets a league control: mixing toward the league instead of this
pitcher is the same shrinkage with no matchup information, so the gap between
them is what the pitcher's identity is actually worth on that line.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, build, plate_appearances, usage)

pd.set_option("display.width", 240)
SPLITS, SEED, EPS = 20, 20260920, 1e-6
GRID = np.round(np.arange(0, 1.0001, 0.05), 2)
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares = usage(pa)
gids = sorted(pa["game_id"].unique())
IX = {l: i for i, l in enumerate(CARD_LINES)}
y = pa["line"].map(lambda l: IX["FP"] if l in ("BB", "HBP") else IX[l]).to_numpy()
gcode = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = gcode.max() + 1
rng = np.random.default_rng(SEED)

# per game, per line, per alpha: accumulated log loss
loss = np.zeros((nG, len(CARD_LINES), len(GRID)))
ctrl = np.zeros((nG, len(CARD_LINES), len(GRID)))
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
            c, _ = build(X.to_numpy().astype(float), names,
                         shares[side].reindex(ids).fillna(0.0).to_numpy(), steps, ks, slug)
            built[side] = pd.DataFrame(c, index=ids, columns=CARD_LINES)
        Lh = tr["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
        lvec = np.array([Lh["BB"] + Lh["HBP"] if l == "FP" else Lh[l] for l in CARD_LINES])
        ok = [i for i in te if pa["B"].iloc[i] in built["B"].index
              and pa["P"].iloc[i] in built["P"].index]
        if not ok:
            continue
        Bm = built["B"].loc[pa["B"].iloc[ok]].to_numpy()
        Pm = built["P"].loc[pa["P"].iloc[ok]].to_numpy()
        yy, gg = y[ok], gcode[ok]
        np.add.at(seen, gg, 1.0)
        for j in range(len(CARD_LINES)):
            hit = (yy == j).astype(float)
            for m, a in enumerate(GRID):
                for target, store in ((Pm[:, j], loss), (lvec[j], ctrl)):
                    p = np.clip(a * target + (1 - a) * Bm[:, j], EPS, 1 - EPS)
                    np.add.at(store[:, j, m], gg,
                              -(hit * np.log(p) + (1 - hit) * np.log(1 - p)))

tot = loss.sum(axis=0) / seen.sum()                # lines x alphas
ctot = ctrl.sum(axis=0) / seen.sum()
draws = np.random.default_rng(SEED + 3).integers(0, nG, size=(1000, nG))
rows = []
for j, line in enumerate(CARD_LINES):
    best = int(np.argmin(tot[j]))
    gain = 1000 * (tot[j, 0] - tot[j, best])                    # vs reading the batter
    lg = 1000 * (ctot[j, best] - tot[j, best])                  # pitcher vs league control
    bs_a = [GRID[int(np.argmin((loss[d, j, :].sum(axis=0))))] for d in draws]
    bs_lg = (1000 * (ctrl[:, j, best][draws].sum(axis=1) - loss[:, j, best][draws].sum(axis=1))
             / seen[draws].sum(axis=1))
    rows.append({"line": line,
                 "best a": GRID[best],
                 "a, 90% of resamples": f"{np.percentile(bs_a, 5):.2f}-{np.percentile(bs_a, 95):.2f}",
                 "gain vs batter-only": round(gain, 2),
                 "pitcher beats league by": f"{lg:+.2f} (SE {bs_lg.std():.2f})",
                 "loss at a=0": round(1000 * tot[j, 0], 1),
                 "loss at best a": round(1000 * tot[j, best], 1),
                 "loss at a=0.4": round(1000 * tot[j, GRID.tolist().index(0.4)], 1)})
print(f"held-out, {SPLITS} splits x 2 folds; log loss x1000 per PA\n")
print(pd.DataFrame(rows).to_string(index=False))
print("\ncurve of log loss x1000 by alpha:")
curve = pd.DataFrame(1000 * tot, index=CARD_LINES, columns=[f"{a:.2f}" for a in GRID])
print(curve.loc[:, ["0.00", "0.10", "0.20", "0.30", "0.40", "0.50",
                    "0.60", "0.70", "0.80", "0.90", "1.00"]].round(1).to_string())
