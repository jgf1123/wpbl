"""Combination rules that sum to 100% by construction, scored on held-out games.

    pixi run python analysis/dice/hybrid_rules.py

log5_fit.py found that the best rule differs by line: log5 for K, the batter
alone for HR / 1B / OUT, the league for 2B, the pitcher for ROE. Mixing those
does not sum to 100%, and nothing at a table can renormalise.

So the candidates here all sum to 100% without being renormalised. Each starts
from a base that already sums to 100% and applies corrections that cancel:

    batter          her card, the pitcher ignored
    additive        B + P - L  (sums to 1 because 1 + 1 - 1 = 1)
    K only          batter's card, K shifted by (P_K - L_K), OUT gives it back
    K + FP          the same for the free pass as well
    K + FP, 2B flat the same, plus 2B replaced by the league rate
    log5            renormalised: the benchmark a table cannot actually do

Scored by the log loss of the line that actually happened -- the proper score
for a seven-way choice, not seven separate binaries -- plus the run value each
rule misses by.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, TO_LINE, build, plate_appearances, usage)

pd.set_option("display.width", 230)
SPLITS, SEED, FLOOR = 20, 20260920, 0.002
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares = usage(pa)
gids = sorted(pa["game_id"].unique())
IX = {l: i for i, l in enumerate(CARD_LINES)}
y = pa["line"].map(lambda l: IX["FP"] if l in ("BB", "HBP") else IX[l]).to_numpy()
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
lw.loc[lw["line"].isin(["BB", "HBP"]), "line"] = "FP"
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES).to_numpy()
K, FP, TWO, OUT = IX["K"], IX["FP"], IX["2B"], IX["OUT"]


IN_PARK = [IX[l] for l in ("1B", "2B", "ROE", "OUT")]
TRUE_OUT = [IX[l] for l in ("K", "FP", "HR")]


def shift(B, moves, give_back="OUT"):
    """Batter's card with named lines shifted, and where the offset comes from.

    Which line gives the probability back is a real choice, not bookkeeping:
      OUT          the biggest line absorbs it (arbitrary, but simplest at a table)
      proportional every other line gives back in proportion -- what log5 does
      branch       only the shifted line's own branch of the card tree gives back
    """
    p = B.copy()
    moved = np.zeros(len(p))
    for j, delta in moves:
        p[:, j] += delta
        moved += delta
    if give_back == "OUT":
        p[:, OUT] -= moved
        return p
    touched = [j for j, _ in moves]
    pool = ([j for j in range(len(CARD_LINES)) if j not in touched] if give_back == "proportional"
            else [j for j in IN_PARK if j not in touched])
    base = p[:, pool].sum(axis=1, keepdims=True)
    p[:, pool] -= moved[:, None] * p[:, pool] / np.maximum(base, 1e-9)
    return p


def build_rules(B, P, lvec):
    out = {"batter": B.copy(), "additive": B + P - lvec}
    dk, dfp = P[:, K] - lvec[K], P[:, FP] - lvec[FP]
    out["K only"] = shift(B, [(K, dk)])
    out["K+FP, OUT gives back"] = shift(B, [(K, dk), (FP, dfp)], "OUT")
    out["K+FP, all give back"] = shift(B, [(K, dk), (FP, dfp)], "proportional")
    out["K+FP, in-park gives back"] = shift(B, [(K, dk), (FP, dfp)], "branch")
    out["K + FP, 2B flat"] = shift(B, [(K, dk), (FP, dfp), (TWO, lvec[TWO] - B[:, TWO])])
    q = B * P / lvec
    out["log5"] = q / q.sum(axis=1, keepdims=True)
    return out


RULES = ["batter", "additive", "K only", "K+FP, OUT gives back",
         "K+FP, all give back", "K+FP, in-park gives back", "K + FP, 2B flat", "log5"]
rng = np.random.default_rng(SEED)
gcode = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = gcode.max() + 1
ll = {r: np.zeros(nG) for r in RULES}
runs = {r: np.zeros(nG) for r in RULES}
seen = np.zeros(nG)
sums = {r: [] for r in RULES}
negs = {r: 0 for r in RULES}

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
        truth = np.eye(len(CARD_LINES))[yy]
        np.add.at(seen, gg, 1.0)
        for r, p in build_rules(Bm, Pm, lvec).items():
            sums[r].append(p.sum(axis=1))
            negs[r] += int((p < 0).sum())
            q = np.clip(p, FLOOR, None)
            q = q / q.sum(axis=1, keepdims=True)          # scoring only; the rule itself is unchanged
            np.add.at(ll[r], gg, -np.log(q[np.arange(len(yy)), yy]))
            np.add.at(runs[r], gg, np.abs((p - truth) @ W))

rows = []
draws = np.random.default_rng(SEED + 2).integers(0, nG, size=(2000, nG))
base = ll["log5"]
for r in RULES:
    s = np.concatenate(sums[r])
    d = ll[r] - base
    bs = 1000 * d[draws].sum(axis=1) / seen[draws].sum(axis=1)
    rows.append({"rule": r,
                 "sums to 100%": "yes" if np.allclose(s, 1) else
                                 f"{100 * s.min():.1f}-{100 * s.max():.1f}%",
                 "negative cells": negs[r],
                 "log loss x1000": round(1000 * ll[r].sum() / seen.sum(), 2),
                 "vs log5": f"{1000 * d.sum() / seen.sum():+.2f} (SE {bs.std():.2f})",
                 "runs missed x1000": round(1000 * runs[r].sum() / seen.sum(), 1)})
print(f"held-out, {SPLITS} splits x 2 folds; lower log loss is better, "
      f"negative 'vs log5' beats log5\n")
print(pd.DataFrame(rows).to_string(index=False))
