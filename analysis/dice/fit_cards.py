"""The canonical tuner: find k and the mixing weight together, by alternating.

    pixi run python analysis/dice/fit_cards.py

Smoothing and mixing do the same job, so their best values depend on each other:
a card built with less k is worse read alone and better once mixed. Choosing one
and then the other by hand gets the pair wrong, and picking each from a separate
script invites exactly the mismatches this replaces. So they are fitted together,
by coordinate descent, until neither moves.

Which score decides which parameter follows spec 9.0:

  k      runs. The runs curve for k has real structure, and runs are what the
         simulation and every question asked of it are measured in.
  alpha  log loss. Runs cannot see the mixing weight: over 0.05 to 0.45 the runs
         curve is flat to within one standard error (alpha_sweep.py), so a runs
         search there returns wherever the noise dipped. Log loss resolves it at
         4.6 SE.
  BB|HBP not fitted here at all. A walk is worth 0.45 and an HBP 0.49, so runs
         are blind to the step; it keeps split_k.py's log-likelihood value.

Held out by game throughout. This reports the fixed point and how it got there,
so a change of structure can be re-tuned in one command instead of by hand.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, TO_LINE, bands, build,
                       plate_appearances, usage)

pd.set_option("display.width", 240)
SPLITS, ROUNDS = 5, 4
KGRID = [2 ** (e / 2) for e in range(0, 25)] + [np.inf]
AGRID = np.round(np.arange(0, 0.8001, 0.025), 3)
SPLIT = {"B": 3, "P": 2}                       # BB | HBP, left to split_k.py
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


def cards_for(fold_i, side, ks):
    key = (fold_i, side, tuple(ks))
    if key not in _cache:
        tr = folds[fold_i][0]
        steps = BATTER_STEPS if side == "B" else PITCHER_STEPS
        X = pd.crosstab(tr[side], tr["line"]).reindex(columns=LINES, fill_value=0)
        ids = X.index.to_numpy()
        nms = [players["person_name"].get(i, i) for i in ids]
        c = build(X.to_numpy().astype(float), nms,
                  shares[side].reindex(ids).fillna(0).to_numpy(), steps, ks,
                  SLUGGERS if side == "B" else (), band)
        _cache[key] = pd.DataFrame(c, index=ids, columns=CARD_LINES)
        if len(_cache) > 400:
            _cache.clear()
            _cache[key] = pd.DataFrame(c, index=ids, columns=CARD_LINES)
    return _cache[key]


def score(kb, kp, a):
    """(runs, log loss) on held-out plate appearances."""
    rt, lt, n = 0.0, 0.0, 0
    for i, (tr, te) in enumerate(folds):
        cb, cp = cards_for(i, "B", kb), cards_for(i, "P", kp)
        ok = [j for j in te if pa["B"].iloc[j] in cb.index and pa["P"].iloc[j] in cp.index]
        if not ok:
            continue
        mix = (a * cp.loc[pa["P"].iloc[ok]].to_numpy()
               + (1 - a) * cb.loc[pa["B"].iloc[ok]].to_numpy())
        yy = y[ok]
        rt += float((((W[yy] - mix @ W)) ** 2).sum())
        lt += float(-np.log(np.clip(mix[np.arange(len(yy)), yy], 1e-9, None)).sum())
        n += len(ok)
    return rt / n, lt / n


kb, kp, a = list(BATTER_K), list(PITCHER_K), 0.45
print(f"start: a={a}  batter {[round(v, 1) for v in kb]}  pitcher {[round(v, 1) for v in kp]}")
hist = []
for rnd in range(ROUNDS):
    a = float(min(AGRID, key=lambda g: score(kb, kp, g)[1]))          # weight on log loss
    for j in range(len(kb)):                                          # k on runs
        if j != SPLIT["B"]:
            kb[j] = min(KGRID, key=lambda k: score(kb[:j] + [k] + kb[j + 1:], kp, a)[0])
    for j in range(len(kp)):
        if j != SPLIT["P"]:
            kp[j] = min(KGRID, key=lambda k: score(kb, kp[:j] + [k] + kp[j + 1:], a)[0])
    r, l = score(kb, kp, a)
    hist.append({"round": rnd + 1, "alpha": a, "runs x1e6": round(1e6 * r, 1),
                 "log loss x1000": round(1000 * l, 2),
                 "batter k": " ".join(f"{v:g}" for v in kb),
                 "pitcher k": " ".join(f"{v:g}" for v in kp)})
    print(f"  round {rnd + 1}: a={a:.3f} runs {1e6 * r:.1f} log loss {1000 * l:.2f}", flush=True)
    if rnd and hist[-1]["batter k"] == hist[-2]["batter k"] \
            and hist[-1]["pitcher k"] == hist[-2]["pitcher k"] \
            and abs(hist[-1]["alpha"] - hist[-2]["alpha"]) < 1e-9:
        print("  fixed point reached")
        break

print()
print(pd.DataFrame(hist).to_string(index=False))
print("\nbatter steps:  " + "; ".join(" | ".join("+".join(c) for c in p) for _, p in BATTER_STEPS))
print("pitcher steps: " + "; ".join(" | ".join("+".join(c) for c in p) for _, p in PITCHER_STEPS))
print(f"\nfor dice.py:\n  MIX_ALPHA = {a}\n"
      f"  BATTER_K  = {[round(float(v), 4) for v in kb]}\n"
      f"  PITCHER_K = {[round(float(v), 4) for v in kp]}")
