"""The BB | HBP step's k, fitted separately for each side.

    pixi run python analysis/dice/split_k_final.py

This step splits a player's free passes into walks and hit-by-pitches. Runs
cannot choose it -- a walk is worth 0.45 and an HBP 0.49 -- so it is fitted on
log loss, per the exception in spec 9.0.

There is no reason the two sides should share a value: a batter's walk/HBP mix
and a pitcher's are different quantities with different amounts of signal
behind them (HBP is 58% real spread for batters and 3% for pitchers). So the
whole grid is searched, both sides at once, rather than one shared k.

Done efficiently: for each fold the batter cards are built once per candidate
batter k and the pitcher cards once per candidate pitcher k, then every pair is
scored from the cached cards.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, MIX_ALPHA,
                       PITCHER_K, PITCHER_STEPS, SLUGGERS, bands, build,
                       plate_appearances, usage)

pd.set_option("display.width", 250)
SPLITS = 15
GRID = [2 ** (e / 2) for e in range(0, 17)] + [np.inf]
SPLIT_B, SPLIT_P = 3, 2
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares, band = usage(pa), bands(pa)
gids = sorted(pa["game_id"].unique())
IX = {l: i for i, l in enumerate(CARD_LINES)}
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


rng = np.random.default_rng(20260921)
loss = np.zeros((len(GRID), len(GRID), nG))
cnt = np.zeros(nG)
for rep in range(SPLITS):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side_of = pa["game_id"].map(half).to_numpy()
    for fold in (0, 1):
        tr, te = pa[side_of != fold], np.flatnonzero(side_of == fold)
        bcards, pcards = [], []
        for k in GRID:
            kb = list(BATTER_K); kb[SPLIT_B] = k
            kp = list(PITCHER_K); kp[SPLIT_P] = k
            bcards.append(make(tr, "B", kb))
            pcards.append(make(tr, "P", kp))
        ok = [i for i in te if pa["B"].iloc[i] in bcards[0].index
              and pa["P"].iloc[i] in pcards[0].index]
        if not ok:
            continue
        yy, gg = y[ok], gcode[ok]
        np.add.at(cnt, gg, 1.0)
        Bs = [c.loc[pa["B"].iloc[ok]].to_numpy() for c in bcards]
        Ps = [c.loc[pa["P"].iloc[ok]].to_numpy() for c in pcards]
        for a, Bm in enumerate(Bs):
            for b, Pm in enumerate(Ps):
                mix = MIX_ALPHA * Pm + (1 - MIX_ALPHA) * Bm
                np.add.at(loss[a, b], gg,
                          -np.log(np.clip(mix[np.arange(len(yy)), yy], 1e-9, None)))
    print(f"  split {rep + 1}/{SPLITS}", flush=True)

tot = loss.sum(axis=2) / cnt.sum()
ai, bi = np.unravel_index(np.argmin(tot), tot.shape)
draws = np.random.default_rng(13).integers(0, nG, size=(2000, nG))
d = loss - loss[ai, bi]
se = np.zeros_like(tot)
for a in range(len(GRID)):
    for b in range(len(GRID)):
        bs = 1000 * d[a, b][draws].sum(axis=1) / cnt[draws].sum(axis=1)
        se[a, b] = bs.std()
lab = ["inf" if np.isinf(k) else f"{k:g}" for k in GRID]
print(f"\nlog loss x1000 by (batter k, pitcher k); alpha={MIX_ALPHA:.4f}\n")
print(pd.DataFrame(1000 * tot, index=[f"B {l}" for l in lab],
                   columns=[f"P {l}" for l in lab]).round(2).to_string())
print(f"\nbest: batter k = {lab[ai]}, pitcher k = {lab[bi]}  "
      f"(log loss {1000 * tot[ai, bi]:.3f})")
within = [(lab[a], lab[b]) for a in range(len(GRID)) for b in range(len(GRID))
          if 1000 * (tot[a, b] - tot[ai, bi]) <= se[a, b]]
print(f"pairs within 1 SE of the best: {len(within)}")
print("  batter k range " + ", ".join(sorted({w[0] for w in within}, key=lambda v: float(v))))
print("  pitcher k range " + ", ".join(sorted({w[1] for w in within}, key=lambda v: float(v))))
b_best = int(np.argmin(tot.min(axis=1)))
p_best = int(np.argmin(tot.min(axis=0)))
print(f"\nbest batter k holding pitcher at its best: {lab[b_best]}")
print(f"best pitcher k holding batter at its best: {lab[p_best]}")
shared = [1000 * tot[i, i] for i in range(len(GRID))]
print(f"best SHARED k (the simplification this replaces): {lab[int(np.argmin(shared))]}, "
      f"log loss {min(shared):.3f}, costing {min(shared) - 1000 * tot[ai, bi]:+.3f}")
