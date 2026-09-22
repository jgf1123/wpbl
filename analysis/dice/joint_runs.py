"""Optimise k and the mixing weight together on runs alone, from several starts.

    pixi run python analysis/dice/joint_runs.py

fit_cards.py alternated two objectives -- the weight on log loss, k on runs --
and drifted to a fixed point worse than where it began on BOTH scores. That is
what mixing objectives does: the alternation descends on nothing.

One objective fixes that. Coordinate descent on runs alone is a true descent:
every accepted move lowers the same number, so the run can only improve, and
whatever it does is the landscape talking.

That makes it a diagnostic as well as a fit. If runs really can see the pair,
every start should land in the same place. If the runs surface is flat -- which
alpha_sweep.py suggested, the weight being worth 0.2 to 1.1 SE -- then different
starts will finish in scattered corners with near-identical scores, and that
settles whether runs can choose the pair at all.

Log loss is reported alongside, never optimised, so the two can be compared at
each stopping point.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, TO_LINE, bands, build,
                       plate_appearances, usage)

pd.set_option("display.width", 250)
SPLITS, ROUNDS = 5, 6
KGRID = [2.0 ** (e / 2) for e in range(0, 25)] + [np.inf]
AGRID = np.round(np.arange(0, 0.8001, 0.025), 3)
SPLIT = {"B": 3, "P": 2}                      # BB | HBP: runs are blind to it
STARTS = [
    ("low k, a=0.10", [2.0] * 5, [2.0] * 5, 0.10),
    ("low k, a=0.45", [2.0] * 5, [2.0] * 5, 0.45),
    ("mid k, a=0.25", [16.0] * 5, [16.0] * 5, 0.25),
    ("high k, a=0.10", [256.0] * 5, [256.0] * 5, 0.10),
    ("high k, a=0.60", [256.0] * 5, [256.0] * 5, 0.60),
    ("shipped, a=0.45", list(BATTER_K), list(PITCHER_K), 0.45),
]
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares, band = usage(pa), bands(pa)
gids = sorted(pa["game_id"].unique())
IX = {l: i for i, l in enumerate(CARD_LINES)}
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES).to_numpy()
y = pa["line"].map(IX).to_numpy()

rng = np.random.default_rng(20260921)
folds = []
for _ in range(SPLITS):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side = pa["game_id"].map(half).to_numpy()
    for f in (0, 1):
        folds.append((pa[side != f], np.flatnonzero(side == f)))

_cache = {}


def cards_for(i, side, ks):
    key = (i, side, tuple(ks))
    if key not in _cache:
        if len(_cache) > 600:
            _cache.clear()
        tr = folds[i][0]
        steps = BATTER_STEPS if side == "B" else PITCHER_STEPS
        X = pd.crosstab(tr[side], tr["line"]).reindex(columns=LINES, fill_value=0)
        ids = X.index.to_numpy()
        nms = [players["person_name"].get(j, j) for j in ids]
        c = build(X.to_numpy().astype(float), nms,
                  shares[side].reindex(ids).fillna(0).to_numpy(), steps, ks,
                  SLUGGERS if side == "B" else (), band)
        _cache[key] = pd.DataFrame(c, index=ids, columns=CARD_LINES)
    return _cache[key]


def score(kb, kp, a):
    rt, lt, n = 0.0, 0.0, 0
    for i, (tr, te) in enumerate(folds):
        cb, cp = cards_for(i, "B", kb), cards_for(i, "P", kp)
        ok = [j for j in te if pa["B"].iloc[j] in cb.index and pa["P"].iloc[j] in cp.index]
        if not ok:
            continue
        mix = (a * cp.loc[pa["P"].iloc[ok]].to_numpy()
               + (1 - a) * cb.loc[pa["B"].iloc[ok]].to_numpy())
        yy = y[ok]
        rt += float(((W[yy] - mix @ W) ** 2).sum())
        lt += float(-np.log(np.clip(mix[np.arange(len(yy)), yy], 1e-9, None)).sum())
        n += len(ok)
    return rt / n, lt / n


rows = []
for name, kb0, kp0, a0 in STARTS:
    kb, kp, a = list(kb0), list(kp0), a0
    best = score(kb, kp, a)[0]
    for rnd in range(ROUNDS):
        moved = False
        for j in range(len(kb)):
            if j == SPLIT["B"]:
                continue
            cand = min(KGRID, key=lambda k: score(kb[:j] + [k] + kb[j + 1:], kp, a)[0])
            if cand != kb[j]:
                kb[j], moved = cand, True
        for j in range(len(kp)):
            if j == SPLIT["P"]:
                continue
            cand = min(KGRID, key=lambda k: score(kb, kp[:j] + [k] + kp[j + 1:], a)[0])
            if cand != kp[j]:
                kp[j], moved = cand, True
        cand_a = float(min(AGRID, key=lambda g: score(kb, kp, g)[0]))
        if abs(cand_a - a) > 1e-9:
            a, moved = cand_a, True
        r, l = score(kb, kp, a)
        assert r <= best + 1e-12, "coordinate descent went uphill"
        best = r
        if not moved:
            break
    r, l = score(kb, kp, a)
    rows.append({"start": name, "rounds": rnd + 1, "final a": a,
                 "runs x1e6": round(1e6 * r, 1), "log loss x1000": round(1000 * l, 2),
                 "batter k": " ".join(f"{v:g}" for v in kb),
                 "pitcher k": " ".join(f"{v:g}" for v in kp)})
    print(f"  {name}: a={a:.3f} runs {1e6 * r:.1f} ll {1000 * l:.2f}", flush=True)

t = pd.DataFrame(rows)
print("\njoint coordinate descent on RUNS ONLY, from six starts\n")
print(t.to_string(index=False))
print(f"\nrun loss across the six endpoints: {t['runs x1e6'].min():.1f} to "
      f"{t['runs x1e6'].max():.1f}  (spread {t['runs x1e6'].max() - t['runs x1e6'].min():.1f})")
print(f"final weight across the six:        {t['final a'].min():.3f} to {t['final a'].max():.3f}")
print(f"log loss across the six:            {t['log loss x1000'].min():.2f} to "
      f"{t['log loss x1000'].max():.2f}")
print("\nIf the run losses cluster while the weights scatter, runs cannot choose the pair.")
