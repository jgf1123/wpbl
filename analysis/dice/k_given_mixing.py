"""If a card will be mixed with the opponent's, what k should build it?

    pixi run python analysis/dice/k_given_mixing.py

Mixing is itself a kind of smoothing: reading the pitcher's card 40% of the time
pulls the batter toward the middle, exactly as a larger k would. The k values in
dice.py were tuned to make a card predict well ON ITS OWN (a = 0). If the card is
going to be mixed, some of that smoothing is now done twice, and the right k
should fall.

So k is re-tuned at each mixing weight, by coordinate descent on held-out games,
scored the usual way: squared error of the expected run value of a plate
appearance. BB | HBP is held fixed -- runs cannot see it, so a runs search
returns an arbitrary tie.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, TO_LINE, bands, build,
                       plate_appearances, usage)

pd.set_option("display.width", 240)
GRID = [2 ** (x / 2) for x in range(0, 25)] + [np.inf]
ALPHAS = [0.35]        # the one global weight the nested test picked
SPLIT_STEP = {"B": 3, "P": 2}                 # BB | HBP: fixed, runs are blind to it
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
for _ in range(10):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side = pa["game_id"].map(half).to_numpy()
    for f in (0, 1):
        folds.append((pa[side != f], np.flatnonzero(side == f)))


def make(frame, side, steps, ks):
    X = pd.crosstab(frame[side], frame["line"]).reindex(columns=LINES, fill_value=0)
    ids = X.index.to_numpy()
    nms = [players["person_name"].get(i, i) for i in ids]
    c = build(X.to_numpy().astype(float), nms,
              shares[side].reindex(ids).fillna(0).to_numpy(), steps, ks,
              SLUGGERS if side == "B" else (), band)
    return pd.DataFrame(c, index=ids, columns=CARD_LINES)


def score(a, kb, kp):
    """Held-out squared error of expected run value, cards mixed at weight a."""
    tot, cnt = 0.0, 0
    for tr, te in folds:
        cb, cp = make(tr, "B", BATTER_STEPS, kb), make(tr, "P", PITCHER_STEPS, kp)
        ok = [i for i in te if pa["B"].iloc[i] in cb.index and pa["P"].iloc[i] in cp.index]
        if not ok:
            continue
        mix = (a * cp.loc[pa["P"].iloc[ok]].to_numpy()
               + (1 - a) * cb.loc[pa["B"].iloc[ok]].to_numpy())
        tot += float(((W[y[ok]] - mix @ W) ** 2).sum())
        cnt += len(ok)
    return tot / cnt


rows = []
for a in ALPHAS:
    kb, kp = list(BATTER_K), list(PITCHER_K)
    for _ in range(2):
        for j in range(len(kb)):
            if j == SPLIT_STEP["B"]:
                continue
            kb[j] = min(GRID, key=lambda k: score(a, kb[:j] + [k] + kb[j + 1:], kp))
        for j in range(len(kp)):
            if j == SPLIT_STEP["P"]:
                continue
            kp[j] = min(GRID, key=lambda k: score(a, kb, kp[:j] + [k] + kp[j + 1:]))
    rows.append({"a": a,
                 "batter k": " ".join(f"{k:g}" for k in kb),
                 "pitcher k": " ".join(f"{k:g}" for k in kp),
                 "score x1e6": round(1e6 * score(a, kb, kp), 1)})
    print(f"a={a}: batter {rows[-1]['batter k']} | pitcher {rows[-1]['pitcher k']}", flush=True)

print("\nbatter steps:  " + "; ".join(" | ".join("+".join(c) for c in p) for _, p in BATTER_STEPS))
print("pitcher steps: " + "; ".join(" | ".join("+".join(c) for c in p) for _, p in PITCHER_STEPS))
print()
print(pd.DataFrame(rows).to_string(index=False))
print("\nthe shipped cards were tuned at a = 0:")
print(f"  batter  {' '.join(f'{k:g}' for k in BATTER_K)}")
print(f"  pitcher {' '.join(f'{k:g}' for k in PITCHER_K)}")
