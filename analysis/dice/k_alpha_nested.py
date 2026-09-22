"""Fit the smoothing and the mixing weight together, and see if that survives nesting.

    pixi run python analysis/dice/k_alpha_nested.py

The two interact: mixing is a form of smoothing, so the k that suits a card read
on its own is too large for a card that will be mixed. Tuning them separately
therefore leaves something on the table -- but tuning them together is ten k plus
a weight fitted at once, which is exactly the kind of thing that looks good on
the games it was fitted to and worse everywhere else.

So the joint fit is nested the way spec 9.0 requires:

    outer: split the games. The test half is untouched until scoring.
    inner: split the build half; cards from one part, k and the weight chosen on
           the other, both directions.
    then:  rebuild on the whole build half with the chosen k, mix at the chosen
           weight, score the untouched half.

Compared with tuning them in sequence (k for a card read alone, then the weight),
which is what the shipped cards do, and with no mixing at all.

Scored on runs, per spec 9.0. The BB | HBP step is held fixed: runs cannot see
it, so a runs search there returns an arbitrary tie.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, TO_LINE, bands, build,
                       plate_appearances, usage)

pd.set_option("display.width", 240)
OUTER = 6
KGRID = [2.0 ** e for e in range(0, 13)] + [np.inf]
AGRID = np.round(np.arange(0, 0.8001, 0.05), 3)
SPLIT = {"B": 3, "P": 2}                     # BB | HBP, fixed at split_k's value
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


def err(train, idx, kb, kp, a, per_game=False):
    cb, cp = make(train, "B", BATTER_STEPS, kb), make(train, "P", PITCHER_STEPS, kp)
    ok = [i for i in idx if pa["B"].iloc[i] in cb.index and pa["P"].iloc[i] in cp.index]
    if not ok:
        return (np.zeros(nG), np.zeros(nG)) if per_game else np.inf
    mix = (a * cp.loc[pa["P"].iloc[ok]].to_numpy()
           + (1 - a) * cb.loc[pa["B"].iloc[ok]].to_numpy())
    e = (W[y[ok]] - mix @ W) ** 2
    if per_game:
        tot, cnt = np.zeros(nG), np.zeros(nG)
        np.add.at(tot, gcode[ok], e)
        np.add.at(cnt, gcode[ok], 1.0)
        return tot, cnt
    return float(e.mean())


def tune(train, idx, joint=True):
    """Coordinate descent over the tunable k and, if joint, the mixing weight."""
    kb, kp, a = list(BATTER_K), list(PITCHER_K), (0.4 if joint else 0.0)
    for _ in range(2):
        for j in range(len(kb)):
            if j != SPLIT["B"]:
                kb[j] = min(KGRID, key=lambda k: err(train, idx, kb[:j] + [k] + kb[j + 1:], kp, a))
        for j in range(len(kp)):
            if j != SPLIT["P"]:
                kp[j] = min(KGRID, key=lambda k: err(train, idx, kb, kp[:j] + [k] + kp[j + 1:], a))
        if joint:
            a = float(min(AGRID, key=lambda g: err(train, idx, kb, kp, g)))
    if not joint:                       # sequential: k for a card alone, then the weight
        a = float(min(AGRID, key=lambda g: err(train, idx, kb, kp, g)))
    return kb, kp, a


rng = np.random.default_rng(20260921)
acc = {r: np.zeros(nG) for r in ("joint", "sequential", "shipped k", "no mixing")}
cnt = np.zeros(nG)
picked = {"joint": [], "sequential": []}

for rep in range(OUTER):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side_of = pa["game_id"].map(half).to_numpy()
    for fold in (0, 1):
        build_g = [g for g in gids if half[g] != fold]
        test = np.flatnonzero(side_of == fold)
        inner = dict(zip(build_g, rng.permutation(np.arange(len(build_g)) % 2)))
        code = pa["game_id"].map(lambda g: inner.get(g, -1)).to_numpy()
        fits = {"joint": [], "sequential": []}
        for ip in (0, 1):
            tr, idx = pa[code == 1 - ip], np.flatnonzero(code == ip)
            if not len(idx):
                continue
            for mode in ("joint", "sequential"):
                fits[mode].append(tune(tr, idx, joint=(mode == "joint")))
        if not fits["joint"]:
            continue
        chosen = {}
        for mode in ("joint", "sequential"):
            kb = [float(np.exp(np.mean([np.log(min(f[0][j], 1e6)) for f in fits[mode]])))
                  for j in range(len(BATTER_K))]
            kp = [float(np.exp(np.mean([np.log(min(f[1][j], 1e6)) for f in fits[mode]])))
                  for j in range(len(PITCHER_K))]
            a = float(np.mean([f[2] for f in fits[mode]]))
            chosen[mode] = (kb, kp, a)
            picked[mode].append((kb, kp, a))
        train = pa[side_of != fold]
        for name, (kb, kp, a) in (("joint", chosen["joint"]),
                                  ("sequential", chosen["sequential"]),
                                  ("shipped k", (list(BATTER_K), list(PITCHER_K),
                                                 chosen["sequential"][2])),
                                  ("no mixing", (list(BATTER_K), list(PITCHER_K), 0.0))):
            t, c = err(train, test, kb, kp, a, per_game=True)
            acc[name] += t
            if name == "joint":
                cnt += c
    print(f"  outer {rep + 1}/{OUTER}", flush=True)

draws = np.random.default_rng(11).integers(0, nG, size=(2000, nG))
base = acc["sequential"]
rows = []
for name in ("no mixing", "shipped k", "sequential", "joint"):
    d = acc[name] - base
    bs = 1e6 * d[draws].sum(axis=1) / cnt[draws].sum(axis=1)
    rows.append({"rule": name, "run loss x1e6": round(1e6 * acc[name].sum() / cnt.sum(), 1),
                 "vs sequential": f"{1e6 * d.sum() / cnt.sum():+.1f} (SE {bs.std():.1f})"})
print(f"\nnested, {OUTER} outer x 2 folds; k and the weight chosen inside the build half\n")
print(pd.DataFrame(rows).to_string(index=False))
for mode in ("joint", "sequential"):
    kb = np.array([p[0] for p in picked[mode]])
    kp = np.array([p[1] for p in picked[mode]])
    a = np.array([p[2] for p in picked[mode]])
    print(f"\n{mode}: weight median {np.median(a):.3f} (middle half "
          f"{np.percentile(a, 25):.2f}-{np.percentile(a, 75):.2f})")
    print("  batter k median  " + " ".join(f"{v:7.1f}" for v in np.median(kb, axis=0)))
    print("  pitcher k median " + " ".join(f"{v:7.1f}" for v in np.median(kp, axis=0)))
